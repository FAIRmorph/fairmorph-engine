"""Exercise publication lifecycle independently of the optional Parquet backend.

These tests use a deliberately fake parquet adapter; a separate Polars test verifies
real Parquet/CSV interoperability when the dependency is installed in CI.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fairmorph_engine.core.csphoc import run_slice
from fairmorph_engine.core.export import export_data_package, verified_run, verify_project

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "cs-phoc"


class FakeFrame:
    def __init__(self, rows=None, schema=None):
        self.rows = rows or []
        self.schema = schema

    def write_parquet(self, path):
        Path(path).write_text(json.dumps(self.rows), encoding="utf-8")

    def write_csv(self, path):
        Path(path).write_text(
            "record_id\n" + "\n".join(str(row.get("record_id", "")) for row in self.rows) + "\n",
            encoding="utf-8",
        )


@pytest.fixture
def mock_parquet(monkeypatch):
    def read_parquet(path):
        return FakeFrame(rows=json.loads(Path(path).read_text(encoding="utf-8")))

    monkeypatch.setitem(
        sys.modules,
        "polars",
        SimpleNamespace(DataFrame=FakeFrame, read_parquet=read_parquet, Int64="i64", String="str"),
    )


def test_run_manifest_export_and_integrity_lifecycle(tmp_path, mock_parquet):
    project = tmp_path / "project.fairmorph"
    events = []

    def emit(event, **data):
        return events.append({"event": event, **data})

    run_slice(
        project,
        FIXTURE / "cs-phoc-events.csv",
        FIXTURE / "cs-phoc-counts.csv",
        FIXTURE / "decision.json",
        emit,
    )
    first = events[-1]["data"]
    assert first["output_rows"] == 16940
    assert first["explicit_zeros"] == 11599
    assert verify_project(project)["completed_runs"] == 1
    first_run = first["run_id"]
    run_dir, _ = verified_run(project, first_run)
    first_manifest = (run_dir / "manifest.json").read_bytes()
    export_data_package(project, first_run, emit)
    assert events[-1]["status"] == "success"
    assert verify_project(project)["exports"] == 1
    assert (run_dir / "manifest.json").read_bytes() == first_manifest

    run_slice(
        project,
        FIXTURE / "cs-phoc-events.csv",
        FIXTURE / "cs-phoc-counts.csv",
        FIXTURE / "decision.json",
        emit,
    )
    assert verify_project(project)["completed_runs"] == 2
    assert len(list((project / "objects").rglob("*"))) > 0
    assert (
        len(
            list(
                (project / "objects").rglob(
                    "be4a28aa5036dea103e9e6bbc6af5fef13d80354ef2750e0960bf78e320c3545"
                )
            )
        )
        == 1
    )
    assert (run_dir / "manifest.json").read_bytes() == first_manifest

    package_file = next((project / "exports").glob("*/package/observations.csv"))
    package_file.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="modified export artifact"):
        verify_project(project)


def test_failure_does_not_publish_completed_run(tmp_path, mock_parquet, monkeypatch):
    project = tmp_path / "project.fairmorph"
    original = FakeFrame.write_parquet

    def fail_write(self, path):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(FakeFrame, "write_parquet", fail_write)
    with pytest.raises(OSError, match="simulated disk failure"):
        run_slice(
            project,
            FIXTURE / "cs-phoc-events.csv",
            FIXTURE / "cs-phoc-counts.csv",
            FIXTURE / "decision.json",
            lambda *args, **kwargs: None,
        )
    assert list((project / "runs").glob(".pending-*/FAILED"))
    assert verify_project(project)["completed_runs"] == 0
    monkeypatch.setattr(FakeFrame, "write_parquet", original)


def test_existing_configuration_tampering_is_rejected(tmp_path, mock_parquet):
    import hashlib

    from fairmorph_engine.core.csphoc import canonical_bytes

    project = tmp_path / "project.fairmorph"
    decision = FIXTURE / "decision.json"
    run_slice(
        project,
        FIXTURE / "cs-phoc-events.csv",
        FIXTURE / "cs-phoc-counts.csv",
        decision,
        lambda *args, **kwargs: None,
    )
    config_hash = hashlib.sha256(canonical_bytes(json.loads(decision.read_text()))).hexdigest()
    stored = project / "configurations" / config_hash / "approval.json"
    stored.write_text('{"status":"suggested"}', encoding="utf-8")
    with pytest.raises(ValueError, match="approval has changed"):
        run_slice(
            project,
            FIXTURE / "cs-phoc-events.csv",
            FIXTURE / "cs-phoc-counts.csv",
            decision,
            lambda *args, **kwargs: None,
        )
    assert verify_project(project)["completed_runs"] == 1
