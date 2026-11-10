"""P0.3 vertical evidence: original source cells through the allowlisted DAG."""

import hashlib
import json

import polars as pl
import pytest

from fairmorph_engine.core.export import verified_run
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline


def _execute(project, definition):
    sha = register_pipeline(project, definition)["pipeline_sha256"]
    select_project_pipeline(project, sha)
    manifest = execute_project_run(project)
    directory, _ = verified_run(project, manifest["run_id"])
    return directory, manifest


def _trace(tmp_path):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    survey = tmp_path / "survey.csv"
    survey.write_text(
        "station,keep,count\na,1,0\nb,0,4\nc,1,7\n",
        encoding="utf-8",
    )
    lookup = tmp_path / "lookup.csv"
    lookup.write_text(
        "station,label\na,Alpha\nb,Beta\nc,Gamma\n",
        encoding="utf-8",
    )
    left = import_resource(project, survey, "survey")
    right = import_resource(project, lookup, "lookup")
    definition = {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {
            "survey": {"resource_id": left["resource_id"], "format": "csv"},
            "lookup": {"resource_id": right["resource_id"], "format": "csv"},
        },
        "steps": [
            {
                "id": "filter",
                "operator": "table.filter/1",
                "inputs": ["survey"],
                "output": "selected",
                "parameters": {
                    "predicate": {"column": "keep", "op": "eq", "value": 1}
                },
            },
            {
                "id": "join",
                "operator": "table.join/1",
                "inputs": ["selected", "lookup"],
                "output": "enriched",
                "parameters": {
                    "keys": ["station"],
                    "cardinality": "m:1",
                    "require_match": True,
                },
            },
            {
                "id": "derive",
                "operator": "table.derive/1",
                "inputs": ["enriched"],
                "output": "derived",
                "parameters": {
                    "expressions": {
                        "display": {
                            "concat": [
                                {"column": "label"},
                                {"literal": ":"},
                                {"column": "station"},
                            ]
                        },
                        "flag": {
                            "when": {
                                "condition": {
                                    "column": "count",
                                    "op": "gt",
                                    "value": 0,
                                },
                                "then": {"column": "count"},
                                "otherwise": {"literal": 0},
                            }
                        },
                    }
                },
            },
            {
                "id": "unpivot",
                "operator": "table.unpivot/1",
                "inputs": ["derived"],
                "output": "long",
                "parameters": {
                    "columns": ["count", "flag"],
                    "identifiers": ["station", "label", "display"],
                    "variable": "variable",
                    "value": "value",
                },
            },
        ],
        "outputs": ["long"],
    }
    return project, left, right, definition


def _cell(lines, table, row, column):
    return lines.filter(
        (pl.col("output_table") == table)
        & (pl.col("output_row_index") == row)
        & (pl.col("output_column") == column)
        & (pl.col("lineage_type") == "cell")
    )


def test_join_unpivot_and_derive_retain_exact_source_cells(tmp_path):
    project, left, right, config = _trace(tmp_path)
    run, manifest = _execute(project, config)
    assert any(
        item["path"] == "audit/lineage.parquet" for item in manifest["artifacts"]
    )
    result = pl.read_parquet(run / "outputs" / "long.parquet")
    assert result["value"].to_list().count(0) == 2
    assert result["value"].to_list().count(7) == 2

    lines = pl.read_parquet(run / "audit" / "lineage.parquet")
    rows = result.with_row_index("idx").filter(
        (pl.col("station") == "a") & (pl.col("variable") == "count")
    )
    row = rows["idx"][0]
    count = _cell(lines, "long", row, "value")
    assert count["source_resource_id"].to_list() == [left["resource_id"]]
    assert count["source_object_sha256"].to_list() == [left["sha256"]]
    assert count["source_row_index"].to_list() == [0]
    assert count["source_column"].to_list() == ["count"]
    assert count["source_kind"].to_list() == ["data_cell"]

    label = _cell(lines, "long", row, "label")
    assert label["source_resource_id"].to_list() == [right["resource_id"]]
    assert label["source_column"].to_list() == ["label"]

    display = _cell(lines, "long", row, "display")
    assert set(display["source_resource_id"].to_list()) == {
        left["resource_id"],
        right["resource_id"],
    }
    variable = _cell(lines, "long", row, "variable")
    assert variable["source_kind"].to_list() == ["column_header"]
    assert variable["source_row_index"].to_list() == [None]

    records = lines.filter(
        (pl.col("output_table") == "long")
        & (pl.col("output_row_index") == row)
        & (pl.col("lineage_type") == "record")
    )
    assert set(zip(
        records["source_resource_id"].to_list(),
        records["source_row_index"].to_list(),
        strict=True,
    )) == {(left["resource_id"], 0), (right["resource_id"], 0)}


def test_distinct_pins_first_surviving_source_row(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "items.csv"
    source.write_text("key,value\na,0\na,8\nb,9\n", encoding="utf-8")
    imported = import_resource(project, source, "items")
    config = {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {
            "items": {"resource_id": imported["resource_id"], "format": "csv"}
        },
        "steps": [
            {
                "id": "unique",
                "operator": "table.distinct/1",
                "inputs": ["items"],
                "output": "result",
                "parameters": {"keys": ["key"]},
            }
        ],
        "outputs": ["result"],
    }
    run, _ = _execute(project, config)
    assert pl.read_parquet(run / "outputs" / "result.parquet")["value"].to_list() == [0, 9]
    lines = pl.read_parquet(run / "audit" / "lineage.parquet")
    rows = lines.filter(pl.col("lineage_type") == "record")
    assert rows["source_row_index"].to_list() == [0, 2]


def test_lineage_hash_and_semantic_verification_reject_forgery(tmp_path):
    project, _, _, config = _trace(tmp_path)
    run, manifest = _execute(project, config)
    path = run / "audit" / "lineage.parquet"
    frame = pl.read_parquet(path)
    frame = frame.with_columns(
        pl.when(pl.col("source_row_index").is_not_null())
        .then(pl.lit(98765))
        .otherwise(pl.col("source_row_index"))
        .alias("source_row_index")
    )
    frame.write_parquet(path)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verified_run(project, manifest["run_id"])

    # A forged, internally consistent checksum is still not valid source provenance.
    doc = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    for artifact in doc["artifacts"]:
        if artifact["path"] == "audit/lineage.parquet":
            artifact["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            artifact["bytes"] = path.stat().st_size
    (run / "manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="source-cell lineage mismatch"):
        verified_run(project, manifest["run_id"])


def test_unmatched_join_has_no_fictitious_right_source(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    left_path = tmp_path / "left.csv"
    left_path.write_text("id,value\na,0\nb,3\n", encoding="utf-8")
    right_path = tmp_path / "right.csv"
    right_path.write_text("id,label\na,Alpha\n", encoding="utf-8")
    left = import_resource(project, left_path, "left")
    right = import_resource(project, right_path, "right")
    config = {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {
            "left": {"resource_id": left["resource_id"], "format": "csv"},
            "right": {"resource_id": right["resource_id"], "format": "csv"},
        },
        "steps": [
            {
                "id": "join",
                "operator": "table.join/1",
                "inputs": ["left", "right"],
                "output": "joined",
                "parameters": {
                    "keys": ["id"],
                    "cardinality": "m:1",
                    "require_match": False,
                },
            }
        ],
        "outputs": ["joined"],
    }
    run, _ = _execute(project, config)
    output = pl.read_parquet(run / "outputs" / "joined.parquet")
    assert output["label"].to_list() == ["Alpha", None]
    lines = pl.read_parquet(run / "audit" / "lineage.parquet")
    records = lines.filter(
        (pl.col("output_row_index") == 1)
        & (pl.col("lineage_type") == "record")
    )
    assert records["source_resource_id"].to_list() == [left["resource_id"]]
    label = _cell(lines, "joined", 1, "label")
    assert label["source_kind"].to_list() == ["derived"]
