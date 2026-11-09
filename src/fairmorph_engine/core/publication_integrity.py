"""Validate externally declared identifiers and relationships on pinned RUN tables."""

import json
from pathlib import Path

import polars as pl
from jsonschema import Draft202012Validator

from fairmorph_engine.core.export import sha256, verified_run
from fairmorph_engine.core.publication_bindings import validate_publication_binding_columns


def validate_publication_integrity(
    project: Path,
    run_id: str,
    profile_file: Path,
    metadata_file: Path,
    projection_file: Path,
    integrity_file: Path,
) -> dict:
    """Read-only validation; does not approve, transform or export publication data."""
    bindings = validate_publication_binding_columns(
        project, run_id, profile_file, metadata_file, projection_file
    )
    if not integrity_file.is_file() or integrity_file.is_symlink():
        raise ValueError("Integrity plan must be an existing regular file")
    schema_path = (
        Path(__file__).resolve().parents[1] / "contracts" / "publication-integrity.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    rules = json.loads(integrity_file.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(rules)
    plan = json.loads(projection_file.read_text(encoding="utf-8"))
    if rules["run_manifest_sha256"] != plan["run_manifest_sha256"]:
        raise ValueError("Integrity and projection RUN pins differ")
    run_dir, manifest = verified_run(project, run_id)
    if manifest["schema_version"] != "fairmorph.poc.run/2":
        raise ValueError("Integrity requires a generic RUN/2")
    if sha256(run_dir / "manifest.json") != rules["run_manifest_sha256"]:
        raise ValueError("Integrity RUN manifest SHA-256 mismatch")
    tables = {table["row_type"]: table for table in plan["tables"]}
    declared = {item["path"] for item in manifest["artifacts"]}
    frames = {}
    for row_type, table in tables.items():
        relative = table["artifact_path"]
        if relative not in declared:
            raise ValueError(f"Unpinned integrity artifact: {relative}")
        artifact = run_dir / relative
        if not artifact.is_file() or artifact.is_symlink():
            raise ValueError(f"Missing integrity artifact: {relative}")
        frames[row_type] = pl.read_parquet(artifact)
    seen_identifiers = set()
    for rule in rules["identifiers"]:
        row_type, column = rule["row_type"], rule["column"]
        if row_type not in frames or column not in tables[row_type]["columns"]:
            raise ValueError(f"Unknown identifier column: {row_type}.{column}")
        if row_type in seen_identifiers:
            raise ValueError(f"Duplicate identifier rule for {row_type}")
        seen_identifiers.add(row_type)
        values = frames[row_type].get_column(column)
        if values.null_count() or values.n_unique() != len(values):
            raise ValueError(f"Invalid identifier values: {row_type}.{column}")
    if seen_identifiers != set(tables):
        raise ValueError("Each projected row type requires an identifier rule")
    for rule in rules["relationships"]:
        child_type, parent_type = rule["child_row_type"], rule["parent_row_type"]
        child_col, parent_col = rule["child_column"], rule["parent_column"]
        if (
            child_type not in frames
            or parent_type not in frames
            or child_col not in tables[child_type]["columns"]
            or parent_col not in tables[parent_type]["columns"]
        ):
            raise ValueError("Relationship references an undeclared table column")
        child_values = frames[child_type].get_column(child_col)
        parent_values = frames[parent_type].get_column(parent_col)
        if child_values.null_count():
            raise ValueError("Relationship contains null foreign keys")
        if parent_values.null_count() or parent_values.n_unique() != len(parent_values):
            raise ValueError("Relationship parent key must be unique and non-null")
        missing = set(child_values.to_list()) - set(parent_values.to_list())
        if missing:
            raise ValueError("Relationship contains orphan foreign keys")
    return {
        "status": "validated",
        "run_id": run_id,
        "row_types": bindings["row_types"],
        "binding_columns_verified": True,
        "integrity_verified": True,
        "publication_ready": False,
    }
