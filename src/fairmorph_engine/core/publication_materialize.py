"""Deterministically materialize externally mapped publication tables from a verified RUN."""

import json
from pathlib import Path

import polars as pl

from fairmorph_engine.core.export import sha256
from fairmorph_engine.core.publication_integrity import validate_publication_integrity
from fairmorph_engine.core.publication_projection import validate_publication_projection


def materialize_publication_tables(
    project: Path,
    run_id: str,
    profile_file: Path,
    metadata_file: Path,
    projection_file: Path,
    integrity_file: Path,
    destination: Path,
) -> dict:
    """PoC materialization: read-only RUN inputs, stable CSV and SHA-pinned manifest."""
    validate_publication_integrity(
        project, run_id, profile_file, metadata_file, projection_file, integrity_file
    )
    validate_publication_projection(project, run_id, projection_file)
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    plan = json.loads(projection_file.read_text(encoding="utf-8"))
    rules = json.loads(integrity_file.read_text(encoding="utf-8"))
    dwca = profile["dwca"]
    declared = [(dwca["core"], dwca["core_fields"])]
    declared.extend(
        (extension["row_type"], extension["fields"])
        for extension in dwca.get("extensions", [])
    )
    source_tables = {table["row_type"]: table for table in plan["tables"]}
    identifiers = {item["row_type"]: item["column"] for item in rules["identifiers"]}
    run_dir = project / "runs" / run_id
    if destination.exists():
        raise ValueError("Publication destination already exists")
    destination.mkdir(parents=True)
    artifacts = []
    for row_type, fields in declared:
        source = source_tables[row_type]
        frame = pl.read_parquet(run_dir / source["artifact_path"])
        id_column = identifiers[row_type]
        selected = [
            pl.col(field["source_field"]).alias(field["term"].rsplit("/", 1)[-1])
            for field in fields
        ]
        output = frame.sort(id_column).select(selected)
        target = destination / f"{row_type}.csv"
        output.write_csv(target, include_header=True)
        artifacts.append(
            {
                "row_type": row_type,
                "path": target.name,
                "rows": output.height,
                "columns": output.columns,
                "source_artifact": source["artifact_path"],
                "sha256": sha256(target),
            }
        )
    manifest = {
        "schema_version": "fairmorph.poc.publication-tables/1",
        "source_run_id": run_id,
        "run_manifest_sha256": plan["run_manifest_sha256"],
        "publication_profile_sha256": sha256(profile_file),
        "projection_sha256": sha256(projection_file),
        "integrity_sha256": sha256(integrity_file),
        "metadata_sha256": sha256(metadata_file),
        "artifacts": artifacts,
        "publication_ready": False,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest
