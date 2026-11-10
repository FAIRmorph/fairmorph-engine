"""Generic publication projection plans do not infer project semantics."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


def _validator():
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "fairmorph_engine"
        / "contracts"
        / "publication-projection.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _plan():
    return {
        "schema_version": "fairmorph.poc.publication-projection/1",
        "run_manifest_sha256": "a" * 64,
        "tables": [
            {
                "row_type": "Occurrence",
                "artifact_path": "outputs/records.parquet",
                "columns": ["record_key", "taxon_key"],
            }
        ],
    }


def test_generic_projection_plan_is_valid():
    _validator().validate(_plan())


@pytest.mark.parametrize("invalid", ["path_escape", "duplicate_columns", "bad_digest"])
def test_projection_plan_rejects_invalid_structure(invalid):
    plan = _plan()
    if invalid == "path_escape":
        plan["tables"][0]["artifact_path"] = "../records.parquet"
    elif invalid == "duplicate_columns":
        plan["tables"][0]["columns"] = ["record_key", "record_key"]
    else:
        plan["run_manifest_sha256"] = "not-a-digest"
    assert not _validator().is_valid(plan)
