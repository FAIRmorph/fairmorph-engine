"""Real reference-data vertical slice through the generic, reviewed CLI workflow."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fairmorph_engine.cli import app


def _result(runner, *args):
    response = runner.invoke(app, list(args))
    assert response.exit_code == 0, response.stdout
    events = [json.loads(line) for line in response.stdout.splitlines() if line.startswith("{")]
    result = next(event for event in reversed(events) if event["event"] == "result")
    assert result["status"] == "success", result
    return result["data"]


def test_csphoc_generic_reference_vertical_slice(tmp_path):
    pytest.importorskip("polars")
    example = Path(__file__).resolve().parents[1]
    project = tmp_path / "reference-project"
    runner = CliRunner()
    _result(runner, "init-project", "--project", str(project), "--name", "Reference")
    counts = _result(
        runner,
        "import-resource",
        "--project",
        str(project),
        "--source",
        str(example / "cs-phoc-counts.csv"),
        "--role",
        "counts",
    )
    events = _result(
        runner,
        "import-resource",
        "--project",
        str(project),
        "--source",
        str(example / "cs-phoc-events.csv"),
        "--role",
        "events",
    )
    profile = json.loads((example / "mapping-profile.json").read_text(encoding="utf-8"))
    profile["auxiliary_resource_ids"] = [events["resource_id"]]
    profile["relationships"] = [
        {
            "relationship_id": "count-event",
            "left_resource_id": counts["resource_id"],
            "left_column": "event_id",
            "right_resource_id": events["resource_id"],
            "right_column": "event_id",
            "cardinality": "many-to-one",
        }
    ]
    profile_path = tmp_path / "reviewed-profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    staged = _result(
        runner,
        "stage-csv-mapping",
        "--project",
        str(project),
        "--resource-id",
        counts["resource_id"],
        "--profile",
        str(profile_path),
    )
    assert staged["status"] == "draft"
    _result(
        runner,
        "approve-mapping",
        "--project",
        str(project),
        "--mapping-sha256",
        staged["mapping_sha256"],
        "--reviewer",
        "reference-reviewer",
    )
    run = _result(
        runner,
        "run-mapping",
        "--project",
        str(project),
        "--mapping-sha256",
        staged["mapping_sha256"],
    )
    assert run["output_rows"] == 16940
    snapshot = json.loads(
        (project / "runs" / run["run_id"] / "inputs.snapshot.json").read_text(encoding="utf-8")
    )
    assert len(snapshot["sources"]) == 2
    assert snapshot["mapping_snapshot"]["relationships"][0]["relationship_id"] == "count-event"
    exported = _result(
        runner, "export-package", "--project", str(project), "--run-id", run["run_id"]
    )
    descriptor = json.loads(
        (
            project / "exports" / exported["export_id"] / "package" / "datapackage.json"
        ).read_text(encoding="utf-8")
    )
    assert descriptor["name"] == "fairmorph-run"
    verified = _result(runner, "verify-project", "--project", str(project))
    assert verified["completed_runs"] == 1
