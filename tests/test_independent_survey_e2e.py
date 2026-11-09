"""Dataset-independent end-to-end acceptance through the public CLI."""

import hashlib
import json

import pytest
from typer.testing import CliRunner

from fairmorph_engine.cli import app


def _cli(*args):
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == 0, result.stdout
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    event = next(item for item in reversed(events) if item["event"] == "result")
    assert event["status"] == "success"
    return event["data"]


def test_independent_survey_full_lifecycle(tmp_path):
    pl = pytest.importorskip("polars")
    source = tmp_path / "survey.csv"
    source.write_text("sample,small,large\nS1,0,4\nS2,,7\n", encoding="utf-8")
    profile = {
        "mapping_id": "independent-survey",
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "identifier": "sample",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": column,
                "target_field": column,
                "description": "Observed count of specimens in category " + column,
                "definition_source": "source_documentation",
                "counting_unit": "specimen",
                "zero_meaning": "true_zero",
                "missing_values": [{"token": "", "meaning": "not recorded"}],
            }
            for column in ("small", "large")
        ],
        "acceptance": {"output_rows": 3, "explicit_zeros": 1, "value_sum": 11},
    }
    profile_path = tmp_path / "mapping.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    project = tmp_path / "survey-project"
    _cli("init-project", "--project", str(project), "--name", "Independent survey")
    imported = _cli(
        "import-resource", "--project", str(project), "--source", str(source),
        "--role", "measurements",
    )
    staged = _cli(
        "stage-csv-mapping", "--project", str(project), "--resource-id",
        imported["resource_id"], "--profile", str(profile_path),
    )
    _cli(
        "approve-mapping", "--project", str(project), "--mapping-sha256",
        staged["mapping_sha256"], "--reviewer", "survey-reviewer",
    )
    run = _cli(
        "run-mapping", "--project", str(project), "--mapping-sha256",
        staged["mapping_sha256"],
    )
    run_dir = project / "runs" / run["run_id"]
    assert json.loads((run_dir / "manifest.json").read_text())["schema_version"] == (
        "fairmorph.poc.run/2"
    )
    rows = pl.read_parquet(run_dir / "outputs" / "observations.parquet")
    assert rows.height == 3
    assert sorted(rows["value"].to_list()) == [0, 4, 7]
    assert pl.read_parquet(run_dir / "audit" / "lineage.parquet").height == 3
    exported = _cli("export-package", "--project", str(project), "--run-id", run["run_id"])
    assert (
        project / "exports" / exported["export_id"] / "package" / "datapackage.json"
    ).is_file()
    assert _cli("verify-project", "--project", str(project))["completed_runs"] == 1
