"""Framework v0.12 regression: separate technical import and approved semantics."""

import sqlite3

import pytest

from fairmorph_engine.core.registry import (
    approve_mapping,
    define_field,
    mapping_snapshot,
    register_mapping,
    review_field,
)


def test_unresolved_import_is_allowed_but_semantic_mapping_is_gated(tmp_path):
    from fairmorph_engine.core.project import import_resource, initialize_project

    project = tmp_path / "p.fairmorph"
    initialize_project(project)
    source = tmp_path / "observations.csv"
    source.write_text("count\n0\n", encoding="utf-8")
    resource = import_resource(project, source, "table")
    field = define_field(project, resource["resource_id"], "csv:count",
                         {"description": None, "semantic_status": "unresolved",
                          "definition_source": "unknown"})
    assert field["status"] == "unresolved"
    with pytest.raises(ValueError, match="description"):
        review_field(project, field["revision_id"], "scientist", "approved")
    mapping = {"mapping_id": "count", "version": "1.0.0", "bindings": [
        {"source_field_id": field["source_field_id"],
         "definition_revision_id": field["revision_id"], "target_field": "individualCount"}
    ]}
    draft = register_mapping(project, mapping)
    assert draft["status"] == "draft"
    with pytest.raises(ValueError, match="approved mapping"):
        mapping_snapshot(project, draft["sha256"])
    with pytest.raises(ValueError, match="approved field"):
        draft2 = register_mapping(project, {**mapping, "version": "1.0.1"})
        approve_mapping(project, draft2["sha256"], "scientist")


def test_approved_revision_pins_are_immutable(tmp_path):
    from fairmorph_engine.core.project import import_resource, initialize_project

    project = tmp_path / "p.fairmorph"
    initialize_project(project)
    source = tmp_path / "counts.csv"
    source.write_text("count\n0\n3\n", encoding="utf-8")
    imported = import_resource(project, source, "table")
    first = define_field(project, imported["resource_id"], "csv:count",
                         {"description": "Number of animals counted",
                          "semantic_status": "defined",
                          "value_semantics": {"missing_values": [], "zero_meaning": "true_zero"},
                          "definition_source": "source_documentation", "counting_unit": "individual"})
    review_field(project, first["revision_id"], "publisher", "approved")
    mapping = {"mapping_id": "animals", "version": "1.0.0", "bindings": [
        {"source_field_id": first["source_field_id"],
         "definition_revision_id": first["revision_id"], "target_field": "individualCount"}
    ]}
    registered = register_mapping(project, mapping)
    approve_mapping(project, registered["sha256"], "publisher")
    snapshot = mapping_snapshot(project, registered["sha256"])
    assert snapshot["field_definition_revisions"][0]["revision_id"] == first["revision_id"]
    assert len(snapshot["source_resources"]) == 1
    assert snapshot["source_resources"][0]["object_sha256"] == imported["sha256"]
    second = define_field(project, imported["resource_id"], "csv:count",
                          {"description": "Number of surveyed individuals",
                           "semantic_status": "defined",
                          "value_semantics": {"missing_values": [], "zero_meaning": "true_zero"},
                          "definition_source": "source_documentation", "counting_unit": "individual"},
                          parent_revision_id=first["revision_id"])
    assert second["revision_id"] != first["revision_id"]
    assert mapping_snapshot(project, registered["sha256"]) == snapshot
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM field_definition_revisions").fetchone()[0] == 2
    review_field(project, second["revision_id"], "publisher", "approved")
    revised = {**mapping, "bindings": [{"source_field_id": second["source_field_id"],
                "definition_revision_id": second["revision_id"],
                "target_field": "individualCount"}]}
    with pytest.raises(ValueError, match="immutable"):
        register_mapping(project, revised)


def test_mapping_rejects_other_resource_field_revision(tmp_path):
    from fairmorph_engine.core.project import import_resource, initialize_project

    project = tmp_path / "p.fairmorph"
    initialize_project(project)
    for role in ("a", "b"):
        path = tmp_path / f"{role}.csv"
        path.write_text("x\n1\n", encoding="utf-8")
        import_resource(project, path, role)
    resources = []
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        resources = [x[0] for x in db.execute("SELECT resource_id FROM source_resources ORDER BY resource_id")]
    field = define_field(project, resources[0], "csv:x",
                         {"description": "Valid individual count", "semantic_status": "defined",
                          "value_semantics": {"missing_values": [], "zero_meaning": "true_zero"}})
    other = define_field(project, resources[1], "csv:x",
                         {"description": "Unresolved", "semantic_status": "unresolved"})
    mapping = {"mapping_id": "m", "version": "1.0.0", "bindings": [
        {"source_field_id": other["source_field_id"],
         "definition_revision_id": field["revision_id"], "target_field": "count"}
    ]}
    with pytest.raises(ValueError, match="another source field"):
        register_mapping(project, mapping)
