"""Project-independent cross-contract publication binding checks."""

import json

import pytest

from fairmorph_engine.core.publication_bindings import validate_publication_binding_columns


def test_binding_columns_require_matching_external_row_types(tmp_path, monkeypatch):
    profile = {
        "run_manifest_sha256": "a" * 64,
        "formats": ["dwca/1"],
        "dwca": {
            "core": "Occurrence",
            "core_fields": [
                {"source_field": "record_key", "term": "http://rs.tdwg.org/dwc/terms/occurrenceID"}
            ],
            "extensions": [],
        },
    }
    plan = {
        "run_manifest_sha256": "a" * 64,
        "tables": [
            {
                "row_type": "Occurrence",
                "columns": ["record_key"],
                "artifact_path": "outputs/records.parquet",
            }
        ],
    }
    profile_file = tmp_path / "profile.json"
    projection_file = tmp_path / "projection.json"

    def check():
        profile_file.write_text(json.dumps(profile), encoding="utf-8")
        projection_file.write_text(json.dumps(plan), encoding="utf-8")
        return validate_publication_binding_columns(
            tmp_path, "synthetic-run", profile_file, tmp_path / "metadata.json", projection_file
        )

    def fake_intent(*_args):
        return {"profile_id": "survey"}

    def fake_projection(*_args):
        return {"row_types": ["Occurrence"]}

    monkeypatch.setattr(
        "fairmorph_engine.core.publication_bindings.validate_publication_intent", fake_intent
    )
    monkeypatch.setattr(
        "fairmorph_engine.core.publication_bindings.validate_publication_projection",
        fake_projection,
    )
    result = check()
    assert result["binding_columns_verified"] is True
    assert result["publication_ready"] is False

    plan["tables"][0]["columns"] = ["different_key"]
    with pytest.raises(ValueError, match="Publication bindings missing"):
        check()

    plan["tables"][0]["row_type"] = "Event"
    with pytest.raises(ValueError, match="row types differ"):
        check()

    plan["tables"][0]["row_type"] = "Occurrence"
    plan["tables"][0]["columns"] = ["record_key"]
    plan["run_manifest_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="RUN pins differ"):
        check()
