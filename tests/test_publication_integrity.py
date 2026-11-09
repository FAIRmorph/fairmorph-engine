"""Generic, synthetic integrity checks across projected Parquet tables."""

import hashlib
import json

import polars as pl
import pytest

from fairmorph_engine.core.publication_integrity import validate_publication_integrity


def test_integrity_checks_identifiers_and_foreign_keys(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "outputs").mkdir(parents=True)
    pl.DataFrame({"event_key": ["e1", "e2"]}).write_parquet(run / "outputs/events.parquet")
    pl.DataFrame({"record_key": ["r1", "r2"], "event_ref": ["e1", "e2"]}).write_parquet(
        run / "outputs/records.parquet"
    )
    manifest_file = run / "manifest.json"
    manifest_file.write_text("{}", encoding="utf-8")
    pin = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    metadata = tmp_path / "metadata.json"
    metadata.write_text("{}", encoding="utf-8")
    profile = {
        "schema_version": "fairmorph.poc.publication-profile/1",
        "profile_id": "synthetic",
        "version": "1.0.0",
        "run_manifest_sha256": pin,
        "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
        "formats": ["dwca/1"],
        "dwca": {
            "core": "Event",
            "core_id_field": "event_key",
            "core_fields": [
                {"source_field": "event_key", "term": "http://rs.tdwg.org/dwc/terms/eventID"}
            ],
            "extensions": [
                {
                    "row_type": "Occurrence",
                    "core_id_field": "record_key",
                    "fields": [
                        {
                            "source_field": "record_key",
                            "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                        }
                    ],
                }
            ],
        },
    }
    plan = {
        "schema_version": "fairmorph.poc.publication-projection/1",
        "run_manifest_sha256": pin,
        "tables": [
            {
                "row_type": "Event",
                "artifact_path": "outputs/events.parquet",
                "columns": ["event_key"],
            },
            {
                "row_type": "Occurrence",
                "artifact_path": "outputs/records.parquet",
                "columns": ["record_key", "event_ref"],
            },
        ],
    }
    rules = {
        "schema_version": "fairmorph.poc.publication-integrity/1",
        "run_manifest_sha256": pin,
        "identifiers": [
            {"row_type": "Event", "column": "event_key"},
            {"row_type": "Occurrence", "column": "record_key"},
        ],
        "relationships": [
            {
                "child_row_type": "Occurrence",
                "child_column": "event_ref",
                "parent_row_type": "Event",
                "parent_column": "event_key",
            }
        ],
    }
    paths = [tmp_path / name for name in ("profile.json", "projection.json", "integrity.json")]
    for path, data in zip(paths, (profile, plan, rules), strict=True):
        path.write_text(json.dumps(data), encoding="utf-8")

    def verified(_project, _run_id):
        return run, {
            "schema_version": "fairmorph.poc.run/2",
            "artifacts": [
                {"path": "outputs/events.parquet"},
                {"path": "outputs/records.parquet"},
            ],
        }

    monkeypatch.setattr("fairmorph_engine.core.publication.verified_run", verified)
    monkeypatch.setattr("fairmorph_engine.core.publication_projection.verified_run", verified)
    monkeypatch.setattr("fairmorph_engine.core.publication_integrity.verified_run", verified)

    def check():
        return validate_publication_integrity(
            tmp_path, "synthetic-run", paths[0], metadata, paths[1], paths[2]
        )

    assert check()["integrity_verified"] is True
    assert check()["publication_ready"] is False
    pl.DataFrame({"record_key": ["r1", "r2"], "event_ref": ["e1", "missing"]}).write_parquet(
        run / "outputs/records.parquet"
    )
    with pytest.raises(ValueError, match="orphan foreign keys"):
        check()
    pl.DataFrame({"record_key": ["r1", "r1"], "event_ref": ["e1", "e2"]}).write_parquet(
        run / "outputs/records.parquet"
    )
    with pytest.raises(ValueError, match="Invalid identifier values"):
        check()


def test_integrity_contract_rejects_unpinned_rules(tmp_path):
    from jsonschema import Draft202012Validator

    schema_path = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "src/fairmorph_engine/contracts/publication-integrity.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    rules = {
        "schema_version": "fairmorph.poc.publication-integrity/1",
        "run_manifest_sha256": "a" * 64,
        "identifiers": [{"row_type": "Occurrence", "column": "record_key"}],
        "relationships": [],
    }
    assert validator.is_valid(rules)
    rules["run_manifest_sha256"] = "invalid"
    assert not validator.is_valid(rules)
