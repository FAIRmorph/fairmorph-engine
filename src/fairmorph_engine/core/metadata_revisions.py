"""Append-only optional metadata envelopes, separate from tabular entity data.

The PoC never creates one SQLite metadata row per source observation.
Only explicitly curated/reviewed metadata revisions are registered and
hash-pinned in the same immutable RUN/2 input snapshot as profile schemas.
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fairmorph_engine.core.domain_profiles import (
    resolve_profiles,
    validate_entity_profiles,
    validate_metadata_envelope,
)
from fairmorph_engine.core.registry import _catalog, canonical_bytes, digest


def _tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata_revisions (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            metadata_revision_id TEXT NOT NULL UNIQUE,
            configuration_sha256 TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            parent_revision_id TEXT,
            envelope_json TEXT NOT NULL,
            envelope_sha256 TEXT NOT NULL,
            schema_pins_json TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            UNIQUE(configuration_sha256, entity_type, entity_id, metadata_revision_id)
        );
        CREATE INDEX IF NOT EXISTS metadata_revisions_pipeline
            ON metadata_revisions(configuration_sha256, sequence);
        CREATE TABLE IF NOT EXISTS current_metadata_revisions (
            configuration_sha256 TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            metadata_revision_id TEXT NOT NULL REFERENCES metadata_revisions(metadata_revision_id),
            PRIMARY KEY(configuration_sha256, entity_type, entity_id)
        );
        CREATE TRIGGER IF NOT EXISTS metadata_revisions_immutable_update
            BEFORE UPDATE ON metadata_revisions
            BEGIN SELECT RAISE(ABORT, 'Metadata revisions are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS metadata_revisions_immutable_delete
            BEFORE DELETE ON metadata_revisions
            BEGIN SELECT RAISE(ABORT, 'Metadata revisions are append-only'); END;
        """
    )


def _projected(project: Path, sha: str) -> dict:
    from fairmorph_engine.core.entity_projection import (
        project_entities,
        require_confirmation,
        verify_projection_evidence,
    )
    from fairmorph_engine.core.pipeline import execute_pipeline
    from fairmorph_engine.core.pipeline_run import load_pipeline, resolve_resources

    config = load_pipeline(project, sha)
    confirmation = require_confirmation(project, sha)
    sources, _ = resolve_resources(project, config)
    tables = execute_pipeline(
        {"schema_version": config["schema_version"], "steps": config["steps"]},
        sources,
    )
    verify_projection_evidence(project, config, tables, confirmation)
    return project_entities(config, tables)


def _revision_events(db: sqlite3.Connection, sha: str, cutoff: int | None):
    statement = (
        "SELECT sequence, metadata_revision_id, entity_type, entity_id, "
        "parent_revision_id, envelope_json, envelope_sha256, schema_pins_json, approved_by "
        "FROM metadata_revisions WHERE configuration_sha256=?"
    )
    args = (sha,)
    if cutoff is not None:
        statement += " AND sequence<=?"
        args = (sha, cutoff)
    statement += " ORDER BY sequence"
    return db.execute(statement, args).fetchall()


def _active_revisions(events: list, pins: dict, resolved: dict) -> dict:
    active = {}
    for (
        _,
        revision_id,
        kind,
        entity_id,
        parent_id,
        raw,
        checksum,
        raw_pins,
        approved_by,
    ) in events:
        envelope = json.loads(raw)
        if (
            digest(envelope) != checksum
            or envelope["metadata_revision_id"] != revision_id
            or envelope["entity_type"] != kind
            or envelope["entity_id"] != entity_id
            or envelope["review_status"] != "approved"
            or not approved_by.strip()
        ):
            raise ValueError("Metadata revision identity or hash mismatch")
        if kind not in pins["entities"]:
            raise ValueError("Metadata revision entity kind is not in selected profile")
        expected = {"envelope": pins["envelope"], "entity": pins["entities"][kind]}
        if json.loads(raw_pins) != expected:
            raise ValueError("Metadata revision does not pin exact schema versions")
        validate_metadata_envelope(resolved, kind, envelope)
        key = (kind, entity_id)
        previous = active.get(key)
        if parent_id != (previous["metadata_revision_id"] if previous else None):
            raise ValueError("Metadata revision parent chain is not append-only")
        active[key] = {
            "entity_type": kind,
            "entity_id": entity_id,
            "metadata_revision_id": revision_id,
            "envelope_sha256": checksum,
        }
    return active


def register_metadata_revision(
    project: Path,
    pipeline_sha256: str,
    *,
    entity_type: str,
    entity_id: str,
    attributes: dict,
    field_provenance: dict,
    source: str,
    confirmed_by: str,
    parent_revision_id: str | None = None,
) -> dict:
    """Persist one user-approved envelope, never mutate a previous revision."""
    from fairmorph_engine.core.pipeline_run import load_pipeline

    if not isinstance(confirmed_by, str) or not confirmed_by.strip():
        raise ValueError("A confirming user is required for approved metadata")
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("Metadata requires an existing technical entity_id")
    config = load_pipeline(project, pipeline_sha256)
    pins = config.get("profile_bindings")
    if pins is None:
        raise ValueError("Metadata needs explicit P0.5 profile bindings")
    resolved = resolve_profiles(project, config)
    if entity_type not in pins["entities"]:
        raise ValueError("Metadata entity type is not selected in this pipeline")
    frames = _projected(project, pipeline_sha256)
    validate_entity_profiles(resolved, frames)
    if entity_id not in frames[entity_type].get_column("entity_id").to_list():
        raise ValueError("Metadata entity_id does not exist in confirmed projection")
    if not isinstance(attributes, dict) or not isinstance(field_provenance, dict):
        raise ValueError("Metadata attributes and field provenance must be objects")
    envelope = {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "schema_version": "0.8.0",
        "metadata_revision_id": "metadata-" + uuid.uuid4().hex,
        "recorded_at": datetime.now(UTC).isoformat(),
        "source": source,
        "review_status": "approved",
        "attributes": attributes,
        "field_provenance": field_provenance,
    }
    validate_metadata_envelope(resolved, entity_type, envelope)
    schema_pins = {"envelope": pins["envelope"], "entity": pins["entities"][entity_type]}
    checksum = digest(envelope)
    with _catalog(project) as db:
        _tables(db)
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT metadata_revision_id FROM current_metadata_revisions "
            "WHERE configuration_sha256=? AND entity_type=? AND entity_id=?",
            (pipeline_sha256, entity_type, entity_id),
        ).fetchone()
        previous = current[0] if current else None
        if parent_revision_id != previous:
            raise ValueError("New metadata revision must name the current parent revision")
        db.execute(
            "INSERT INTO metadata_revisions "
            "(metadata_revision_id,configuration_sha256,entity_type,entity_id,"
            "parent_revision_id,envelope_json,envelope_sha256,schema_pins_json,approved_by) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                envelope["metadata_revision_id"],
                pipeline_sha256,
                entity_type,
                entity_id,
                previous,
                canonical_bytes(envelope).decode(),
                checksum,
                canonical_bytes(schema_pins).decode(),
                confirmed_by.strip(),
            ),
        )
        db.execute(
            "INSERT INTO current_metadata_revisions VALUES (?, ?, ?, ?) "
            "ON CONFLICT(configuration_sha256,entity_type,entity_id) "
            "DO UPDATE SET metadata_revision_id=excluded.metadata_revision_id",
            (pipeline_sha256, entity_type, entity_id, envelope["metadata_revision_id"]),
        )
    return {
        "metadata_revision_id": envelope["metadata_revision_id"],
        "entity_type": entity_type,
        "entity_id": entity_id,
        "envelope_sha256": checksum,
        "parent_revision_id": parent_revision_id,
        "approved_by": confirmed_by.strip(),
    }


def metadata_snapshot(
    project: Path,
    pipeline_sha256: str,
    *,
    through_sequence: int | None = None,
    entity_frames: dict | None = None,
) -> dict:
    """Freeze only explicitly reviewed metadata revisions at a sequence boundary."""
    from fairmorph_engine.core.pipeline_run import load_pipeline

    config = load_pipeline(project, pipeline_sha256)
    pins = config.get("profile_bindings")
    if pins is None:
        raise ValueError("Metadata snapshot requires explicit profile bindings")
    resolved = resolve_profiles(project, config)
    if through_sequence is not None and (type(through_sequence) is not int or through_sequence < 0):
        raise ValueError("Invalid metadata sequence boundary")
    with _catalog(project) as db:
        _tables(db)
        events = _revision_events(db, pipeline_sha256, through_sequence)
        active = _active_revisions(events, pins, resolved)
        if through_sequence is None:
            actual = {
                (kind, entity_id): rev_id
                for kind, entity_id, rev_id in db.execute(
                    "SELECT entity_type,entity_id,metadata_revision_id "
                    "FROM current_metadata_revisions WHERE configuration_sha256=?",
                    (pipeline_sha256,),
                )
            }
            if actual != {k: v["metadata_revision_id"] for k, v in active.items()}:
                raise ValueError("Current metadata pointer disagrees with revision history")
        cutoff = (
            through_sequence if through_sequence is not None else (events[-1][0] if events else 0)
        )
    if entity_frames is not None:
        validate_entity_profiles(resolved, entity_frames)
        for kind, entity_id in active:
            if (
                kind not in entity_frames
                or entity_id not in entity_frames[kind].get_column("entity_id").to_list()
            ):
                raise ValueError("Metadata refers to a missing projected entity")
    snapshot = {
        "schema_version": "fairmorph.metadata.snapshot/1",
        "configuration_sha256": pipeline_sha256,
        "through_sequence": cutoff,
        "schema_pins": pins,
        "active_revisions": [active[k] for k in sorted(active)],
    }
    return {**snapshot, "snapshot_sha256": digest(snapshot)}
