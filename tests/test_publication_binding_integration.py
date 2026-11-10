"""Exercise the generic publication checks against an actual Parquet artifact."""

import hashlib
import json

import polars as pl
import pytest

from fairmorph_engine.core.publication_bindings import validate_publication_binding_columns


def test_publication_binding_integration_with_parquet(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    (run_dir / "outputs").mkdir(parents=True)
    artifact = run_dir / "outputs" / "observations.parquet"
    pl.DataFrame({"record_id": ["r1"], "value": [1]}).write_parquet(artifact)
    manifest_file = run_dir / "manifest.json"
    manifest_file.write_text('{"schema_version":"fairmorph.poc.run/2"}', encoding="utf-8")
    manifest_hash = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    metadata = tmp_path / "metadata.json"
    metadata.write_text('{"title":"Synthetic"}', encoding="utf-8")
    metadata_hash = hashlib.sha256(metadata.read_bytes()).hexdigest()
    profile = {
        "schema_version": "fairmorph.poc.publication-profile/1",
        "profile_id": "synthetic",
        "version": "1.0.0",
        "run_manifest_sha256": manifest_hash,
        "metadata_sha256": metadata_hash,
        "formats": ["dwca/1"],
        "dwca": {
            "core": "Occurrence",
            "core_id_field": "record_id",
            "core_fields": [
                {
                    "source_field": "record_id",
                    "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                }
            ],
        },
    }
    plan = {
        "schema_version": "fairmorph.poc.publication-projection/1",
        "run_manifest_sha256": manifest_hash,
        "tables": [
            {
                "row_type": "Occurrence",
                "artifact_path": "outputs/observations.parquet",
                "columns": ["record_id", "value"],
            }
        ],
    }
    profile_file = tmp_path / "publication.json"
    projection_file = tmp_path / "projection.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    projection_file.write_text(json.dumps(plan), encoding="utf-8")

    def verified(_project, _run_id):
        return run_dir, {
            "schema_version": "fairmorph.poc.run/2",
            "artifacts": [{"path": "outputs/observations.parquet"}],
        }

    monkeypatch.setattr("fairmorph_engine.core.publication.verified_run", verified)
    monkeypatch.setattr("fairmorph_engine.core.publication_projection.verified_run", verified)

    result = validate_publication_binding_columns(
        tmp_path, "synthetic-run", profile_file, metadata, projection_file
    )
    assert result["binding_columns_verified"] is True
    assert result["publication_ready"] is False

    profile["dwca"]["core_fields"].append(
        {"source_field": "unavailable", "term": "http://rs.tdwg.org/dwc/terms/taxonID"}
    )
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="Publication bindings missing"):
        validate_publication_binding_columns(
            tmp_path, "synthetic-run", profile_file, metadata, projection_file
        )
