"""Fault injection at generic RUN publication and recovery boundaries."""

import json
import sqlite3

import pytest

from fairmorph_engine.core.export import verify_project
from fairmorph_engine.core.run_recovery import reconcile_runs
from fairmorph_engine.core import run_executor
from test_generic_run_executor import _approve, _prepare


def _catalog_ids(project):
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        return {row[0] for row in db.execute("SELECT run_id FROM runs")}


def _index_ids(project):
    return json.loads((project / "project.json").read_text(encoding="utf-8"))["run_ids"]


@pytest.mark.parametrize("boundary", ["publish_directory", "publish_index"])
def test_io_fault_rolls_back_publication_and_preserves_pending(
    tmp_path, monkeypatch, boundary
):
    pytest.importorskip("polars")
    project, _, _, draft = _prepare(tmp_path)
    _approve(project, draft)
    original = run_executor.os.replace

    def interrupted(source, target):
        source_name = source.name
        if boundary == "publish_directory" and source_name.startswith(".pending-"):
            raise OSError("injected directory publication failure")
        if boundary == "publish_index" and source_name.startswith(".project."):
            raise OSError("injected project index publication failure")
        return original(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(run_executor.os, "replace", interrupted)
        with pytest.raises(OSError, match="injected"):
            run_executor.execute_mapping_run(project, draft["sha256"])

    assert _index_ids(project) == []
    assert _catalog_ids(project) == set()
    assert not [p for p in (project / "runs").iterdir() if not p.name.startswith(".pending-")]
    assert len(list((project / "runs").glob(".pending-*/FAILED"))) == 1
    assert reconcile_runs(project)["recovered"] == []
    assert verify_project(project)["completed_runs"] == 0


@pytest.mark.parametrize("boundary", ["directory_only", "index_only", "catalog_only"])
def test_crash_boundary_reconciles_all_indexes(tmp_path, boundary):
    pytest.importorskip("polars")
    project, _, _, draft = _prepare(tmp_path)
    _approve(project, draft)
    run_id = run_executor.execute_mapping_run(project, draft["sha256"])["run_id"]

    # Simulate process termination after publishing the immutable RUN directory,
    # but before one or both independent indexes became durable.
    if boundary in ("directory_only", "catalog_only"):
        with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
            db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
    if boundary in ("directory_only", "index_only"):
        path = project / "project.json"
        index = json.loads(path.read_text(encoding="utf-8"))
        index["run_ids"] = []
        path.write_text(json.dumps(index), encoding="utf-8")

    result = reconcile_runs(project)
    assert result["recovered"] == [run_id]
    assert _catalog_ids(project) == {run_id}
    assert _index_ids(project) == [run_id]
    assert verify_project(project)["completed_runs"] == 1
    assert reconcile_runs(project)["recovered"] == []


def test_recovery_index_replace_failure_rolls_back_catalog(tmp_path, monkeypatch):
    pytest.importorskip("polars")
    project, _, _, draft = _prepare(tmp_path)
    _approve(project, draft)
    run_id = run_executor.execute_mapping_run(project, draft["sha256"])["run_id"]
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
    index_path = project / "project.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["run_ids"] = []
    index_path.write_text(json.dumps(index), encoding="utf-8")

    from fairmorph_engine.core import run_recovery

    original = run_recovery.os.replace

    def fail_recovery(source, target):
        if source.name.endswith(".recovery"):
            raise OSError("injected recovery index failure")
        return original(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(run_recovery.os, "replace", fail_recovery)
        with pytest.raises(OSError, match="injected"):
            reconcile_runs(project)

    assert _catalog_ids(project) == set()
    assert _index_ids(project) == []
    assert reconcile_runs(project)["recovered"] == [run_id]
    assert verify_project(project)["completed_runs"] == 1


def test_recovery_rejects_missing_indexed_run_without_deleting_reference(tmp_path):
    pytest.importorskip("polars")
    project, _, _, draft = _prepare(tmp_path)
    _approve(project, draft)
    run_id = run_executor.execute_mapping_run(project, draft["sha256"])["run_id"]
    (project / "runs" / run_id / "manifest.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        reconcile_runs(project)
    assert _catalog_ids(project) == {run_id}
    assert _index_ids(project) == [run_id]
