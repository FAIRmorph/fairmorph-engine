"""P0.2 vertical PoC: pinned field semantics -> confirmation -> verified RUN/2."""

import json
import sqlite3

import polars as pl
import pytest

from fairmorph_engine.core.entity_projection import confirm_projection
from fairmorph_engine.core.export import verified_run, verify_project
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline
from fairmorph_engine.core.registry import define_field, review_field


def _setup(tmp_path, *, duplicate_events=False, confirm_fields=True):
    project = tmp_path / "project"
    initialize_project(project)
    data = tmp_path / "data.csv"
    event2 = "e1" if duplicate_events else "e2"
    data.write_text(
        f"obs,event,occ,count\no1,e1,x1,0\no2,{event2},x2,4\n",
        encoding="utf-8",
    )
    resource = import_resource(project, data, "survey")
    resource_id = resource["resource_id"]
    fields = {}
    for column in ("obs", "event", "occ", "count"):
        definition = {
            "semantic_status": "defined",
            "definition_source": "user_confirmed",
            "description": f"User-defined semantics for source column {column}.",
            "value_semantics": {
                "missing_values": [],
                "zero_meaning": "true_zero" if column == "count" else "not_applicable",
            },
        }
        if column == "count":
            definition["counting_unit"] = "individual"
        revision = define_field(project, resource_id, f"csv:{column}", definition)
        fields[column] = {
            "source_resource_id": resource_id,
            "source_field_id": revision["source_field_id"],
            "definition_revision_id": revision["revision_id"],
            "definition_sha256": revision["content_sha256"],
        }
        if confirm_fields:
            review_field(project, revision["revision_id"], "responsible-user", "approved")
    return project, resource_id, fields


def _binding(column, definitions):
    return {
        "column": column,
        "description": f"Explicitly configured target semantics for {column}.",
        "source_definitions": [definitions[column]],
    }


def _config(resource_id, definitions, *, event_only=False):
    entities = {
        "Event": {
            "source_table": "normalized",
            "description": "Explicitly defined and confirmed sampling event.",
            "fields": {
                "eventID": _binding("event", definitions),
            },
        }
    }
    if not event_only:
        entities.update(
            {
                "Observation": {
                    "source_table": "normalized",
                    "description": "Explicit user-confirmed observation metadata.",
                    "fields": {
                        "observationID": _binding("obs", definitions),
                        "eventID": _binding("event", definitions),
                    },
                },
                "Occurrence": {
                    "source_table": "normalized",
                    "description": "Explicit user decision to model each evidence record.",
                    "fields": {
                        "occurrenceID": _binding("occ", definitions),
                        "eventID": _binding("event", definitions),
                    },
                },
                "MeasurementOrFact": {
                    "source_table": "normalized",
                    "description": "User-confirmed measured individual count values.",
                    "fields": {
                        "measurementID": _binding("obs", definitions),
                        "eventID": _binding("event", definitions),
                        "value": _binding("count", definitions),
                    },
                },
            }
        )
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
        "entities": entities,
    }


def test_confirmed_entities_materialize_into_verified_run(tmp_path):
    project, resource_id, definitions = _setup(tmp_path)
    sha = register_pipeline(project, _config(resource_id, definitions))["pipeline_sha256"]
    with pytest.raises(ValueError, match="confirmation"):
        select_project_pipeline(project, sha)
    confirmed = confirm_projection(project, sha, "responsible-user")
    assert confirmed["confirmed_by"] == "responsible-user"
    assert len(confirmed["evidence"]["field_definitions"]) == 4
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute(
            "SELECT confirmed_by FROM projection_confirmations WHERE configuration_sha256=?",
            (sha,),
        ).fetchone() == ("responsible-user",)
    with pytest.raises(ValueError, match="already confirmed"):
        confirm_projection(project, sha, "responsible-user")
    select_project_pipeline(project, sha)
    manifest = execute_project_run(project)
    run_dir, _ = verified_run(project, manifest["run_id"])
    assert pl.read_parquet(run_dir / "outputs" / "event.parquet").height == 2
    assert pl.read_parquet(run_dir / "outputs" / "occurrence.parquet").height == 2
    assert pl.read_parquet(run_dir / "outputs" / "measurementorfact.parquet")[
        "value"
    ].to_list() == [0, 4]
    snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["projection_confirmation"]["confirmed_by"] == "responsible-user"
    assert snapshot["projection_confirmation"]["evidence_sha256"] == confirmed["evidence_sha256"]
    assert verify_project(project)["completed_runs"] == 1


def test_event_only_is_valid_without_occurrence(tmp_path):
    project, resource_id, definitions = _setup(tmp_path)
    sha = register_pipeline(project, _config(resource_id, definitions, event_only=True))[
        "pipeline_sha256"
    ]
    confirm_projection(project, sha, "responsible-user")
    select_project_pipeline(project, sha)
    manifest = execute_project_run(project)
    run_dir, _ = verified_run(project, manifest["run_id"])
    assert (run_dir / "outputs" / "event.parquet").is_file()
    assert not (run_dir / "outputs" / "occurrence.parquet").exists()


def test_unconfirmed_field_blocks_projection(tmp_path):
    project, resource_id, definitions = _setup(tmp_path, confirm_fields=False)
    sha = register_pipeline(project, _config(resource_id, definitions))["pipeline_sha256"]
    with pytest.raises(ValueError, match="SourceFieldDefinition requires"):
        confirm_projection(project, sha, "responsible-user")


def test_wrong_field_revision_pin_blocks_projection(tmp_path):
    project, resource_id, definitions = _setup(tmp_path)
    definitions["event"]["definition_sha256"] = "0" * 64
    sha = register_pipeline(project, _config(resource_id, definitions))["pipeline_sha256"]
    with pytest.raises(ValueError, match="identity or hash"):
        confirm_projection(project, sha, "responsible-user")


def test_duplicate_event_rejected_without_publication(tmp_path):
    project, resource_id, definitions = _setup(tmp_path, duplicate_events=True)
    sha = register_pipeline(project, _config(resource_id, definitions))["pipeline_sha256"]
    confirm_projection(project, sha, "responsible-user")
    select_project_pipeline(project, sha)
    with pytest.raises(ValueError, match="Event eventID"):
        execute_project_run(project)
    assert not list((project / "runs").iterdir())


def test_missing_semantic_entity_contract_rejected(tmp_path):
    project, resource_id, definitions = _setup(tmp_path)
    config = _config(resource_id, definitions)
    del config["entities"]["Event"]["fields"]["eventID"]["source_definitions"]
    with pytest.raises(ValueError, match="explicit field contract"):
        register_pipeline(project, config)
