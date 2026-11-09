"""Execute a project-defined typed observation mapping without count assumptions."""

import hashlib
import json

import pytest

from fairmorph_engine.core.profile import approve_staged_mapping, stage_csv_mapping
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.run_executor import execute_mapping_run


def test_typed_decimal_and_text_observations(tmp_path):
    pl = pytest.importorskip("polars")
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "measurements.csv"
    source.write_text(
        "site,temperature,condition\nA,12.50,wet\nB,-0.25,dry\n",
        encoding="utf-8",
    )
    resource_id = import_resource(project, source, "observations")["resource_id"]
    profile = {
        "mapping_id": "typed-observations",
        "version": "1.0.0",
        "operation": "wide-to-long-values/1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "identifier": "site",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": "temperature",
                "target_field": "temperature",
                "description": "Recorded temperature measurement",
                "definition_source": "source_documentation",
                "zero_meaning": "not_applicable",
                "missing_values": [],
                "value_type": "decimal",
            },
            {
                "source_column": "condition",
                "target_field": "condition",
                "description": "Recorded categorical condition",
                "definition_source": "source_documentation",
                "zero_meaning": "not_applicable",
                "missing_values": [],
                "value_type": "text",
            },
        ],
        "acceptance": {"output_rows": 4},
    }
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    staged = stage_csv_mapping(project, resource_id, path)
    approve_staged_mapping(project, staged["mapping_sha256"], "reviewer")
    run = execute_mapping_run(project, staged["mapping_sha256"])
    frame = pl.read_parquet(project / "runs" / run["run_id"] / "outputs" / "observations.parquet")
    assert frame.height == 4
    values = {
        (row["source_identifier"], row["source_column"]): (
            row["value"],
            row["value_type"],
        )
        for row in frame.to_dicts()
    }
    assert values[("A", "temperature")] == ("12.50", "decimal")
    assert values[("B", "temperature")] == ("-0.25", "decimal")
    assert values[("A", "condition")] == ("wet", "text")
