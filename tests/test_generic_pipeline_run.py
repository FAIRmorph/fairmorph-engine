"""Real generic pipeline through project selection, CLI, RUN/2 and verification."""

import json

import polars as pl
import pytest
from typer.testing import CliRunner

from fairmorph_engine.cli import app
from fairmorph_engine.core.export import verified_run, verify_project
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline


def configuration(resource_id):
    return {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {"survey": {"resource_id": resource_id, "format": "csv"}},
        "steps": [
            {"id": "select", "operator": "table.select/1", "inputs": ["survey"],
             "output": "result", "parameters": {"columns": ["event", "count"]}}
        ],
        "outputs": ["result"],
    }


def test_generic_dag_end_to_end_without_runtime_config(tmp_path):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    source = tmp_path / "survey.csv"
    source.write_text("event,count\ne1,0\ne2,7\n", encoding="utf-8")
    resource = import_resource(project, source, "survey")
    config = configuration(resource["resource_id"])
    checksum = register_pipeline(project, config)["pipeline_sha256"]
    select_project_pipeline(project, checksum)
    result = CliRunner().invoke(app, ["run-pipeline", "--project", str(project)])
    assert result.exit_code == 0, result.output
    run_id = json.loads(result.output.strip().splitlines()[-1])["data"]["run_id"]
    run_dir, manifest = verified_run(project, run_id)
    assert manifest["transformation_version"] == "fairmorph.pipeline/1"
    assert pl.read_parquet(run_dir / "outputs" / "result.parquet")["count"].to_list() == [0, 7]
    assert verify_project(project)["completed_runs"] == 1
    assert json.loads((run_dir / "inputs.snapshot.json").read_text())["sources"][0]["sha256"] == resource["sha256"]


def test_pipeline_rejects_source_tampering_before_run(tmp_path):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    source = tmp_path / "survey.csv"
    source.write_text("event,count\ne1,1\n", encoding="utf-8")
    resource = import_resource(project, source, "survey")
    sha = register_pipeline(project, configuration(resource["resource_id"]))["pipeline_sha256"]
    select_project_pipeline(project, sha)
    (project / resource["object_path"]).write_text("event,count\ne1,999\n")
    with pytest.raises(ValueError, match="modified"):
        execute_project_run(project)
    assert not list((project / "runs").iterdir())


def test_pipeline_rejects_configuration_tampering_and_unregistered_source(tmp_path):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    with pytest.raises(ValueError, match="Resource not imported"):
        select_project_pipeline(
            project, register_pipeline(project, configuration("nonexistent"))["pipeline_sha256"]
        )
    source = tmp_path / "survey.csv"
    source.write_text("event,count\ne1,1\n", encoding="utf-8")
    resource = import_resource(project, source, "survey")
    sha = register_pipeline(project, configuration(resource["resource_id"]))["pipeline_sha256"]
    select_project_pipeline(project, sha)
    path = project / "configurations" / "pipelines" / f"{sha}.json"
    path.write_text(path.read_text().replace("result", "altered"), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        execute_project_run(project)


def test_pipeline_rejects_undeclared_outputs(tmp_path):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    config = configuration("resource-placeholder")
    config["outputs"] = ["missing"]
    with pytest.raises(ValueError, match="produced"):
        register_pipeline(project, config)
