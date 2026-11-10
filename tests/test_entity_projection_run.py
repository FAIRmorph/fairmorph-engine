"""P0.2 PoC: confirmed SourceFieldDefinitions -> SamplingEvent/RUN/2."""

import json
import sqlite3

import polars as pl
import pytest

from fairmorph_engine.core.domain_profiles import install_builtin_profiles, profile_bindings_for
from fairmorph_engine.core.entity_projection import confirm_projection
from fairmorph_engine.core.export import verified_run, verify_project
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline
from fairmorph_engine.core.registry import define_field, review_field


def _setup(tmp_path, *, duplicate_events=False, confirm_fields=True):
    project = tmp_path / "project"
    initialize_project(project)
    install_builtin_profiles(project, "responsible-user")
    source = tmp_path / "source.csv"
    event2 = "e1" if duplicate_events else "e2"
    source.write_text(
        "obs,event,occ,count,event_type,measurement_type\n"
        "o1,e1,x1,0,point_count,individual_count\n"
        f"o2,{event2},x2,4,point_count,individual_count\n",
        encoding="utf-8",
    )
    resource = import_resource(project, source, "survey")
    resource_id = resource["resource_id"]
    pins = {}
    for column in ("obs", "event", "occ", "count", "event_type", "measurement_type"):
        definition = {
            "semantic_status": "defined",
            "definition_source": "user_confirmed",
            "description": f"Documented source-field meaning for {column} in survey.",
            "value_semantics": {
                "missing_values": [],
                "zero_meaning": "true_zero" if column == "count" else "not_applicable",
            },
        }
        if column == "count":
            definition["counting_unit"] = "individual"
        revision = define_field(project, resource_id, f"csv:{column}", definition)
        pins[column] = {
            "source_resource_id": resource_id,
            "source_field_id": revision["source_field_id"],
            "definition_revision_id": revision["revision_id"],
            "definition_sha256": revision["content_sha256"],
        }
        if confirm_fields:
            review_field(project, revision["revision_id"], "responsible-user", "approved")
    return project, resource_id, pins


def _binding(column, pins):
    return {
        "column": column,
        "description": f"User-confirmed semantic interpretation of {column}.",
        "source_definitions": [pins[column]],
    }


def _config(project, resource_id, pins, *, event_only=False):
    entities = {
        "SamplingEvent": {
            "source_table": "normalized",
            "description": "User-defined general ecological sampling event.",
            "fields": {
                "entity_id": _binding("event", pins),
                "event_type": _binding("event_type", pins),
            },
        }
    }
    if not event_only:
        entities.update(
            {
                "Occurrence": {
                    "source_table": "normalized",
                    "description": "Explicitly user-configured occurrence relation.",
                    "fields": {
                        "entity_id": _binding("occ", pins),
                        "sampling_event_ref": _binding("event", pins),
                    },
                },
                "MeasurementOrFact": {
                    "source_table": "normalized",
                    "description": "Explicitly documented measurement of counts.",
                    "fields": {
                        "entity_id": _binding("obs", pins),
                        "sampling_event_ref": _binding("event", pins),
                        "measurement_type": _binding("measurement_type", pins),
                        "value": _binding("count", pins),
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
                "parameters": {
                    "columns": [
                        "obs",
                        "event",
                        "occ",
                        "count",
                        "event_type",
                        "measurement_type",
                    ]
                },
            }
        ],
        "outputs": ["normalized"],
        "entities": entities,
        "profile_bindings": profile_bindings_for(project, list(entities)),
    }


def test_entity_vertical_slice_pins_fields_and_verifies_run(tmp_path):
    project, resource_id, pins = _setup(tmp_path)
    sha = register_pipeline(project, _config(project, resource_id, pins))["pipeline_sha256"]
    with pytest.raises(ValueError, match="confirmation"):
        select_project_pipeline(project, sha)
    confirmation = confirm_projection(project, sha, "responsible-user")
    assert confirmation["confirmed_by"] == "responsible-user"
    assert len(confirmation["evidence"]["field_definitions"]) == 6
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
    assert pl.read_parquet(run_dir / "outputs" / "samplingevent.parquet").height == 2
    assert pl.read_parquet(run_dir / "outputs" / "occurrence.parquet").height == 2
    assert pl.read_parquet(run_dir / "outputs" / "measurementorfact.parquet")[
        "value"
    ].to_list() == [0, 4]
    snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["projection_confirmation"]["confirmed_by"] == "responsible-user"
    assert snapshot["projection_confirmation"]["evidence_sha256"] == confirmation["evidence_sha256"]
    # Projection only renames explicitly bound values: no per-cell copies are audited.
    audit = json.loads((run_dir / "audit" / "pipeline.json").read_text(encoding="utf-8"))
    assert audit["value_change_count"] == 0
    assert not (run_dir / "audit" / "value_changes.parquet").exists()
    assert verify_project(project)["completed_runs"] == 1


def test_event_only_run_does_not_require_occurrence(tmp_path):
    project, resource_id, pins = _setup(tmp_path)
    sha = register_pipeline(project, _config(project, resource_id, pins, event_only=True))["pipeline_sha256"]
    confirm_projection(project, sha, "responsible-user")
    select_project_pipeline(project, sha)
    manifest = execute_project_run(project)
    run_dir, _ = verified_run(project, manifest["run_id"])
    assert (run_dir / "outputs" / "samplingevent.parquet").is_file()
    assert not (run_dir / "outputs" / "occurrence.parquet").exists()


def test_unconfirmed_field_blocks_projection(tmp_path):
    project, resource_id, pins = _setup(tmp_path, confirm_fields=False)
    sha = register_pipeline(project, _config(project, resource_id, pins))["pipeline_sha256"]
    with pytest.raises(ValueError, match="SourceFieldDefinition requires"):
        confirm_projection(project, sha, "responsible-user")


def test_incorrect_field_revision_pin_blocks_confirmation(tmp_path):
    project, resource_id, pins = _setup(tmp_path)
    pins["event"]["definition_sha256"] = "0" * 64
    sha = register_pipeline(project, _config(project, resource_id, pins))["pipeline_sha256"]
    with pytest.raises(ValueError, match="identity or hash"):
        confirm_projection(project, sha, "responsible-user")


def test_duplicate_sampling_event_rejected_before_run(tmp_path):
    project, resource_id, pins = _setup(tmp_path, duplicate_events=True)
    sha = register_pipeline(project, _config(project, resource_id, pins))["pipeline_sha256"]
    confirm_projection(project, sha, "responsible-user")
    select_project_pipeline(project, sha)
    with pytest.raises(ValueError, match="SamplingEvent entity_id"):
        execute_project_run(project)
    assert not list((project / "runs").iterdir())


def test_incomplete_field_mapping_rejected(tmp_path):
    project, resource_id, pins = _setup(tmp_path)
    config = _config(project, resource_id, pins)
    del config["entities"]["SamplingEvent"]["fields"]["entity_id"]["source_definitions"]
    with pytest.raises(ValueError, match="explicit field contract"):
        register_pipeline(project, config)
