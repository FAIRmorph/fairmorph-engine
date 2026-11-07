"""Regression checks for immutable project/RUN/export contracts."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fairmorph_engine.core.csphoc import EXPECTED_SOURCE_HASHES, run_slice, sha256
from fairmorph_engine.core.export import dwca_profile, verified_run

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "cs-phoc"


def test_source_hashes_match_approved_fixtures():
    assert sha256(FIXTURE / "cs-phoc-events.csv") == EXPECTED_SOURCE_HASHES["events"]
    assert sha256(FIXTURE / "cs-phoc-counts.csv") == EXPECTED_SOURCE_HASHES["counts"]


def test_tampered_source_rejected_before_project_is_created(tmp_path):
    tampered = tmp_path / "counts.csv"
    tampered.write_bytes((FIXTURE / "cs-phoc-counts.csv").read_bytes() + b"\n")
    project = tmp_path / "project.fairmorph"
    with pytest.raises(ValueError, match="approved reference"):
        run_slice(
            project,
            FIXTURE / "cs-phoc-events.csv",
            tampered,
            FIXTURE / "decision.json",
            lambda *args, **kwargs: None,
        )
    assert not project.exists()


def test_dwca_published_profile_is_explicit():
    profile = dwca_profile()
    assert profile["core_rows"] == 536
    assert profile["extension_rows"] == 16940
    assert profile["zero_status"] == "absent"


def test_dwca_preflight_reports_ndjson_profile():
    result = subprocess.run(
        [sys.executable, "-m", "fairmorph_engine.cli", "dwca-preflight"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    doc = json.loads(result.stdout.splitlines()[-1])
    assert doc["status"] == "success"
    assert doc["data"]["extension_rows"] == 16940


def test_export_rejects_invalid_run_path(tmp_path):
    with pytest.raises(ValueError, match="RUN identifier"):
        verified_run(tmp_path, "../../outside")


def test_end_to_end_project_run_export_and_tamper_detection(tmp_path):
    pl = pytest.importorskip("polars")
    from fairmorph_engine.core.export import export_data_package

    project = tmp_path / "CS-PHOC.fairmorph"
    events = []

    def emit(event, **payload):
        return events.append({"event": event, **payload})

    run_slice(
        project,
        FIXTURE / "cs-phoc-events.csv",
        FIXTURE / "cs-phoc-counts.csv",
        FIXTURE / "decision.json",
        emit,
    )
    summary = events[-1]["data"]
    assert events[-1]["status"] == "success"
    assert summary["output_rows"] == 16940
    run_id = summary["run_id"]
    run_path, manifest = verified_run(project, run_id)
    assert pl.read_parquet(run_path / "outputs" / "observations.parquet").height == 16940
    assert pl.read_parquet(run_path / "audit" / "lineage.parquet").height == 16940
    assert pl.read_parquet(run_path / "audit" / "findings.parquet").height == 0
    before = {f: sha256(run_path / f) for f in ["manifest.json", "outputs/observations.parquet"]}

    export_data_package(project, run_id, emit)
    first = events[-1]["data"]
    package = Path(first["export_path"]) / "package"
    assert sum(1 for _ in package.joinpath("observations.csv").open(encoding="utf-8")) == 16941
    assert (
        json.loads((package / "datapackage.json").read_text(encoding="utf-8"))["profile"]
        == "data-package"
    )
    assert {f: sha256(run_path / f) for f in before} == before

    export_data_package(project, run_id, emit)
    assert events[-1]["data"]["export_id"] != first["export_id"]
    assert {f: sha256(run_path / f) for f in before} == before

    with (run_path / "outputs" / "observations.parquet").open("ab") as f:
        f.write(b"tampered")
    with pytest.raises(ValueError, match="modified RUN artifact"):
        verified_run(project, run_id)
