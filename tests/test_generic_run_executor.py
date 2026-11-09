"""Generic v0.12 RUN regression: no scientific fixture is installed or inferred."""

import json
import sqlite3
import sys
import types

import pytest

from fairmorph_engine.core.registry import (
    approve_mapping,
    define_field,
    mapping_snapshot,
    register_mapping,
    review_field,
)
from fairmorph_engine.core.run_executor import execute_mapping_run


def _prepare(tmp_path):
    # Use the public project and import API, not a CS-PHOC fixture or test shim.
    from fairmorph_engine.core.project import import_resource, initialize_project

    project = tmp_path / "generic.fairmorph"
    initialize_project(project, "Independent survey")
    source = tmp_path / "observations.csv"
    source.write_bytes(b"station,juvenile,adult\na,0,2\nb,,3\n")
    resource = import_resource(project, source, "measurements")
    bindings = []
    for col in ("juvenile", "adult"):
        revision = define_field(
            project,
            resource["resource_id"],
            f"csv:{col}",
            {
                "description": f"Number of counted individuals in {col} category",
                "semantic_status": "defined",
                "definition_source": "source_documentation",
                "counting_unit": "individual",
                "value_semantics": {"missing_values": [], "zero_meaning": "true_zero"},
            },
        )
        review_field(project, revision["revision_id"], "scientific-reviewer", "approved")
        bindings.append(
            {
                "source_field_id": revision["source_field_id"],
                "definition_revision_id": revision["revision_id"],
                "source_column": col,
                "target_field": col,
            }
        )
    mapping = {
        "mapping_id": "survey-counts",
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_resource_id": resource["resource_id"],
        "identifier": "station",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "bindings": bindings,
    }
    approved = register_mapping(project, mapping)
    return project, resource, mapping, approved


def _approve(project, approved):
    approve_mapping(project, approved["sha256"], "scientific-reviewer")


def test_run_rejects_draft_mapping_before_creating_run(tmp_path):
    project, _, _, draft = _prepare(tmp_path)
    with pytest.raises(ValueError, match="approved"):
        execute_mapping_run(project, draft["sha256"])
    assert list((project / "runs").iterdir()) == []


def test_run_rejects_modified_original_object_before_creating_run(tmp_path):
    project, resource, _, draft = _prepare(tmp_path)
    _approve(project, draft)
    (project / resource["object_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="modified immutable source"):
        execute_mapping_run(project, draft["sha256"])
    assert list((project / "runs").iterdir()) == []


def test_run_rejects_undeclared_or_ambiguous_mapping_columns(tmp_path):
    project, _, mapping, draft = _prepare(tmp_path)
    _approve(project, draft)
    changed = {**mapping, "version": "1.0.1"}
    changed["bindings"] = [{**mapping["bindings"][0], "source_column": "undeclared"}]
    new = register_mapping(project, changed)
    approve_mapping(project, new["sha256"], "scientific-reviewer")
    with pytest.raises(ValueError, match="corresponding approved field"):
        execute_mapping_run(project, new["sha256"])


def test_reviewed_mapping_produces_immutable_run_and_verify(tmp_path):
    pl = pytest.importorskip("polars")
    from fairmorph_engine.core.export import verified_run, verify_project

    project, resource, _, draft = _prepare(tmp_path)
    _approve(project, draft)
    result = execute_mapping_run(project, draft["sha256"])
    run = project / "runs" / result["run_id"]
    assert (run / "manifest.json").is_file()
    frame = pl.read_parquet(run / "outputs" / "observations.parquet")
    assert frame.height == 3
    assert sum(frame["value"]) == 5
    assert sum(v == 0 for v in frame["value"]) == 1
    assert mapping_snapshot(project, draft["sha256"])["mapping_sha256"] == draft["sha256"]
    assert verify_project(project)["completed_runs"] == 1
    assert verified_run(project, result["run_id"])[1] == result
    snapshot = json.loads((run / "inputs.snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["sources"][0]["sha256"] == resource["sha256"]
    (run / "outputs" / "observations.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="RUN artifact|Checksum"):
        verified_run(project, result["run_id"])


def test_failed_processing_is_not_published(tmp_path, monkeypatch):
    """Failure preserves pending diagnostics and publishes no completed RUN."""
    from fairmorph_engine.core import run_executor

    project, _, _, draft = _prepare(tmp_path)
    _approve(project, draft)
    # Validate failure handling independently of optional installed Polars.
    class FakeFrame:
        def __init__(self, rows):
            self.rows = rows
        def select(self, *columns):
            return self
        def write_parquet(self, path):
            raise OSError("disk failure")
    monkeypatch.setitem(sys.modules, "polars", types.SimpleNamespace(DataFrame=FakeFrame))
    with pytest.raises(OSError, match="disk failure"):
        run_executor.execute_mapping_run(project, draft["sha256"])
    pending = list((project / "runs").glob(".pending-*/FAILED"))
    assert len(pending) == 1
    assert json.loads((project / "project.json").read_text(encoding="utf-8"))["run_ids"] == []
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_generic_run_publication_with_fake_parquet_writer(tmp_path, monkeypatch):
    """Exercise the lifecycle even when the local runner lacks Polars."""
    from fairmorph_engine.core.export import verified_run, verify_project

    project, _, _, draft = _prepare(tmp_path)
    _approve(project, draft)

    class FakeFrame:
        def __init__(self, rows):
            self.rows = rows

        def select(self, *columns):
            return FakeFrame([{column: row[column] for column in columns} for row in self.rows])

        def write_parquet(self, path):
            path.write_text(json.dumps(self.rows, sort_keys=True), encoding="utf-8")

    monkeypatch.setitem(sys.modules, "polars", types.SimpleNamespace(DataFrame=FakeFrame))
    result = execute_mapping_run(project, draft["sha256"])
    path = project / "runs" / result["run_id"]
    rows = json.loads((path / "outputs" / "observations.parquet").read_text(encoding="utf-8"))
    assert len(rows) == 3
    assert [x["value"] for x in rows] == [0, 2, 3]
    assert len({x["record_id"] for x in rows}) == 3
    assert verified_run(project, result["run_id"])[1] == result
    assert verify_project(project)["completed_runs"] == 1
    assert not list((project / "runs").glob(".pending-*"))
    # JSON objects remain immutable even if a caller alters its approved mapping.
    (path / "configuration.snapshot.json").write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="RUN artifact|Checksum"):
        verified_run(project, result["run_id"])
