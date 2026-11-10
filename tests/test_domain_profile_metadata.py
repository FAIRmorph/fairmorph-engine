"""P0.5 vertical PoC: versioned profile validation and optional metadata envelopes."""

import json
import sqlite3

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from fairmorph_engine.cli import app
from fairmorph_engine.core.domain_profiles import (
    install_builtin_profiles,
    profile_bindings_for,
    profile_bundle,
    validate_attributes,
)
from fairmorph_engine.core.entity_projection import confirm_projection
from fairmorph_engine.core.export import verified_run, verify_project
from fairmorph_engine.core.metadata_revisions import (
    metadata_snapshot,
    register_metadata_revision,
)
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline
from fairmorph_engine.core.registry import define_field, review_field
from fairmorph_engine.core.schema_registry import get_schema, register_schema


def _setup(tmp_path, *, install=True):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    file = tmp_path / "survey.csv"
    file.write_text(
        "event,event_type,measurement,measurement_type,count\n"
        "e1,point_count,m1,count,0\n"
        "e2,point_count,m2,count,4\n",
        encoding="utf-8",
    )
    imported = import_resource(project, file, "survey")
    pins = {}
    columns = ["event", "event_type", "measurement", "measurement_type", "count"]
    for column in columns:
        definition = {
            "semantic_status": "defined",
            "definition_source": "user_confirmed",
            "description": f"Explicitly defined ecological field {column} in this survey.",
            "value_semantics": {
                "missing_values": [],
                "zero_meaning": "true_zero" if column == "count" else "not_applicable",
            },
        }
        if column == "count":
            definition["counting_unit"] = "individual"
        registered = define_field(project, imported["resource_id"], f"csv:{column}", definition)
        review_field(project, registered["revision_id"], "owner", "approved")
        pins[column] = {
            "source_resource_id": imported["resource_id"],
            "source_field_id": registered["source_field_id"],
            "definition_revision_id": registered["revision_id"],
            "definition_sha256": registered["content_sha256"],
        }

    def binding(column):
        return {
            "column": column,
            "description": f"Approved target binding to declared field {column}.",
            "source_definitions": [pins[column]],
        }

    config = {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {"survey": {"resource_id": imported["resource_id"], "format": "csv"}},
        "steps": [
            {
                "id": "select",
                "operator": "table.select/1",
                "inputs": ["survey"],
                "output": "normalized",
                "parameters": {"columns": columns},
            }
        ],
        "outputs": ["normalized"],
        "entities": {
            "SamplingEvent": {
                "source_table": "normalized",
                "description": "Explicitly recorded generic ecological sampling event.",
                "fields": {
                    "entity_id": binding("event"),
                    "event_type": binding("event_type"),
                },
            },
            "MeasurementOrFact": {
                "source_table": "normalized",
                "description": "User-defined measurement with explicit zero semantics.",
                "fields": {
                    "entity_id": binding("measurement"),
                    "measurement_type": binding("measurement_type"),
                    "value": binding("count"),
                },
            },
        },
    }
    if install:
        install_builtin_profiles(project, "owner")
        config["profile_bindings"] = profile_bindings_for(
            project, ["SamplingEvent", "MeasurementOrFact"]
        )
    return project, config


def _confirmed(project, config):
    sha = register_pipeline(project, config)["pipeline_sha256"]
    confirm_projection(project, sha, "owner")
    select_project_pipeline(project, sha)
    return sha


def _provenance(*names):
    return {
        f"/attributes/{name}": {
            "source_type": "user_confirmed",
            "source_ref": "original-fieldbook",
        }
        for name in names
    }


def test_semantic_projection_requires_profiles_without_legacy_fallback(tmp_path):
    project, config = _setup(tmp_path, install=False)
    with pytest.raises(ValueError, match="require explicit approved P0.5 profile bindings"):
        register_pipeline(project, config)

    config["profile_bindings"] = {
        "envelope": {
            "schema_id": "https://fairmorph.org/schemas/v0.8/metadata-envelope.schema.json",
            "schema_version": "0.8.0",
            "schema_sha256": "0" * 64,
        },
        "entities": {},
    }
    with pytest.raises(ValueError, match="cover every selected entity"):
        register_pipeline(project, config)


def test_v012_profile_bundle_is_valid_and_is_installed_by_explicit_user(tmp_path):
    project, config = _setup(tmp_path)
    bundle = profile_bundle()
    assert len(bundle["domains"]) == 8
    for schema in [*bundle["domains"].values(), bundle["envelope"]]:
        Draft202012Validator.check_schema(schema)
        version = "0.8.0"
        registered, checksum = get_schema(project, schema_id=schema["$id"], schema_version=version)
        assert checksum
        assert registered == schema
    assert config["profile_bindings"]["entities"]["SamplingEvent"]["schema_version"] == "0.8.0"

    with pytest.raises(ValueError, match="confirming user"):
        install_builtin_profiles(project, "")


def test_approved_profiles_and_metadata_are_pinned_without_cell_duplication(tmp_path):
    project, config = _setup(tmp_path)
    sha = _confirmed(project, config)
    first = register_metadata_revision(
        project,
        sha,
        entity_type="SamplingEvent",
        entity_id="e1",
        attributes={"event_type": "point_count", "remarks": "User checked the event"},
        field_provenance=_provenance("event_type", "remarks"),
        source="user_confirmed",
        confirmed_by="owner",
    )
    assert first["approved_by"] == "owner"
    first_run = execute_project_run(project)
    run_dir, _ = verified_run(project, first_run["run_id"])
    snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text())
    assert snapshot["profile_bindings"] == config["profile_bindings"]
    frozen = snapshot["metadata_snapshot"]
    assert len(frozen["active_revisions"]) == 1
    assert frozen["active_revisions"][0]["metadata_revision_id"] == first["metadata_revision_id"]
    assert frozen["schema_pins"]["envelope"]["schema_sha256"]
    assert "audit/lineage.parquet" not in {item["path"] for item in first_run["artifacts"]}
    assert not (run_dir / "audit" / "value_changes.parquet").exists()

    with pytest.raises(ValueError, match="current parent"):
        register_metadata_revision(
            project,
            sha,
            entity_type="SamplingEvent",
            entity_id="e1",
            attributes={"event_type": "point_count"},
            field_provenance=_provenance("event_type"),
            source="user_confirmed",
            confirmed_by="owner",
        )
    updated = register_metadata_revision(
        project,
        sha,
        entity_type="SamplingEvent",
        entity_id="e1",
        attributes={"event_type": "point_count", "remarks": "Updated review evidence"},
        field_provenance=_provenance("event_type", "remarks"),
        source="user_confirmed",
        confirmed_by="owner",
        parent_revision_id=first["metadata_revision_id"],
    )
    assert updated["parent_revision_id"] == first["metadata_revision_id"]
    assert metadata_snapshot(project, sha)["snapshot_sha256"] != frozen["snapshot_sha256"]

    second_run = execute_project_run(project)
    verified_run(project, second_run["run_id"])
    assert verified_run(project, first_run["run_id"])[1] == first_run
    assert metadata_snapshot(project, sha, through_sequence=frozen["through_sequence"]) == frozen
    assert verify_project(project)["completed_runs"] == 2
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute(
                "DELETE FROM metadata_revisions WHERE metadata_revision_id=?",
                (first["metadata_revision_id"],),
            )


def test_invalid_values_provenance_and_schema_pin_are_blocked(tmp_path):
    project, config = _setup(tmp_path)
    wrong = json.loads(json.dumps(config))
    wrong["profile_bindings"]["entities"]["SamplingEvent"]["schema_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 pin"):
        register_pipeline(project, wrong)
    wrong = json.loads(json.dumps(config))
    wrong["entities"]["SamplingEvent"]["fields"]["unknown_flag"] = {
        **wrong["entities"]["SamplingEvent"]["fields"]["event_type"],
    }
    sha = _confirmed(project, wrong)
    with pytest.raises(ValueError, match="profile validation"):
        execute_project_run(project)  # unknown target field is rejected by profile

    # A separate valid pipeline still allows metadata validation failures to be exercised.
    sha = _confirmed(project, config)
    with pytest.raises(ValueError, match="field_provenance"):
        register_metadata_revision(
            project,
            sha,
            entity_type="SamplingEvent",
            entity_id="e1",
            attributes={"event_type": "point_count"},
            field_provenance={},
            source="user_confirmed",
            confirmed_by="owner",
        )
    with pytest.raises(ValueError, match="does not exist in confirmed projection"):
        register_metadata_revision(
            project,
            sha,
            entity_type="SamplingEvent",
            entity_id="nonexistent",
            attributes={"event_type": "point_count"},
            field_provenance=_provenance("event_type"),
            source="user_confirmed",
            confirmed_by="owner",
        )
    with pytest.raises(ValueError, match="minimum|profile validation"):
        register_metadata_revision(
            project,
            sha,
            entity_type="MeasurementOrFact",
            entity_id="m1",
            attributes={"measurement_type": "count", "value": 0, "uncertainty": -2},
            field_provenance=_provenance("measurement_type", "value", "uncertainty"),
            source="user_confirmed",
            confirmed_by="owner",
        )
    assert metadata_snapshot(project, sha)["active_revisions"] == []


def test_later_approved_schema_version_does_not_reinterpret_old_run(tmp_path):
    project, config = _setup(tmp_path)
    _confirmed(project, config)
    run = execute_project_run(project)
    original = profile_bundle()["domains"]["SamplingEvent"]
    new_schema = json.loads(json.dumps(original))
    new_schema["properties"]["extra_method_note"] = {"type": ["string", "null"]}
    registered = register_schema(
        project,
        schema_id=original["$id"],
        schema_version="0.9.0",
        schema=new_schema,
        kind="domain",
        status="approved",
        reviewer="owner",
    )
    assert (
        registered["schema_sha256"]
        != config["profile_bindings"]["entities"]["SamplingEvent"]["schema_sha256"]
    )
    assert verified_run(project, run["run_id"])[1] == run
    with pytest.raises(ValueError, match="immutable"):
        register_schema(
            project,
            schema_id=original["$id"],
            schema_version="0.8.0",
            schema=new_schema,
            kind="domain",
            status="approved",
            reviewer="owner",
        )


def test_general_v012_profile_rules_without_global_taxon_or_transect_requirements():
    schemas = profile_bundle()["domains"]
    validate_attributes(
        schemas["SamplingEvent"], {"event_type": "sensor_interval"}, context="event"
    )
    validate_attributes(schemas["Occurrence"], {}, context="occurrence")
    validate_attributes(schemas["Sample"], {}, context="sample")
    validate_attributes(schemas["Transect"], {}, context="transect")
    validate_attributes(
        schemas["MeasurementOrFact"],
        {"measurement_type": "count", "value": 0},
        context="zero",
    )
    with pytest.raises(ValueError, match="profile validation"):
        validate_attributes(
            schemas["MeasurementOrFact"],
            {"measurement_type": "count", "value": 7, "uncertainty": -0.1},
            context="negative uncertainty",
        )
    with pytest.raises(ValueError, match="start must precede end"):
        validate_attributes(
            schemas["SamplingEvent"],
            {
                "event_type": "sensor_interval",
                "event_time": {"start": "2026-11-10T16:00:00Z", "end": "2026-11-10T15:00:00Z"},
            },
            context="backwards time",
        )
    with pytest.raises(ValueError, match="profile validation"):
        validate_attributes(
            schemas["MediaAsset"],
            {
                "file_object_hash": "invalid",
                "media_type": "image/jpeg",
                "original_filename": "a.jpg",
            },
            context="bad file hash",
        )


def test_cli_profile_install_and_binding_template(tmp_path):
    project, _ = _setup(tmp_path, install=False)
    runner = CliRunner()
    install = runner.invoke(
        app, ["install-profile-contracts", "--project", str(project), "--confirmed-by", "owner"]
    )
    assert install.exit_code == 0, install.output
    show = runner.invoke(
        app,
        [
            "profile-bindings",
            "--project",
            str(project),
            "--entities",
            "SamplingEvent,MeasurementOrFact",
        ],
    )
    assert show.exit_code == 0, show.output
    pins = json.loads(show.output.splitlines()[-1])["data"]
    assert set(pins["entities"]) == {"SamplingEvent", "MeasurementOrFact"}
