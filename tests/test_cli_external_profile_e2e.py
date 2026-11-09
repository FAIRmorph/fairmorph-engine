"""Exercise the public configuration-only workflow with an unrelated survey."""

import csv
import hashlib
import json

import pytest
from typer.testing import CliRunner

from fairmorph_engine.cli import app
from fairmorph_engine.core.publication_integrity import validate_publication_integrity


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
    _result(runner.invoke(app, ["init-project", "--project",
                str(project), "--name", "Survey"]))
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
    assert {item["path"] for item in descriptor["resources"]} == {
        "observations.csv",
        "lineage.csv",
        "quality.json",
    }
    package = project / "exports" / exported["export_id"] / "package"
    with (package / "observations.csv").open(encoding="utf-8", newline="") as stream:
        observations = list(csv.DictReader(stream))
    assert len(observations) == 3
    assert {row["source_column"] for row in observations} == {"juveniles", "adults"}
    assert sorted(int(row["value"]) for row in observations) == [0, 2, 3]
    with (package / "lineage.csv").open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) > 0
    assert "CS-PHOC" not in descriptor["title"]
    verified = _result(runner.invoke(app, ["verify-project", "--project", str(project)]))
    assert verified["completed_runs"] == 1


def test_generic_publication_integrity_against_real_verified_run(tmp_path):
    """No mocked RUN verification, project fixtures or publication defaults."""
    runner = CliRunner()
    project = tmp_path / "project"
    source = tmp_path / "source.csv"
    source.write_text("site,juveniles,adults\nA,0,2\nB,,3\n", encoding="utf-8")
    _result(runner.invoke(app, ["init-project", "--project", str(project)]))
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
    mapping = {
        "mapping_id": "survey",
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "identifier": "site",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": column,
                "target_field": column,
                "description": "Synthetic measurement",
                "definition_source": "source_documentation",
                "counting_unit": "individual",
                "zero_meaning": "true_zero",
                "missing_values": [],
            }
            for column in ("juveniles", "adults")
        ],
        "acceptance": {"output_rows": 3, "explicit_zeros": 1, "value_sum": 5},
    }
    mapping_file = tmp_path / "mapping.json"
    mapping_file.write_text(json.dumps(mapping), encoding="utf-8")
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
                str(mapping_file),
            ],
        )
    )
    _result(
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
    run = _result(
        runner.invoke(
            app,
            [
                "run-mapping", "--project",
                str(project),
                "--mapping-sha256",
                staged["mapping_sha256"],
            ],
        )
    )
    run_dir = project / "runs" / run["run_id"]
    pin = hashlib.sha256((run_dir / "manifest.json").read_bytes()).hexdigest()
    metadata = tmp_path / "metadata.json"
    metadata.write_text('{"title":"Synthetic survey"}', encoding="utf-8")
    profile = {
        "schema_version": "fairmorph.poc.publication-profile/1",
        "profile_id": "synthetic",
        "version": "1.0.0",
        "run_manifest_sha256": pin,
        "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
        "formats": ["dwca/1"],
        "dwca": {
            "core": "Occurrence",
            "core_id_field": "record_id",
            "core_fields": [
                {
                    "source_field": "record_id",
                    "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                }
            ],
        },
    }
    projection = {
        "schema_version": "fairmorph.poc.publication-projection/1",
        "run_manifest_sha256": pin,
        "tables": [
            {
                "row_type": "Occurrence",
                "artifact_path": "outputs/observations.parquet",
                "columns": ["record_id"],
            }
        ],
    }
    integrity = {
        "schema_version": "fairmorph.poc.publication-integrity/1",
        "run_manifest_sha256": pin,
        "identifiers": [{"row_type": "Occurrence", "column": "record_id"}],
        "relationships": [],
    }
    files = [tmp_path / name for name in ("publication.json", "projection.json", "integrity.json")]
    for path, document in zip(files, (profile, projection, integrity), strict=True):
        path.write_text(json.dumps(document), encoding="utf-8")
    result = validate_publication_integrity(
        project, run["run_id"], files[0], metadata, files[1], files[2]
    )
    assert result["integrity_verified"] is True
    assert result["publication_ready"] is False
