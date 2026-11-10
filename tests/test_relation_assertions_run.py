"""P0.4 vertical PoC: explicit typed relations, append-only revisions and RUN pins."""

import json
import sqlite3

import polars as pl
import pytest
from typer.testing import CliRunner

from fairmorph_engine.cli import app
from fairmorph_engine.core.entity_projection import confirm_projection
from fairmorph_engine.core.export import verified_run, verify_project
from fairmorph_engine.core.pipeline_run import register_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.project_execution import execute_project_run, select_project_pipeline
from fairmorph_engine.core.registry import define_field, review_field
from fairmorph_engine.core.relation_assertions import (
    assert_relation,
    relation_profile,
    relation_snapshot,
    replace_relation,
    retract_relation,
)


def _project(tmp_path, *, include_foreign_key=False):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    source = tmp_path / "survey.csv"
    source.write_text(
        "event,event_type,occurrence,measurement,measurement_type,count\n"
        "e1,point,o1,m1,count,0\n"
        "e2,point,o2,m2,count,4\n"
        "e3,point,o3,m3,count,6\n",
        encoding="utf-8",
    )
    resource = import_resource(project, source, "survey")
    rid = resource["resource_id"]
    pins = {}
    columns = ("event", "event_type", "occurrence", "measurement", "measurement_type", "count")
    for column in columns:
        definition = {
            "semantic_status": "defined",
            "definition_source": "user_confirmed",
            "description": f"Confirmed ecological field semantics for source column {column}.",
            "value_semantics": {
                "missing_values": [],
                "zero_meaning": "true_zero" if column == "count" else "not_applicable",
            },
        }
        if column == "count":
            definition["counting_unit"] = "individual"
        revision = define_field(project, rid, f"csv:{column}", definition)
        review_field(project, revision["revision_id"], "same-user", "approved")
        pins[column] = {
            "source_resource_id": rid,
            "source_field_id": revision["source_field_id"],
            "definition_revision_id": revision["revision_id"],
            "definition_sha256": revision["content_sha256"],
        }

    def binding(column):
        return {
            "column": column,
            "description": f"Explicit ecological target binding of source field {column}.",
            "source_definitions": [pins[column]],
        }

    occurrence_fields = {"entity_id": binding("occurrence")}
    if include_foreign_key:
        occurrence_fields["sampling_event_ref"] = binding("event")
    config = {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {"survey": {"resource_id": rid, "format": "csv"}},
        "steps": [
            {
                "id": "select",
                "operator": "table.select/1",
                "inputs": ["survey"],
                "output": "selected",
                "parameters": {"columns": list(columns)},
            }
        ],
        "outputs": ["selected"],
        "entities": {
            "SamplingEvent": {
                "source_table": "selected",
                "description": "Explicitly recorded ecological sampling event entity.",
                "fields": {
                    "entity_id": binding("event"),
                    "event_type": binding("event_type"),
                },
            },
            "Occurrence": {
                "source_table": "selected",
                "description": "Optional evidence entity confirmed by the user.",
                "fields": occurrence_fields,
            },
            "MeasurementOrFact": {
                "source_table": "selected",
                "description": "Explicit ecological measurement retaining numeric zeros.",
                "fields": {
                    "entity_id": binding("measurement"),
                    "measurement_type": binding("measurement_type"),
                    "value": binding("count"),
                },
            },
        },
    }
    sha = register_pipeline(project, config)["pipeline_sha256"]
    confirm_projection(project, sha, "same-user")
    select_project_pipeline(project, sha)
    return project, sha


def test_relations_are_pinned_and_old_run_survives_retraction(tmp_path):
    project, sha = _project(tmp_path)
    first = assert_relation(
        project, sha, "parent_event", "e2", "e1", "same-user", "fieldwork-note-1"
    )
    assert first["profile"]["sha256"] == relation_profile()["sha256"]
    assert first["source"]["kind"] == "user_confirmed"
    second = assert_relation(
        project, sha, "event_occurrence", "e1", "o1", "same-user", "fieldwork-note-2"
    )
    assert_relation(project, sha, "event_measurement", "e1", "m1", "same-user", "count-note")
    assert_relation(project, sha, "occurrence_measurement", "o1", "m1", "same-user", "count-note")
    assert len(relation_snapshot(project, sha)["active_assertions"]) == 4

    run_a = execute_project_run(project)
    dir_a, _ = verified_run(project, run_a["run_id"])
    saved = json.loads((dir_a / "inputs.snapshot.json").read_text(encoding="utf-8"))
    original = saved["relations_snapshot"]
    assert original["profile"]["version"] == "0.12-poc.1"
    assert original["snapshot_sha256"]
    assert len(original["active_assertions"]) == 4
    assert pl.read_parquet(dir_a / "outputs" / "measurementorfact.parquet")["value"].to_list() == [
        0,
        4,
        6,
    ]

    revoked = retract_relation(project, sha, second["relation_id"], "same-user", "correction")
    assert revoked["operation"] == "retract"
    assert revoked["supersedes_assertion_id"] == second["assertion_id"]
    with pytest.raises(ValueError, match="not active"):
        retract_relation(project, sha, second["relation_id"], "same-user", "again")
    current = relation_snapshot(project, sha)
    assert len(current["active_assertions"]) == 3
    assert current["snapshot_sha256"] != original["snapshot_sha256"]
    run_b = execute_project_run(project)
    dir_b, _ = verified_run(project, run_b["run_id"])
    assert (
        len(
            json.loads((dir_b / "inputs.snapshot.json").read_text())["relations_snapshot"][
                "active_assertions"
            ]
        )
        == 3
    )
    assert verified_run(project, run_a["run_id"])[1] == run_a
    assert (
        relation_snapshot(project, sha, through_sequence=original["through_sequence"]) == original
    )
    assert verify_project(project)["completed_runs"] == 2

    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute(
            "SELECT operation FROM relation_assertions WHERE relation_id=? ORDER BY sequence",
            (second["relation_id"],),
        ).fetchall() == [("assert",), ("retract",)]
        assert (
            db.execute(
                "SELECT assertion_id FROM current_relations WHERE relation_id=?",
                (second["relation_id"],),
            ).fetchone()
            is None
        )
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute(
                "DELETE FROM relation_assertions WHERE assertion_id=?", (first["assertion_id"],)
            )


def test_hierarchy_cycles_cardinality_and_replacements_are_transactional(tmp_path):
    project, sha = _project(tmp_path)
    a = assert_relation(project, sha, "parent_event", "e2", "e1", "u", "hierarchy")
    b = assert_relation(project, sha, "parent_event", "e3", "e2", "u", "hierarchy")
    prior = relation_snapshot(project, sha)
    with pytest.raises(ValueError, match="Cyclic parent_event"):
        replace_relation(project, sha, a["relation_id"], "e3", "u", "mistake")
    with pytest.raises(ValueError, match="cardinality"):
        assert_relation(project, sha, "parent_event", "e2", "e3", "u", "mistake")
    assert relation_snapshot(project, sha) == prior

    swapped = replace_relation(project, sha, b["relation_id"], "e1", "u", "correction")
    assert swapped["operation"] == "replace"
    assert swapped["supersedes_assertion_id"] == b["assertion_id"]
    assert swapped["relation_id"] == b["relation_id"]
    assert relation_snapshot(project, sha)["active_assertions"][1]["assertion"][
        "object_entity_id"
    ] in {"e1", "e2"}

    assert_relation(project, sha, "event_occurrence", "e1", "o1", "u", "note")
    with pytest.raises(ValueError, match="cardinality"):
        assert_relation(project, sha, "event_occurrence", "e2", "o1", "u", "other")
    # Multiple different Occurrences may belong to the same Event.
    assert_relation(project, sha, "event_occurrence", "e1", "o2", "u", "note")


def test_missing_entity_predicate_identity_and_confirmed_mapping_conflicts(tmp_path):
    project, sha = _project(tmp_path, include_foreign_key=True)
    with pytest.raises(ValueError, match="existing projected entity"):
        assert_relation(project, sha, "event_occurrence", "e404", "o1", "u", "source")
    with pytest.raises(ValueError, match="Predicate"):
        assert_relation(project, sha, "magic_relation", "e1", "o1", "u", "source")
    with pytest.raises(ValueError, match="confirming user"):
        assert_relation(project, sha, "event_occurrence", "e1", "o1", "", "source")
    with pytest.raises(ValueError, match="source reference"):
        assert_relation(project, sha, "event_occurrence", "e1", "o1", "u", "")
    with pytest.raises(ValueError, match="confirmed entity field mapping"):
        assert_relation(project, sha, "event_occurrence", "e2", "o1", "u", "source")
    assert relation_snapshot(project, sha)["active_assertions"] == []


def test_cli_assert_and_show_explicit_user_relation(tmp_path):
    project, sha = _project(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "assert-relation",
            "--project",
            str(project),
            "--pipeline-sha256",
            sha,
            "--predicate",
            "parent_event",
            "--subject-id",
            "e2",
            "--object-id",
            "e1",
            "--confirmed-by",
            "same-user",
            "--source-reference",
            "field-note-42",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip().splitlines()[-1])["data"]
    assert data["review"]["confirmed_by"] == "same-user"
    response = CliRunner().invoke(
        app, ["show-relations", "--project", str(project), "--pipeline-sha256", sha]
    )
    assert response.exit_code == 0, response.output
    assert (
        len(json.loads(response.output.strip().splitlines()[-1])["data"]["active_assertions"]) == 1
    )



def test_valid_time_offsets_and_source_class_do_not_replace_user_confirmation(tmp_path):
    project, sha = _project(tmp_path)
    approved = assert_relation(
        project,
        sha,
        "parent_event",
        "e2",
        "e1",
        "same-user",
        "track-suggestion-1",
        source_kind="suggested",
        valid_from="2026-11-07T23:00:00+02:00",
        valid_to="2026-11-07T22:00:00Z",
    )
    assert approved["source"]["kind"] == "suggested"
    assert approved["review"]["status"] == "approved"
    assert approved["review"]["confirmed_by"] == "same-user"
    assert approved["recorded_at"] != approved["valid_time"]["valid_from"]
    with pytest.raises(ValueError, match="valid_from must precede valid_to"):
        assert_relation(
            project,
            sha,
            "parent_event",
            "e3",
            "e1",
            "same-user",
            "bad-interval",
            valid_from="2026-11-07T22:00:00Z",
            valid_to="2026-11-07T23:00:00+02:00",
        )
    assert len(relation_snapshot(project, sha)["active_assertions"]) == 1
