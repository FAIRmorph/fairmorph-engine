"""Generic relationship preflight rejects malformed imported CSV data."""

import hashlib
import json

import pytest

from fairmorph_engine.core.profile import stage_csv_mapping
from fairmorph_engine.core.project import import_resource, initialize_project


@pytest.mark.parametrize(
    "auxiliary_bytes",
    [b"key,label\na,ok\nb\n", b"key,label\na,ok,unexpected\n"],
)
def test_relationship_preflight_rejects_malformed_auxiliary_rows(tmp_path, auxiliary_bytes):
    project = tmp_path / "project"
    initialize_project(project, "Independent measurements")
    primary = tmp_path / "measurements.csv"
    primary.write_bytes(b"sample,count\na,2\n")
    auxiliary = tmp_path / "lookup.csv"
    auxiliary.write_bytes(auxiliary_bytes)
    source = import_resource(project, primary, "measurements")
    lookup = import_resource(project, auxiliary, "lookup")
    profile = {
        "mapping_id": "measurements",
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_sha256": hashlib.sha256(primary.read_bytes()).hexdigest(),
        "identifier": "sample",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": "count",
                "target_field": "count",
                "description": "Count of measured items",
                "definition_source": "source_documentation",
                "counting_unit": "item",
                "zero_meaning": "true_zero",
                "missing_values": [{"token": "", "meaning": "not recorded"}],
            }
        ],
        "auxiliary_resource_ids": [lookup["resource_id"]],
        "relationships": [
            {
                "relationship_id": "measurement-lookup",
                "left_resource_id": source["resource_id"],
                "left_column": "sample",
                "right_resource_id": lookup["resource_id"],
                "right_column": "key",
                "cardinality": "many-to-one",
            }
        ],
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed relationship CSV row"):
        stage_csv_mapping(project, source["resource_id"], profile_path)
