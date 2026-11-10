"""P0.4: append-only, user-confirmed ecological relation assertions.

The versioned profile is a contract, not an inferred ecological interpretation.
RUNs freeze a canonical current assertion set at a logged sequence boundary.
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from fairmorph_engine.core.registry import _catalog, digest

_PROFILE_PATH = Path(__file__).resolve().parents[1] / "contracts" / "relation-profile.poc.json"
_SOURCE_KINDS = {"user_confirmed", "imported_declared", "extracted", "suggested"}


def relation_profile() -> dict:
    """The selected, explicitly versioned minimal PoC predicate contract."""
    profile = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    if profile["schema_version"] != "fairmorph.relation-profile/1":
        raise ValueError("Unsupported relation profile version")
    return {
        "schema_version": profile["schema_version"],
        "profile_id": profile["profile_id"],
        "version": profile["version"],
        "sha256": digest(profile),
        "predicates": profile["predicates"],
    }


def _ensure_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS relation_assertions (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            assertion_id TEXT NOT NULL UNIQUE,
            relation_id TEXT NOT NULL,
            pipeline_sha256 TEXT NOT NULL,
            operation TEXT NOT NULL CHECK(operation IN ('assert','retract','replace')),
            supersedes_assertion_id TEXT,
            payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
            payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
            UNIQUE(relation_id, assertion_id)
        );
        CREATE INDEX IF NOT EXISTS relation_assertions_pipeline
            ON relation_assertions(pipeline_sha256, sequence);
        CREATE TABLE IF NOT EXISTS current_relations (
            relation_id TEXT PRIMARY KEY,
            pipeline_sha256 TEXT NOT NULL,
            assertion_id TEXT NOT NULL,
            FOREIGN KEY(relation_id, assertion_id)
                REFERENCES relation_assertions(relation_id, assertion_id)
        );
        CREATE INDEX IF NOT EXISTS current_relations_pipeline
            ON current_relations(pipeline_sha256);
        CREATE TRIGGER IF NOT EXISTS relation_assertions_append_only_update
            BEFORE UPDATE ON relation_assertions
            BEGIN SELECT RAISE(ABORT, 'Relation assertions are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS relation_assertions_append_only_delete
            BEFORE DELETE ON relation_assertions
            BEGIN SELECT RAISE(ABORT, 'Relation assertions are append-only'); END;
        """
    )


def _events(db: sqlite3.Connection, sha: str, through: int | None) -> list[tuple[int, dict]]:
    statement = (
        "SELECT sequence, assertion_id, relation_id, operation, "
        "supersedes_assertion_id, payload_json, payload_sha256 "
        "FROM relation_assertions WHERE pipeline_sha256=?"
    )
    arguments = (sha,)
    if through is not None:
        statement += " AND sequence<=?"
        arguments = (sha, through)
    statement += " ORDER BY sequence"
    events = []
    for sequence, aid, rid, operation, previous, raw, checksum in db.execute(statement, arguments):
        payload = json.loads(raw)
        if (
            digest(payload) != checksum
            or payload["assertion_id"] != aid
            or payload["relation_id"] != rid
            or payload["operation"] != operation
            or payload["supersedes_assertion_id"] != previous
            or payload["configuration_sha256"] != sha
        ):
            raise ValueError("Relation assertion hash or identity mismatch")
        events.append((sequence, payload))
    return events


def _replay(events: list[tuple[int, dict]], profile: dict) -> dict[str, dict]:
    active = {}
    seen = set()
    for _, assertion in events:
        rid = assertion["relation_id"]
        if assertion["profile"] != {
            key: profile[key] for key in ("schema_version", "profile_id", "version", "sha256")
        }:
            raise ValueError("Relation assertion profile mismatch")
        if (
            assertion["review"]["status"] != "approved"
            or not assertion["review"]["confirmed_by"].strip()
            or assertion["source"]["kind"] not in _SOURCE_KINDS
        ):
            raise ValueError("Relation assertion is not explicitly user confirmed")
        operation = assertion["operation"]
        if operation == "assert":
            if rid in seen or assertion["supersedes_assertion_id"] is not None:
                raise ValueError("Relation ID already asserted")
            seen.add(rid)
            active[rid] = assertion
            continue
        old = active.get(rid)
        if old is None or old["assertion_id"] != assertion["supersedes_assertion_id"]:
            raise ValueError("Superseded assertion is not the currently active revision")
        if (
            old["subject_type"] != assertion["subject_type"]
            or old["subject_entity_id"] != assertion["subject_entity_id"]
            or old["predicate"] != assertion["predicate"]
        ):
            raise ValueError("Relation replacement cannot change predicate or subject")
        if operation == "retract":
            del active[rid]
        elif operation == "replace":
            active[rid] = assertion
        else:
            raise ValueError("Unsupported relation assertion operation")
    return active


def _check_current(db: sqlite3.Connection, sha: str, active: dict[str, dict]) -> None:
    actual = dict(
        db.execute(
            "SELECT relation_id, assertion_id FROM current_relations WHERE pipeline_sha256=?",
            (sha,),
        ).fetchall()
    )
    expected = {rid: document["assertion_id"] for rid, document in active.items()}
    if actual != expected:
        raise ValueError("Current relations disagree with append-only assertion history")


def _entity_frames(project: Path, sha: str) -> dict[str, pl.DataFrame]:
    from fairmorph_engine.core.entity_projection import (
        project_entities,
        require_confirmation,
        verify_projection_evidence,
    )
    from fairmorph_engine.core.pipeline import execute_pipeline
    from fairmorph_engine.core.pipeline_run import load_pipeline, resolve_resources

    config = load_pipeline(project, sha)
    if "entities" not in config:
        raise ValueError("Relation assertions require a confirmed entity projection")
    confirmation = require_confirmation(project, sha)
    frames, _ = resolve_resources(project, config)
    tables = execute_pipeline(
        {"schema_version": config["schema_version"], "steps": config["steps"]},
        frames,
    )
    verify_projection_evidence(project, config, tables, confirmation)
    return project_entities(config, tables)


def _check_active(
    active: dict[str, dict], profile: dict, entities: dict[str, pl.DataFrame]
) -> None:
    ids = {kind: set(frame.get_column("entity_id").to_list()) for kind, frame in entities.items()}
    by_subject = {}
    by_object = {}
    seen_edges = set()
    parent = {}
    for assertion in active.values():
        predicate = assertion["predicate"]
        rule = profile["predicates"].get(predicate)
        if rule is None:
            raise ValueError("Predicate is not permitted by the relation profile")
        subject_kind, object_kind = assertion["subject_type"], assertion["object_type"]
        subject, object_id = assertion["subject_entity_id"], assertion["object_entity_id"]
        if (subject_kind, object_kind) != (rule["subject"], rule["object"]):
            raise ValueError("Relation entity types do not match predicate contract")
        if subject not in ids.get(subject_kind, set()):
            raise ValueError("Relation subject is not an existing projected entity")
        if object_id not in ids.get(object_kind, set()):
            raise ValueError("Relation object is not an existing projected entity")
        edge = (predicate, subject, object_id)
        if edge in seen_edges:
            raise ValueError("Duplicate active relation")
        seen_edges.add(edge)
        by_subject[(predicate, subject)] = by_subject.get((predicate, subject), 0) + 1
        by_object[(predicate, object_id)] = by_object.get((predicate, object_id), 0) + 1
        if (
            rule.get("max_objects_per_subject") is not None
            and by_subject[(predicate, subject)] > rule["max_objects_per_subject"]
        ):
            raise ValueError("Relation cardinality conflict for subject")
        if (
            rule.get("max_subjects_per_object") is not None
            and by_object[(predicate, object_id)] > rule["max_subjects_per_object"]
        ):
            raise ValueError("Relation cardinality conflict for object")
        # Do not silently contradict an explicitly mapped reference column.
        reference = {
            "parent_event": ("SamplingEvent", "parent_event_ref", subject, object_id),
            "event_occurrence": ("Occurrence", "sampling_event_ref", object_id, subject),
            "event_measurement": (
                "MeasurementOrFact",
                "sampling_event_ref",
                object_id,
                subject,
            ),
            "occurrence_measurement": (
                "MeasurementOrFact",
                "occurrence_ref",
                object_id,
                subject,
            ),
        }.get(predicate)
        if reference is not None:
            kind, column, row_id, expected = reference
            frame = entities[kind]
            if column in frame.columns:
                actual = frame.filter(pl.col("entity_id") == row_id)[column][0]
                if actual is not None and actual != expected:
                    raise ValueError("Relation conflicts with confirmed entity field mapping")
        if rule.get("acyclic"):
            parent[subject] = object_id
    for node in parent:
        visited = set()
        current = node
        while current in parent:
            if current in visited:
                raise ValueError("Cyclic parent_event hierarchy")
            visited.add(current)
            current = parent[current]


def _valid_time(start: str | None, end: str | None) -> dict:
    def instant(value: str | None) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Invalid ISO-8601 relation validity time")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Invalid ISO-8601 relation validity time") from error
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    beginning, ending = instant(start), instant(end)
    if beginning is not None and ending is not None and beginning >= ending:
        raise ValueError("Relation valid_from must precede valid_to")
    return {"valid_from": start, "valid_to": end}


def _assertion(
    sha: str,
    profile: dict,
    *,
    operation: str,
    relation_id: str,
    previous: dict | None,
    subject_type: str,
    subject_entity_id: str,
    predicate: str,
    object_type: str,
    object_entity_id: str,
    confirmed_by: str,
    source_reference: str,
    source_kind: str,
    valid_from: str | None,
    valid_to: str | None,
) -> dict:
    if not confirmed_by or not confirmed_by.strip():
        raise ValueError("Explicit confirming user identity required")
    if not source_reference or not source_reference.strip():
        raise ValueError("Explicit relation source reference required")
    if source_kind not in _SOURCE_KINDS:
        raise ValueError("Unknown relation source kind")
    if not all(
        isinstance(value, str) and value.strip() for value in (subject_entity_id, object_entity_id)
    ):
        raise ValueError("Relation requires explicit technical entity identities")
    valid_time = _valid_time(valid_from, valid_to)
    return {
        "schema_version": "fairmorph.relation-assertion/1",
        "assertion_id": "assert-" + uuid.uuid4().hex,
        "relation_id": relation_id,
        "configuration_sha256": sha,
        "operation": operation,
        "supersedes_assertion_id": (previous["assertion_id"] if previous is not None else None),
        "subject_type": subject_type,
        "subject_entity_id": subject_entity_id,
        "predicate": predicate,
        "object_type": object_type,
        "object_entity_id": object_entity_id,
        "source": {"kind": source_kind, "reference": source_reference.strip()},
        "review": {"status": "approved", "confirmed_by": confirmed_by.strip()},
        "recorded_at": datetime.now(UTC).isoformat(),
        "valid_time": valid_time,
        "profile": {
            key: profile[key] for key in ("schema_version", "profile_id", "version", "sha256")
        },
    }


def _append(
    project: Path,
    sha: str,
    *,
    operation: str,
    predicate: str | None = None,
    subject_entity_id: str | None = None,
    object_entity_id: str | None = None,
    relation_id: str | None = None,
    confirmed_by: str,
    source_reference: str,
    source_kind: str = "user_confirmed",
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict:
    profile = relation_profile()
    # The validator does not manufacture any source entity or scientific meaning.
    entities = _entity_frames(project, sha)
    with _catalog(project) as db:
        _ensure_tables(db)
        db.execute("BEGIN IMMEDIATE")
        events = _events(db, sha, None)
        active = _replay(events, profile)
        _check_current(db, sha, active)
        _check_active(active, profile, entities)
        if operation == "assert":
            if predicate not in profile["predicates"]:
                raise ValueError("Predicate is not permitted by the relation profile")
            previous = None
            relation_id = "rel-" + uuid.uuid4().hex
            spec = profile["predicates"][predicate]
            subject_type, object_type = spec["subject"], spec["object"]
        else:
            previous = active.get(relation_id)
            if previous is None:
                raise ValueError("Relation is not active (or belongs to another pipeline)")
            predicate = previous["predicate"]
            subject_type = previous["subject_type"]
            subject_entity_id = previous["subject_entity_id"]
            object_type = previous["object_type"]
            if operation == "retract":
                object_entity_id = previous["object_entity_id"]
            elif operation != "replace":
                raise ValueError("Unsupported relation operation")
            # A target correction must not silently erase scientific validity.
            if valid_from is None:
                valid_from = previous["valid_time"]["valid_from"]
            if valid_to is None:
                valid_to = previous["valid_time"]["valid_to"]
        document = _assertion(
            sha,
            profile,
            operation=operation,
            relation_id=relation_id,
            previous=previous,
            subject_type=subject_type,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            object_type=object_type,
            object_entity_id=object_entity_id,
            confirmed_by=confirmed_by,
            source_reference=source_reference,
            source_kind=source_kind,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        proposed = dict(active)
        if operation == "retract":
            del proposed[relation_id]
        else:
            proposed[relation_id] = document
        _check_active(proposed, profile, entities)
        db.execute(
            "INSERT INTO relation_assertions("
            "assertion_id,relation_id,pipeline_sha256,operation,"
            "supersedes_assertion_id,payload_json,payload_sha256"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                document["assertion_id"],
                relation_id,
                sha,
                operation,
                document["supersedes_assertion_id"],
                json.dumps(document, sort_keys=True, ensure_ascii=False),
                digest(document),
            ),
        )
        if operation == "assert":
            db.execute(
                "INSERT INTO current_relations(relation_id,pipeline_sha256,assertion_id)"
                " VALUES (?, ?, ?)",
                (relation_id, sha, document["assertion_id"]),
            )
        elif operation == "replace":
            db.execute(
                "UPDATE current_relations SET assertion_id=? WHERE relation_id=?",
                (document["assertion_id"], relation_id),
            )
        else:
            db.execute("DELETE FROM current_relations WHERE relation_id=?", (relation_id,))
    return {**document, "assertion_sha256": digest(document)}


def assert_relation(
    project: Path,
    pipeline_sha256: str,
    predicate: str,
    subject_entity_id: str,
    object_entity_id: str,
    confirmed_by: str,
    source_reference: str,
    *,
    source_kind: str = "user_confirmed",
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict:
    """Record one confirmed assertion; no second/independent reviewer required."""
    return _append(
        project,
        pipeline_sha256,
        operation="assert",
        predicate=predicate,
        subject_entity_id=subject_entity_id,
        object_entity_id=object_entity_id,
        confirmed_by=confirmed_by,
        source_reference=source_reference,
        source_kind=source_kind,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def replace_relation(
    project: Path,
    pipeline_sha256: str,
    relation_id: str,
    new_object_entity_id: str,
    confirmed_by: str,
    source_reference: str,
    *,
    source_kind: str = "user_confirmed",
) -> dict:
    """Re-point an existing relation by a new assertion, never an overwrite."""
    return _append(
        project,
        pipeline_sha256,
        operation="replace",
        relation_id=relation_id,
        object_entity_id=new_object_entity_id,
        confirmed_by=confirmed_by,
        source_reference=source_reference,
        source_kind=source_kind,
    )


def retract_relation(
    project: Path,
    pipeline_sha256: str,
    relation_id: str,
    confirmed_by: str,
    source_reference: str,
) -> dict:
    """Revoke a relation with an append-only event, preserving old RUNs."""
    return _append(
        project,
        pipeline_sha256,
        operation="retract",
        relation_id=relation_id,
        confirmed_by=confirmed_by,
        source_reference=source_reference,
    )


def relation_snapshot(
    project: Path,
    pipeline_sha256: str,
    *,
    through_sequence: int | None = None,
    entity_frames: dict[str, pl.DataFrame] | None = None,
) -> dict:
    """Hash the approved current set as of a recorded, immutable log sequence."""
    from fairmorph_engine.core.pipeline_run import load_pipeline

    config = load_pipeline(project, pipeline_sha256)
    if "entities" not in config:
        raise ValueError("Relations require a semantic entity pipeline")
    profile = relation_profile()
    with _catalog(project) as db:
        _ensure_tables(db)
        if through_sequence is not None and (
            type(through_sequence) is not int or through_sequence < 0
        ):
            raise ValueError("Invalid relation snapshot sequence")
        events = _events(db, pipeline_sha256, through_sequence)
        active = _replay(events, profile)
        if through_sequence is None:
            _check_current(db, pipeline_sha256, active)
        cutoff = (
            through_sequence if through_sequence is not None else (events[-1][0] if events else 0)
        )
    if entity_frames is not None:
        _check_active(active, profile, entity_frames)
    result = {
        "schema_version": "fairmorph.relations.snapshot/1",
        "configuration_sha256": pipeline_sha256,
        "profile": {
            key: profile[key] for key in ("schema_version", "profile_id", "version", "sha256")
        },
        "through_sequence": cutoff,
        "active_assertions": [
            {"assertion_sha256": digest(doc), "assertion": doc} for _, doc in sorted(active.items())
        ],
    }
    return {**result, "snapshot_sha256": digest(result)}
