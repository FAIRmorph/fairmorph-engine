"""Reject invalid externally declared CSV relationships before reviewer approval."""

import hashlib
import json

import pytest

from fairmorph_engine.core.profile import stage_csv_mapping
from fairmorph_engine.core.project import import_resource, initialize_project


@pytest.mark.parametrize(
    ("primary_csv", "auxiliary_csv", "cardinality", "error"),
    [
        ("key,count\nA,1\nB,2\n", "key,label\nA,x\n", "many-to-one", "unmatched"),
        ("key,count\nA,1\nA,2\n", "key,label\nA,x\n", "one-to-one", "left-side"),
        ("key,count\nA,1\n", "key,label\nA,x\nA,y\n", "many-to-one", "right-side"),
        ("key,count\n,1\n", "key,label\nA,x\n", "many-to-one", "missing"),
    ],
)
def test_relationship_integrity_rejects_invalid_sources(
    tmp_path, primary_csv, auxiliary_csv, cardinality, error
):
    project = tmp_path / "project"
    initialize_project(project)
    primary = tmp_path / "primary.csv"
    auxiliary = tmp_path / "auxiliary.csv"
    primary.write_text(primary_csv, encoding="utf-8")
    auxiliary.write_text(auxiliary_csv, encoding="utf-8")
    primary_id = import_resource(project, primary, "primary")["resource_id"]
    auxiliary_id = import_resource(project, auxiliary, "auxiliary")["resource_id"]
    profile = {
        "mapping_id": "integrity",
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_sha256": hashlib.sha256(primary.read_bytes()).hexdigest(),
        "identifier": "key",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": "count",
                "target_field": "count",
                "description": "Counted individuals in this category",
                "definition_source": "source_documentation",
                "counting_unit": "individual",
                "zero_meaning": "true_zero",
                "missing_values": [],
            }
        ],
        "auxiliary_resource_ids": [auxiliary_id],
        "relationships": [
            {
                "relationship_id": "link",
                "left_resource_id": primary_id,
                "left_column": "key",
                "right_resource_id": auxiliary_id,
                "right_column": "key",
                "cardinality": cardinality,
            }
        ],
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        stage_csv_mapping(project, primary_id, profile_path)


@pytest.mark.parametrize(
    ("primary_csv", "auxiliary_csv", "policy"),
    [
        ("key,count\nA,1\nB,2\n", "key,label\nA,x\n", {"require_match": False}),
        ("key,count\n,1\nA,2\n", "key,label\nA,x\n", {"missing_key_policy": "ignore"}),
    ],
)
def test_relationship_policies_are_project_configured(
    tmp_path, primary_csv, auxiliary_csv, policy
):
    project = tmp_path / "project"
    initialize_project(project)
    primary = tmp_path / "primary.csv"
    auxiliary = tmp_path / "auxiliary.csv"
    primary.write_text(primary_csv, encoding="utf-8")
    auxiliary.write_text(auxiliary_csv, encoding="utf-8")
    primary_id = import_resource(project, primary, "primary")["resource_id"]
    auxiliary_id = import_resource(project, auxiliary, "auxiliary")["resource_id"]
    profile = {
        "mapping_id": "configurable",
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_sha256": hashlib.sha256(primary.read_bytes()).hexdigest(),
        "identifier": "key",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": "count",
                "target_field": "count",
                "description": "Counted individuals in this category",
                "definition_source": "source_documentation",
                "counting_unit": "individual",
                "zero_meaning": "true_zero",
                "missing_values": [],
            }
        ],
        "auxiliary_resource_ids": [auxiliary_id],
        "relationships": [
            {
                "relationship_id": "link",
                "left_resource_id": primary_id,
                "left_column": "key",
                "right_resource_id": auxiliary_id,
                "right_column": "key",
                "cardinality": "many-to-one",
                **policy,
            }
        ],
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    staged = stage_csv_mapping(project, primary_id, profile_path)
    assert staged["status"] == "draft"
