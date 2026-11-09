"""Generic publication preflight checks hashes, not scientific semantics."""

import hashlib
import json

import pytest

from fairmorph_engine.core.publication import validate_publication_intent


def test_publication_preflight_pins_run_and_metadata(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest_file = run_dir / "manifest.json"
    manifest_file.write_text('{"schema_version":"fairmorph.poc.run/2"}', encoding="utf-8")
    metadata = tmp_path / "metadata.json"
    metadata.write_text('{"title":"Survey"}', encoding="utf-8")

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    profile = {
        "schema_version": "fairmorph.poc.publication-profile/1",
        "profile_id": "survey",
        "version": "1.0.0",
        "run_manifest_sha256": digest(manifest_file),
        "metadata_sha256": digest(metadata),
        "formats": ["eml/2.2.0"],
    }
    profile_file = tmp_path / "publication.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(
        "fairmorph_engine.core.publication.verified_run",
        lambda _project, _run_id: (run_dir, {"schema_version": "fairmorph.poc.run/2"}),
    )
    result = validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)
    assert result["status"] == "validated"
    assert result["publication_ready"] is False
    assert result["field_bindings_verified"] is False

    metadata.write_text('{"title":"Changed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="metadata SHA-256 mismatch"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)

    metadata.write_text('{"title":"Survey"}', encoding="utf-8")
    profile["run_manifest_sha256"] = "0" * 64
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="RUN manifest SHA-256 mismatch"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)

    profile["run_manifest_sha256"] = digest(manifest_file)
    profile["formats"] = ["dwca/1"]
    profile["dwca"] = {
        "core": "Event",
        "core_id_field": "event_key",
        "core_fields": [
            {"source_field": "event_key", "term": "http://rs.tdwg.org/dwc/terms/eventID"}
        ],
        "extensions": [
            {
                "row_type": "Occurrence",
                "core_id_field": "occurrence_key",
                "fields": [
                    {
                        "source_field": "occurrence_key",
                        "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                    }
                ],
            }
        ],
    }
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    assert (
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)["status"]
        == "validated"
    )

    profile["dwca"]["extensions"][0]["fields"][0]["source_field"] = "wrong_key"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="must bind its identifier"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)


def test_occurrence_core_preflight_and_duplicate_bindings(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = run_dir / "manifest.json"
    manifest.write_text('{"schema_version":"fairmorph.poc.run/2"}', encoding="utf-8")
    metadata = tmp_path / "metadata.json"
    metadata.write_text('{"title":"Survey"}', encoding="utf-8")
    profile = {
        "schema_version": "fairmorph.poc.publication-profile/1",
        "profile_id": "survey",
        "version": "1.0.0",
        "run_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
        "formats": ["dwca/1"],
        "dwca": {
            "core": "Occurrence",
            "core_id_field": "record_key",
            "core_fields": [
                {
                    "source_field": "record_key",
                    "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                }
            ],
        },
    }
    profile_file = tmp_path / "publication.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")

    def fake_verified_run(_project, _run_id):
        return run_dir, {"schema_version": "fairmorph.poc.run/2"}

    monkeypatch.setattr("fairmorph_engine.core.publication.verified_run", fake_verified_run)
    result = validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)
    assert result["status"] == "validated"
    assert result["publication_ready"] is False

    profile["dwca"]["core_fields"].append(
        {
            "source_field": "record_key",
            "term": "http://rs.tdwg.org/dwc/terms/taxonID",
        }
    )
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate Occurrence source field"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)

    profile["dwca"]["core_fields"][1]["source_field"] = "taxon_key"
    profile["dwca"]["core_fields"][1]["term"] = "http://rs.tdwg.org/dwc/terms/occurrenceID"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate Occurrence source field or Darwin Core term"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)


def test_publication_preflight_rejects_symlinked_profile(tmp_path):
    target = tmp_path / "intent.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "intent-link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable on this platform")
    with pytest.raises(ValueError, match="Publication profile must be an existing regular file"):
        validate_publication_intent(tmp_path, "unused", link, tmp_path / "metadata.json")


def test_publication_preflight_rejects_duplicate_row_types(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = run_dir / "manifest.json"
    manifest.write_text('{"schema_version":"fairmorph.poc.run/2"}', encoding="utf-8")
    metadata = tmp_path / "metadata.json"
    metadata.write_text("{}", encoding="utf-8")
    profile = {
        "schema_version": "fairmorph.poc.publication-profile/1",
        "profile_id": "survey",
        "version": "1.0.0",
        "run_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
        "formats": ["dwca/1"],
        "dwca": {
            "core": "Occurrence",
            "core_id_field": "record_key",
            "core_fields": [
                {
                    "source_field": "record_key",
                    "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                }
            ],
            "extensions": [
                {
                    "row_type": "Occurrence",
                    "core_id_field": "other_key",
                    "fields": [
                        {
                            "source_field": "other_key",
                            "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                        }
                    ],
                }
            ],
        },
    }
    profile_file = tmp_path / "publication.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")

    def fake_verified_run(_project, _run_id):
        return run_dir, {"schema_version": "fairmorph.poc.run/2"}

    monkeypatch.setattr("fairmorph_engine.core.publication.verified_run", fake_verified_run)
    with pytest.raises(ValueError, match="Duplicate Darwin Core row type"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)
