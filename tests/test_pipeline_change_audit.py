"""P0.3 sparse audit: log real value changes, not unchanged source cells."""

import hashlib
import json

import polars as pl
import pytest

from fairmorph_engine.core.export import verified_run
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline


def _run(tmp_path, files, steps, output):
    project = tmp_path / "project"
    initialize_project(project)
    resources = {}
    for name, data in files.items():
        path = tmp_path / f"{name}.csv"
        path.write_text(data, encoding="utf-8")
        imported = import_resource(project, path, name)
        resources[name] = {"resource_id": imported["resource_id"], "format": "csv"}
    config = {
        "schema_version": "fairmorph.pipeline/1",
        "resources": resources,
        "steps": steps,
        "outputs": [output],
    }
    sha = register_pipeline(project, config)["pipeline_sha256"]
    select_project_pipeline(project, sha)
    manifest = execute_project_run(project)
    directory, _ = verified_run(project, manifest["run_id"])
    return project, directory, manifest


def _step(id, operator, inputs, output, parameters):
    return {
        "id": id,
        "operator": operator,
        "inputs": inputs,
        "output": output,
        "parameters": parameters,
    }


def _audit(run):
    return json.loads((run / "audit" / "pipeline.json").read_text(encoding="utf-8"))


def test_no_cell_audit_for_unchanged_values_through_filter_join_unpivot(tmp_path):
    project, run, manifest = _run(
        tmp_path,
        {
            "survey": "key,keep,count\na,1,0\nb,0,4\nc,1,7\n",
            "lookup": "key,label\na,Alpha\nb,Beta\nc,Gamma\n",
        },
        [
            _step(
                "filter",
                "table.filter/1",
                ["survey"],
                "selected",
                {"predicate": {"column": "keep", "op": "eq", "value": 1}},
            ),
            _step(
                "join",
                "table.join/1",
                ["selected", "lookup"],
                "joined",
                {"keys": ["key"], "cardinality": "m:1", "require_match": True},
            ),
            _step(
                "unpivot",
                "table.unpivot/1",
                ["joined"],
                "long",
                {
                    "columns": ["count"],
                    "identifiers": ["key", "label"],
                    "variable": "name",
                    "value": "value",
                },
            ),
        ],
        "long",
    )
    result = pl.read_parquet(run / "outputs" / "long.parquet")
    assert result["value"].to_list() == [0, 7]
    assert not (run / "audit" / "value_changes.parquet").exists()
    assert all(item["path"] != "audit/value_changes.parquet" for item in manifest["artifacts"])
    audit = _audit(run)
    assert audit["value_change_count"] == 0
    assert [s["output_rows"] for s in audit["step_audit"]] == [2, 2, 2]
    assert [s["input_rows"] for s in audit["step_audit"]] == [[3], [2, 3], [2]]
    assert verified_run(project, manifest["run_id"])[1] == manifest


def test_logs_only_derived_values_that_actually_change(tmp_path):
    project, run, manifest = _run(
        tmp_path,
        {"survey": "id,count\na,0\nb,7\nc,\n"},
        [
            _step(
                "normalize",
                "table.derive/1",
                ["survey"],
                "normalized",
                {
                    "expressions": {
                        "count": {
                            "when": {
                                "condition": {"column": "count", "op": "gt", "value": 0},
                                "then": {"literal": 0},
                                "otherwise": {"column": "count"},
                            }
                        }
                    }
                },
            )
        ],
        "normalized",
    )
    assert pl.read_parquet(run / "outputs" / "normalized.parquet")["count"].to_list() == [
        0,
        0,
        None,
    ]
    events = pl.read_parquet(run / "audit" / "value_changes.parquet")
    assert events.height == 1
    assert events["step_id"].to_list() == ["normalize"]
    assert events["input_column"].to_list() == ["count"]
    assert events["output_row_index"].to_list() == [1]
    assert json.loads(events["before_json"][0]) == {"dtype": "Int64", "value": 7}
    assert json.loads(events["after_json"][0]) == {"dtype": "Int64", "value": 0}
    assert _audit(run)["value_change_count"] == 1
    assert verified_run(project, manifest["run_id"])[1] == manifest


def test_null_to_zero_is_logged_but_original_zero_is_not(tmp_path):
    _, run, _ = _run(
        tmp_path,
        {"survey": "id,count\na,\nb,0\nc,7\n"},
        [
            _step(
                "fill",
                "table.derive/1",
                ["survey"],
                "filled",
                {
                    "expressions": {
                        "count": {
                            "when": {
                                "condition": {"column": "count", "op": "is_null", "value": None},
                                "then": {"literal": 0},
                                "otherwise": {"column": "count"},
                            }
                        }
                    }
                },
            )
        ],
        "filled",
    )
    events = pl.read_parquet(run / "audit" / "value_changes.parquet")
    assert events["output_row_index"].to_list() == [0]
    assert json.loads(events["before_json"][0])["value"] is None
    assert json.loads(events["after_json"][0])["value"] == 0


def test_multi_source_derived_values_are_described_once_by_mapping_rule(tmp_path):
    _, run, _ = _run(
        tmp_path,
        {"survey": "id,site\na,North\nb,South\n"},
        [
            _step(
                "display",
                "table.derive/1",
                ["survey"],
                "named",
                {
                    "expressions": {
                        "description": {
                            "concat": [
                                {"column": "id"},
                                {"literal": ":"},
                                {"column": "site"},
                            ]
                        }
                    }
                },
            )
        ],
        "named",
    )
    assert not (run / "audit" / "value_changes.parquet").exists()
    assert _audit(run)["step_audit"][0]["fields_without_direct_value_comparison"] == ["description"]


def test_distinct_removal_is_counted_without_doubling_cell_evidence(tmp_path):
    _, run, _ = _run(
        tmp_path,
        {"survey": "key,count\na,0\na,8\nb,9\n"},
        [
            _step(
                "unique",
                "table.distinct/1",
                ["survey"],
                "result",
                {"keys": ["key"]},
            )
        ],
        "result",
    )
    assert pl.read_parquet(run / "outputs" / "result.parquet")["count"].to_list() == [
        0,
        9,
    ]
    step = _audit(run)["step_audit"][0]
    assert step["input_rows"] == [3]
    assert step["output_rows"] == 2
    assert step["value_changes"] == 0
    assert not (run / "audit" / "value_changes.parquet").exists()


def test_forged_change_events_are_rejected_even_with_replaced_manifest_hash(tmp_path):
    project, run, manifest = _run(
        tmp_path,
        {"survey": "id,count\na,0\nb,7\n"},
        [
            _step(
                "zero",
                "table.derive/1",
                ["survey"],
                "result",
                {"expressions": {"count": {"literal": 0}}},
            )
        ],
        "result",
    )
    path = run / "audit" / "value_changes.parquet"
    changed = pl.read_parquet(path)
    changed.with_columns(pl.lit(999).alias("output_row_index")).write_parquet(path)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verified_run(project, manifest["run_id"])

    document = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    for artifact in document["artifacts"]:
        if artifact["path"] == "audit/value_changes.parquet":
            artifact["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            artifact["bytes"] = path.stat().st_size
    (run / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="value-change audit mismatch"):
        verified_run(project, manifest["run_id"])
