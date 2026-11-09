"""Exercise the public configuration-only workflow with an unrelated survey."""

import hashlib
import json

import pytest
from typer.testing import CliRunner

from fairmorph_engine.cli import app


def _result(response):
    assert response.exit_code == 0, response.stdout
    events = [json.loads(line) for line in response.stdout.splitlines() if line.startswith("{")]
    result = next(event for event in reversed(events) if event["event"] == "result")
    assert result["status"] == "success", result
    return result["data"]


@pytest.mark.parametrize("counting_unit", ["individual", "sampling_event"])
def test_external_profile_cli_review_and_run(tmp_path, counting_unit):
    pytest.importorskip("polars")
    project = tmp_path / "survey-project"
    source = tmp_path / "survey.csv"
    source.write_text("station,juveniles,adults\nA,0,2\nB,,3\n", encoding="utf-8")
    auxiliary = tmp_path / "stations.csv"
    auxiliary.write_text("station,region\nA,north\nB,south\n", encoding="utf-8")
    runner = CliRunner()
    _result(runner.invoke(app, ["init-project", "--project", str(project), "--name", "Survey"]))
    imported = _result(
        runner.invoke(
            app,
            [
                "import-resource",
                "--project",
                str(project),
                "--source",
                str(source),
                "--role",
                "observations",
            ],
        )
    )
    auxiliary_import = _result(
        runner.invoke(
            app,
            [
                "import-resource",
                "--project",
                str(project),
                "--source",
                str(auxiliary),
                "--role",
                "stations",
            ],
        )
    )
    profile = {
        "mapping_id": "survey",
        "auxiliary_resource_ids": [auxiliary_import["resource_id"]],
        "relationships": [
            {
                "relationship_id": "survey-station",
                "left_resource_id": imported["resource_id"],
                "left_column": "station",
                "right_resource_id": auxiliary_import["resource_id"],
                "right_column": "station",
                "cardinality": "many-to-one",
            }
        ],
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "identifier": "station",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": column,
                "target_field": column,
                "description": f"Counted individuals in {column} category",
                "definition_source": "source_documentation",
                "counting_unit": counting_unit,
                "zero_meaning": "true_zero",
                "missing_values": [],
            }
            for column in ("juveniles", "adults")
        ],
        "acceptance": {"output_rows": 3, "explicit_zeros": 1, "value_sum": 5},
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    staged = _result(
        runner.invoke(
            app,
            [
                "stage-csv-mapping",
                "--project",
                str(project),
                "--resource-id",
                imported["resource_id"],
                "--profile",
                str(profile_path),
            ],
        )
    )
    assert staged["status"] == "draft"
    approved = _result(
        runner.invoke(
            app,
            [
                "approve-mapping",
                "--project",
                str(project),
                "--mapping-sha256",
                staged["mapping_sha256"],
                "--reviewer",
                "reviewer",
            ],
        )
    )
    assert approved["status"] == "approved"
    run = _result(
        runner.invoke(
            app,
            [
                "run-mapping",
                "--project",
                str(project),
                "--mapping-sha256",
                staged["mapping_sha256"],
            ],
        )
    )
    assert run["output_rows"] == 3
    inputs = json.loads(
        (project / "runs" / run["run_id"] / "inputs.snapshot.json").read_text(encoding="utf-8")
    )
    assert len(inputs["sources"]) == 2
    assert inputs["mapping_snapshot"]["relationships"][0]["relationship_id"] == "survey-station"
    exported = _result(
        runner.invoke(
            app,
            [
                "export-package",
                "--project",
                str(project),
                "--run-id",
                run["run_id"],
            ],
        )
    )
    descriptor = json.loads(
        (project / "exports" / exported["export_id"] / "package" / "datapackage.json").read_text(
            encoding="utf-8"
        )
    )
    assert descriptor["name"] == "fairmorph-run"
    assert "CS-PHOC" not in descriptor["title"]
    verified = _result(runner.invoke(app, ["verify-project", "--project", str(project)]))
    assert verified["completed_runs"] == 1
