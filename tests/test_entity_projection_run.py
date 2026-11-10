"""P0.2 explicit approved entity projection through public RUN/2."""

import json

import polars as pl
import pytest

from fairmorph_engine.core.entity_projection import approve_projection
from fairmorph_engine.core.export import verified_run, verify_project
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline


def make_config(resource_id):
    return {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {"survey": {"resource_id": resource_id, "format": "csv"}},
        "steps": [
            {
                "id": "select",
                "operator": "table.select/1",
                "inputs": ["survey"],
                "output": "normalized",
                "parameters": {"columns": ["obs", "event", "occ", "count"]},
            }
        ],
        "outputs": ["normalized"],
        "entities": {
            "Observation": {
                "source_table": "normalized",
                "description": "Explicitly reviewed source observation identities.",
                "fields": {"observationID": "obs", "eventID": "event", "individualCount": "count"},
            },
            "Event": {
                "source_table": "normalized",
                "description": "Explicitly reviewed event identifiers and metadata.",
                "fields": {"eventID": "event"},
            },
            "Occurrence": {
                "source_table": "normalized",
                "description": "Explicitly reviewed occurrence identities and event references.",
                "fields": {"occurrenceID": "occ", "eventID": "event"},
            },
        },
    }


def test_approved_entities_materialize_into_verified_run(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "data.csv"
    source.write_text("obs,event,occ,count\no1,e1,x1,0\no2,e2,x2,4\n", encoding="utf-8")
    resource = import_resource(project, source, "survey")
    sha = register_pipeline(project, make_config(resource["resource_id"]))["pipeline_sha256"]
    with pytest.raises(ValueError, match="approval"):
        select_project_pipeline(project, sha)
    approve_projection(project, sha, "scientific-reviewer")
    select_project_pipeline(project, sha)
    manifest = execute_project_run(project)
    run_dir, _ = verified_run(project, manifest["run_id"])
    assert pl.read_parquet(run_dir / "outputs" / "observation.parquet")["individualCount"].to_list() == [0, 4]
    assert pl.read_parquet(run_dir / "outputs" / "event.parquet").height == 2
    assert pl.read_parquet(run_dir / "outputs" / "occurrence.parquet").height == 2
    snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text())
    assert snapshot["projection_approval"]["reviewer"] == "scientific-reviewer"
    assert verify_project(project)["completed_runs"] == 1


def test_orphan_event_reference_rejected_before_publication(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "data.csv"
    source.write_text("obs,event,occ,count\no1,e1,x1,0\no2,e1,x2,4\n", encoding="utf-8")
    resource = import_resource(project, source, "survey")
    sha = register_pipeline(project, make_config(resource["resource_id"]))["pipeline_sha256"]
    approve_projection(project, sha, "scientific-reviewer")
    select_project_pipeline(project, sha)
    with pytest.raises(ValueError, match="Event identifiers"):
        execute_project_run(project)
    assert not list((project / "runs").iterdir())


def test_missing_entity_mapping_rejected(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    config = make_config("source")
    del config["entities"]["Occurrence"]
    with pytest.raises(ValueError, match="Observation, Event and Occurrence"):
        register_pipeline(project, config)
