import pytest

from fairmorph_engine.core.schema_registry import get_schema, register_schema


def _project(tmp_path):
    from fairmorph_engine.core.project import initialize_project

    project = tmp_path / "registry.fairmorph"
    initialize_project(project)
    return project


def test_new_profile_does_not_need_catalog_migration(tmp_path):
    project = _project(tmp_path)
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
              "$id": "https://fairmorph.org/schema/observations", "type": "object",
              "properties": {"n": {"type": "integer"}}}
    result = register_schema(project, schema_id=schema["$id"], schema_version="1.0.0",
                             kind="source", schema=schema)
    restored, checksum = get_schema(project, schema_id=schema["$id"], schema_version="1.0.0")
    assert restored == schema
    assert checksum == result["schema_sha256"]
    with pytest.raises(ValueError, match="immutable"):
        register_schema(project, schema_id=schema["$id"], schema_version="1.0.0",
                        kind="source", schema={**schema, "description": "changed"})


def test_unreviewed_remote_schema_reference_is_rejected(tmp_path):
    project = _project(tmp_path)
    schema = {"$id": "https://fairmorph.org/schema/ref", "type": "object",
              "properties": {"x": {"$ref": "https://untrusted.invalid/schema.json"}}}
    with pytest.raises(ValueError, match="Remote"):
        register_schema(project, schema_id=schema["$id"], schema_version="1.0.0",
                        kind="source", schema=schema)


def test_schema_file_tamper_is_detected(tmp_path):
    project = _project(tmp_path)
    schema = {"$id": "https://fairmorph.org/schema/a", "type": "object"}
    registered = register_schema(project, schema_id=schema["$id"], schema_version="1.0.0",
                                 kind="core", schema=schema)
    (project / registered["schema_path"]).write_text('{"type":"object"}')
    with pytest.raises(ValueError, match="immutable"):
        get_schema(project, schema_id=schema["$id"], schema_version="1.0.0")


def test_schema_approval_requires_explicit_reviewer(tmp_path):
    project = _project(tmp_path)
    schema = {"$id": "https://fairmorph.org/schema/review", "type": "object"}
    with pytest.raises(ValueError, match="reviewer"):
        register_schema(project, schema_id=schema["$id"], schema_version="1.0.0",
                        kind="source", schema=schema, status="approved")
    approved = register_schema(project, schema_id=schema["$id"], schema_version="1.0.0",
                               kind="source", schema=schema, status="approved", reviewer="researcher")
    assert approved["status"] == "approved"
