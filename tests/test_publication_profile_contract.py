"""Publication intent is validated without loading project examples or scientific defaults."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


def _validator():
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "src"
            / "fairmorph_engine"
            / "contracts"
            / "publication-profile.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _profile():
    return {
        "schema_version": "fairmorph.poc.publication-profile/1",
        "profile_id": "survey-publication",
        "version": "1.0.0",
        "run_manifest_sha256": "a" * 64,
        "metadata_sha256": "b" * 64,
        "formats": ["eml/2.2.0", "dwca/1"],
        "dwca": {
            "core": "Event",
            "core_id_field": "event_key",
            "occurrence_event_id_field": "event_key",
        },
    }


def test_generic_publication_profile_is_valid():
    _validator().validate(_profile())


@pytest.mark.parametrize("invalid", ["missing_dwca", "unknown_format", "bad_hash"])
def test_publication_profile_rejects_invalid_intent(invalid):
    profile = _profile()
    if invalid == "missing_dwca":
        del profile["dwca"]
    elif invalid == "unknown_format":
        profile["formats"] = ["unreviewed/1"]
    else:
        profile["run_manifest_sha256"] = "not-a-sha256"
    assert not _validator().is_valid(profile)
