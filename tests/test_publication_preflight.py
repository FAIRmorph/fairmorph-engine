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
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
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

    metadata.write_text('{"title":"Changed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="metadata SHA-256 mismatch"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)

    metadata.write_text('{"title":"Survey"}', encoding="utf-8")
    profile["run_manifest_sha256"] = "0" * 64
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="RUN manifest SHA-256 mismatch"):
        validate_publication_intent(tmp_path, "synthetic-run", profile_file, metadata)
