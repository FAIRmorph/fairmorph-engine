"""Explicit, reviewed Observation/Event/Occurrence projections.

No dataset-specific inference: the Workbench can produce these declarative
bindings, while the responsible user explicitly confirms the pinned configuration.
"""

import sqlite3
import re
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from fairmorph_engine.core.registry import _catalog

ENTITIES = ("Observation", "Event", "Occurrence")
ID = {"Observation": "observationID", "Event": "eventID", "Occurrence": "occurrenceID"}
RELATIONS = {
    "Observation": {"eventID": "Event"},
    "Occurrence": {"eventID": "Event", "observationID": "Observation"},
}


def validate_entities(config):
    entities = config.get("entities")
    if not isinstance(entities, dict) or set(entities) != set(ENTITIES):
        raise ValueError("Explicit Observation, Event and Occurrence mappings required")
    tables = set(config["resources"]) | {step["output"] for step in config["steps"]}
    for kind in ENTITIES:
        item = entities[kind]
        if not isinstance(item, dict) or set(item) != {"source_table", "fields", "description"}:
            raise ValueError(f"Invalid {kind} mapping")
        if item["source_table"] not in tables:
            raise ValueError(f"Unknown {kind} source table")
        if not isinstance(item["description"], str) or len(item["description"].strip()) < 12:
            raise ValueError(f"{kind} requires a substantive user description")
        fields = item["fields"]
        if not isinstance(fields, dict) or ID[kind] not in fields or not fields:
            raise ValueError(f"{kind} requires explicit identifier binding")
        for target, source in fields.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", target):
                raise ValueError("Invalid target field name")
            if not isinstance(source, str) or not source:
                raise ValueError("Invalid source field binding")
        if kind == "Occurrence" and "eventID" not in fields:
            raise ValueError("Occurrence requires an explicit eventID relationship")


def _confirmation_table(db: sqlite3.Connection) -> None:
    """Append-only confirmations in the same project registry as field reviews."""
    db.execute(
        "CREATE TABLE IF NOT EXISTS projection_confirmations ("
        "configuration_sha256 TEXT PRIMARY KEY, "
        "confirmed_by TEXT NOT NULL, confirmed_at TEXT NOT NULL, "
        "decision TEXT NOT NULL CHECK(decision='approved'))"
    )


def approve_projection(project: Path, sha: str, reviewer: str) -> dict:
    """Explicit confirmation by a responsible user; no second actor is required."""
    from fairmorph_engine.core.pipeline_run import load_pipeline

    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Explicit confirming user identity required")
    config = load_pipeline(project, sha)
    validate_entities(config)
    timestamp = datetime.now(UTC).isoformat()
    with _catalog(project) as db:
        _confirmation_table(db)
        if db.execute(
            "SELECT 1 FROM projection_confirmations WHERE configuration_sha256=?", (sha,)
        ).fetchone():
            raise ValueError("Projection already confirmed; register a new revision")
        db.execute(
            "INSERT INTO projection_confirmations VALUES (?, ?, ?, 'approved')",
            (sha, reviewer.strip(), timestamp),
        )
    return {
        "schema_version": "fairmorph.projection.approval/1",
        "configuration_sha256": sha,
        "reviewer": reviewer.strip(),
        "reviewed_at": timestamp,
        "decision": "approved",
    }


def require_approval(project: Path, sha: str) -> dict:
    """Resolve the immutable user confirmation from the project registry."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Invalid configuration SHA-256")
    with _catalog(project) as db:
        _confirmation_table(db)
        row = db.execute(
            "SELECT confirmed_by, confirmed_at, decision FROM projection_confirmations "
            "WHERE configuration_sha256=?", (sha,)
        ).fetchone()
    if row is None or row[2] != "approved" or not row[0]:
        raise ValueError("Projection requires explicit user confirmation")
    return {
        "schema_version": "fairmorph.projection.approval/1",
        "configuration_sha256": sha,
        "reviewer": row[0],
        "reviewed_at": row[1],
        "decision": row[2],
    }


def project_entities(config: dict, tables: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    validate_entities(config)
    result = {}
    for kind in ENTITIES:
        spec = config["entities"][kind]
        frame = tables[spec["source_table"]]
        missing = set(spec["fields"].values()) - set(frame.columns)
        if missing:
            raise ValueError(f"{kind} missing mapped source columns: {sorted(missing)}")
        output = frame.select([pl.col(source).alias(target) for target, source in spec["fields"].items()])
        identifier = output.get_column(ID[kind])
        if not output.height or identifier.null_count() or identifier.n_unique() != output.height:
            raise ValueError(f"{kind} identifiers must be unique and non-null")
        if identifier.dtype == pl.String and identifier.str.strip_chars().eq("").any():
            raise ValueError(f"{kind} identifiers cannot be blank")
        result[kind] = output
    for child, references in RELATIONS.items():
        for foreign_key, parent in references.items():
            if foreign_key not in result[child].columns:
                continue
            child_ids = result[child].get_column(foreign_key)
            parent_ids = result[parent].get_column(ID[parent])
            if child_ids.null_count() or child_ids.dtype != parent_ids.dtype:
                raise ValueError(f"{child}.{foreign_key} contains null or incompatible keys")
            if set(child_ids.to_list()) - set(parent_ids.to_list()):
                raise ValueError(f"{child}.{foreign_key} contains orphan references")
    return result
