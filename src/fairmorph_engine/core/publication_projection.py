"""Validate external publication projection declarations against immutable RUN artifacts."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from fairmorph_engine.core.export import sha256, verified_run


def validate_publication_projection(project: Path, run_id: str, plan_file: Path) -> dict:
    """Check pinned Parquet artifact columns; do not execute a publication export."""
    schema_path = (
        Path(__file__).resolve().parents[1] / "contracts" / "publication-projection.schema.json"
    )
    if not plan_file.is_file() or plan_file.is_symlink():
        raise ValueError("Projection plan must be an existing regular file")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(plan)
    run_dir, manifest = verified_run(project, run_id)
    if manifest["schema_version"] != "fairmorph.poc.run/2":
        raise ValueError("Projection requires a generic RUN/2")
    if sha256(run_dir / "manifest.json") != plan["run_manifest_sha256"]:
        raise ValueError("Projection RUN manifest SHA-256 mismatch")

    declared_artifacts = {item["path"] for item in manifest["artifacts"]}
    seen_types = set()
    from polars import scan_parquet

    for table in plan["tables"]:
        row_type = table["row_type"]
        if row_type in seen_types:
            raise ValueError("Duplicate projection row type")
        seen_types.add(row_type)
        relative = table["artifact_path"]
        if relative not in declared_artifacts:
            raise ValueError(f"Projection artifact not pinned in RUN: {relative}")
        artifact = run_dir / relative
        if artifact.is_symlink() or not artifact.is_file():
            raise ValueError(f"Projection artifact must be a regular file: {relative}")
        available = set(scan_parquet(artifact).collect_schema().names())
        missing = set(table["columns"]) - available
        if missing:
            raise ValueError(f"Projection columns missing in {relative}: {sorted(missing)}")
        declared_types = table.get("column_types", {})
        if set(declared_types) - set(table["columns"]):
            raise ValueError("Projection types reference undeclared columns")
        actual_types = scan_parquet(artifact).collect_schema()
        for column, expected in declared_types.items():
            if str(actual_types[column]) != expected:
                raise ValueError(f"Projection type mismatch: {row_type}.{column}")
    return {
        "status": "validated",
        "run_id": run_id,
        "row_types": sorted(seen_types),
        "artifact_columns_verified": True,
        "field_bindings_verified": False,
        "publication_ready": False,
    }
