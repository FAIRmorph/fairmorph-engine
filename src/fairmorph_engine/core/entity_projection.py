"""Version-pinned semantic projections with explicit user confirmation.

Scientific meaning is supplied by confirmed SourceFieldDefinition revisions.
The engine validates provenance; it never infers an ecological interpretation.
"""

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from fairmorph_engine.core.registry import (
    _catalog,
    _ensure_revision,
    _field_schema,
    digest,
)

ENTITIES = ("Observation", "Event", "Occurrence", "MeasurementOrFact")
ID = {"Observation": "observationID", "Event": "eventID", "Occurrence": "occurrenceID", "MeasurementOrFact": "measurementID"}
RELATIONS = {
    "Observation": {"eventID": "Event"},
    "Occurrence": {"eventID": "Event", "observationID": "Observation"},
    "MeasurementOrFact": {"eventID": "Event", "occurrenceID": "Occurrence"},
}
_SHA = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def validate_entities(config: dict) -> None:
    """Check the explicit contract before any project or catalog access."""
    entities = config.get("entities")
    if not isinstance(entities, dict) or not entities or set(entities) - set(ENTITIES):
        raise ValueError("Entities must be an explicit, nonempty supported subset")
    tables = set(config["resources"]) | {step["output"] for step in config["steps"]}
    for kind, spec in entities.items():
        if not isinstance(spec, dict) or set(spec) != {
            "source_table",
            "description",
            "fields",
        }:
            raise ValueError(f"Invalid {kind} projection contract")
        if spec["source_table"] not in tables:
            raise ValueError(f"Unknown {kind} source table")
        if not isinstance(spec["description"], str) or len(spec["description"].strip()) < 12:
            raise ValueError(f"{kind} requires a substantive user description")
        fields = spec["fields"]
        if not isinstance(fields, dict) or ID[kind] not in fields:
            raise ValueError(f"{kind} requires an explicit {ID[kind]} binding")
        for target, binding in fields.items():
            if not isinstance(target, str) or not _NAME.fullmatch(target):
                raise ValueError("Invalid semantic target field")
            if not isinstance(binding, dict) or set(binding) != {
                "column",
                "description",
                "source_definitions",
            }:
                raise ValueError(f"{kind}.{target} requires an explicit field contract")
            if not isinstance(binding["column"], str) or not binding["column"]:
                raise ValueError("Missing source column")
            if (
                not isinstance(binding["description"], str)
                or len(binding["description"].strip()) < 12
            ):
                raise ValueError("Target field requires an explicit semantic rationale")
            definitions = binding["source_definitions"]
            if not isinstance(definitions, list) or not definitions:
                raise ValueError("Target field requires pinned SourceFieldDefinitions")
            seen = set()
            for definition in definitions:
                if not isinstance(definition, dict) or set(definition) != {
                    "source_resource_id",
                    "source_field_id",
                    "definition_revision_id",
                    "definition_sha256",
                }:
                    raise ValueError("Incomplete SourceFieldDefinition pin")
                if any(not isinstance(value, str) or not value for value in definition.values()):
                    raise ValueError("Invalid SourceFieldDefinition identity")
                if not _SHA.fullmatch(definition["definition_sha256"]):
                    raise ValueError("Invalid SourceFieldDefinition SHA-256")
                identifier = definition["definition_revision_id"]
                if identifier in seen:
                    raise ValueError("Duplicate source definition pin")
                seen.add(identifier)
    for kind, references in RELATIONS.items():
        if kind not in entities:
            continue
        for foreign_key, parent in references.items():
            if foreign_key in entities[kind]["fields"] and parent not in entities:
                raise ValueError(f"{kind}.{foreign_key} requires an explicit {parent} projection")


def _expr_sources(expression: dict, columns: dict) -> set:
    name, value = next(iter(expression.items()))
    if name == "column":
        return set(columns[value])
    if name == "literal":
        return set()
    if name == "concat":
        result = set()
        for item in value:
            result.update(_expr_sources(item, columns))
        return result
    if name == "when":
        result = _expr_sources(value["then"], columns)
        result.update(_expr_sources(value["otherwise"], columns))
        result.update(columns[value["condition"]["column"]])
        return result
    raise ValueError("Unsupported derived-field provenance")


def _column_provenance(config: dict, tables: dict) -> dict:
    """Trace physical source columns through the allowlisted DAG, not names alone."""
    provenance = {}
    for name, resource in config["resources"].items():
        resource_id = resource["resource_id"]
        provenance[name] = {
            col: {(resource_id, col)} for col in tables[name].columns
        }
    pending = {step["id"]: step for step in config["steps"]}
    while pending:
        ready = sorted(
            (s for s in pending.values() if all(n in provenance for n in s["inputs"])),
            key=lambda s: s["id"],
        )
        if not ready:
            raise ValueError("Unresolved provenance dependencies")
        for step in ready:
            operator = step["operator"]
            params = step["parameters"]
            inputs = [provenance[n] for n in step["inputs"]]
            original = inputs[0]
            if operator == "table.select/1":
                output = {c: set(original[c]) for c in params["columns"]}
            elif operator in {"table.filter/1", "table.distinct/1"}:
                output = {c: set(v) for c, v in original.items()}
            elif operator == "table.derive/1":
                output = {c: set(v) for c, v in original.items()}
                for col, expression in params["expressions"].items():
                    output[col] = _expr_sources(expression, original)
            elif operator == "table.join/1":
                output = {c: set(v) for c, v in original.items()}
                right = inputs[1]
                for col, values in right.items():
                    if col in params["keys"]:
                        continue
                    name = col if col not in original else col + "_right"
                    if name in output:
                        raise ValueError("Ambiguous join column provenance")
                    output[name] = set(values)
            elif operator == "table.unpivot/1":
                index = params["identifiers"]
                union = set()
                for col in params["columns"]:
                    union.update(original[col])
                output = {col: set(original[col]) for col in index}
                output[params["variable"]] = set(union)
                output[params["value"]] = set(union)
            else:
                raise ValueError("Unsupported projection provenance operation")
            if set(output) != set(tables[step["output"]].columns):
                raise ValueError("DAG field provenance does not match executed output")
            provenance[step["output"]] = output
            del pending[step["id"]]
    return provenance


def _confirmation_table(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS projection_confirmations ("
        "configuration_sha256 TEXT PRIMARY KEY, "
        "confirmed_by TEXT NOT NULL, confirmed_at TEXT NOT NULL, "
        "evidence_json TEXT NOT NULL, evidence_sha256 TEXT NOT NULL)"
    )


def _evidence(project: Path, config: dict, tables: dict) -> dict:
    """Preflight every projected field against current, confirmed source revisions."""
    provenance = _column_provenance(config, tables)
    revisions = {}
    bindings = []
    with _catalog(project) as db:
        for kind, spec in config["entities"].items():
            for target, binding in spec["fields"].items():
                source = provenance[spec["source_table"]].get(binding["column"])
                if not source:
                    raise ValueError(f"{kind}.{target} has no traceable source columns")
                pinned = set()
                for pin in binding["source_definitions"]:
                    rid = pin["definition_revision_id"]
                    field_id, definition = _ensure_revision(db, rid)
                    if (
                        field_id != pin["source_field_id"]
                        or definition["source_resource_id"] != pin["source_resource_id"]
                        or digest(definition) != pin["definition_sha256"]
                    ):
                        raise ValueError("SourceFieldDefinition identity or hash mismatch")
                    resource_id = definition["source_resource_id"]
                    locator = definition["field_locator"]
                    resource_names = {
                        name: info["format"]
                        for name, info in config["resources"].items()
                        if info["resource_id"] == resource_id
                    }
                    if not resource_names:
                        raise ValueError("Field definition references an unbound resource")
                    original_column = None
                    if locator.get("kind") == "column":
                        for fmt in resource_names.values():
                            prefix = "csv:" if fmt == "csv" else "parquet:"
                            if locator["path"].startswith(prefix):
                                original_column = locator["path"][len(prefix):]
                                break
                    if original_column is None or (resource_id, original_column) not in source:
                        raise ValueError("Field definition does not match source-column provenance")
                    if definition["semantic_status"] != "defined":
                        raise ValueError("Unresolved source field semantics")
                    review = db.execute(
                        "SELECT review_id, decision, reviewer, reviewed_at "
                        "FROM field_definition_reviews WHERE revision_id=?",
                        (rid,),
                    ).fetchone()
                    if review is None or review[1] != "approved":
                        raise ValueError("SourceFieldDefinition requires explicit user confirmation")
                    current = db.execute(
                        "SELECT revision_id FROM current_field_definitions WHERE source_field_id=?",
                        (field_id,),
                    ).fetchone()
                    if current is None or current[0] != rid:
                        raise ValueError("Projection must bind current field-definition revisions")
                    if target == "individualCount":
                        if (
                            definition.get("counting_unit") != "individual"
                            or definition["value_semantics"]["zero_meaning"] == "unknown"
                        ):
                            raise ValueError("individualCount requires confirmed count/zero semantics")
                    pinned.add((resource_id, original_column))
                    revisions[rid] = {
                        "revision_id": rid,
                        "source_field_id": field_id,
                        "source_resource_id": resource_id,
                        "definition_sha256": pin["definition_sha256"],
                        "definition": definition,
                        "confirmation": {
                            "review_id": review[0],
                            "decision": review[1],
                            "confirmed_by": review[2],
                            "confirmed_at": review[3],
                        },
                    }
                if pinned != source:
                    raise ValueError(
                        f"{kind}.{target} source definitions do not cover exact DAG provenance"
                    )
                bindings.append({
                    "entity": kind,
                    "target_field": target,
                    "source_table": spec["source_table"],
                    "source_column": binding["column"],
                    "description": binding["description"],
                    "definition_revision_ids": sorted(pin["definition_revision_id"] for pin in binding["source_definitions"]),
                })
    return {
        "schema_version": "fairmorph.projection.evidence/1",
        "field_definition_schema_sha256": digest(_field_schema()),
        "field_definitions": [revisions[r] for r in sorted(revisions)],
        "bindings": sorted(bindings, key=lambda b: (b["entity"], b["target_field"])),
    }


def confirm_projection(project: Path, sha: str, confirmed_by: str) -> dict:
    """Record one immutable user decision; no independent reviewer is required."""
    from fairmorph_engine.core.pipeline import execute_pipeline
    from fairmorph_engine.core.pipeline_run import load_pipeline, resolve_resources
    from fairmorph_engine.core.registry import canonical_bytes

    if not isinstance(confirmed_by, str) or not confirmed_by.strip():
        raise ValueError("Explicit confirming user identity required")
    config = load_pipeline(project, sha)
    if "entities" not in config:
        raise ValueError("Pipeline does not declare semantic entity projections")
    frames, _ = resolve_resources(project, config)
    tables = execute_pipeline(
        {"schema_version": config["schema_version"], "steps": config["steps"]},
        frames,
    )
    evidence = _evidence(project, config, tables)
    timestamp = datetime.now(UTC).isoformat()
    with _catalog(project) as db:
        _confirmation_table(db)
        if db.execute(
            "SELECT 1 FROM projection_confirmations WHERE configuration_sha256=?",
            (sha,),
        ).fetchone():
            raise ValueError("Projection already confirmed; register a new revision")
        db.execute(
            "INSERT INTO projection_confirmations VALUES (?, ?, ?, ?, ?)",
            (sha, confirmed_by.strip(), timestamp, canonical_bytes(evidence).decode(), digest(evidence)),
        )
    return require_confirmation(project, sha)


def require_confirmation(project: Path, sha: str) -> dict:
    """Resolve and verify revision-bound evidence from the project catalog."""
    if not _SHA.fullmatch(sha):
        raise ValueError("Invalid projection configuration SHA-256")
    with _catalog(project) as db:
        _confirmation_table(db)
        row = db.execute(
            "SELECT confirmed_by, confirmed_at, evidence_json, evidence_sha256 "
            "FROM projection_confirmations WHERE configuration_sha256=?",
            (sha,),
        ).fetchone()
        if row is None:
            raise ValueError("Projection requires explicit user confirmation")
        evidence = json.loads(row[2])
        if digest(evidence) != row[3]:
            raise ValueError("Corrupted projection confirmation evidence")
        for item in evidence["field_definitions"]:
            field_id, definition = _ensure_revision(db, item["revision_id"])
            if field_id != item["source_field_id"] or definition != item["definition"]:
                raise ValueError("Projection field-definition evidence mismatch")
            review = db.execute(
                "SELECT decision, reviewer, reviewed_at FROM field_definition_reviews "
                "WHERE review_id=? AND revision_id=?",
                (item["confirmation"]["review_id"], item["revision_id"]),
            ).fetchone()
            if review is None or review != (
                item["confirmation"]["decision"],
                item["confirmation"]["confirmed_by"],
                item["confirmation"]["confirmed_at"],
            ) or review[0] != "approved":
                raise ValueError("Projection field confirmation was modified")
    return {
        "schema_version": "fairmorph.projection.confirmation/1",
        "configuration_sha256": sha,
        "confirmed_by": row[0],
        "confirmed_at": row[1],
        "evidence_sha256": row[3],
        "evidence": evidence,
    }


def verify_projection_evidence(project: Path, config: dict, tables: dict, confirmation: dict) -> None:
    """Require exact source-field provenance at RUN execution."""
    current = _evidence(project, config, tables)
    if digest(current) != confirmation["evidence_sha256"]:
        raise ValueError("Projection source-field definitions or provenance changed")


def project_entities(config: dict, tables: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Materialize only declared entities, with no implicit scientific interpretation."""
    validate_entities(config)
    result = {}
    for kind, spec in config["entities"].items():
        frame = tables[spec["source_table"]]
        fields = spec["fields"]
        missing = {b["column"] for b in fields.values()} - set(frame.columns)
        if missing:
            raise ValueError(f"{kind} missing source columns: {sorted(missing)}")
        output = frame.select(
            [pl.col(binding["column"]).alias(target) for target, binding in fields.items()]
        )
        identity = output.get_column(ID[kind])
        if not output.height or identity.null_count() or identity.n_unique() != output.height:
            raise ValueError(f"{kind} {ID[kind]} must be unique and non-null")
        if identity.dtype == pl.String and identity.str.strip_chars().eq("").any():
            raise ValueError(f"{kind} {ID[kind]} cannot be blank")
        if kind == "Event" and "eventID" in output.columns:
            ids = output.get_column("eventID")
            if ids.null_count() or ids.n_unique() != output.height:
                raise ValueError("Event eventID must be unique and non-null when mapped")
        result[kind] = output
    for child, references in RELATIONS.items():
        if child not in result:
            continue
        for foreign_key, parent in references.items():
            if foreign_key not in result[child].columns:
                continue
            parent_key = ID[parent]
            if parent not in result or parent_key not in result[parent].columns:
                raise ValueError(f"{child}.{foreign_key} has no mapped parent identity")
            child_ids = result[child].get_column(foreign_key)
            parent_ids = result[parent].get_column(parent_key)
            if child_ids.null_count() or child_ids.dtype != parent_ids.dtype:
                raise ValueError(f"{child}.{foreign_key} contains missing/incompatible keys")
            if set(child_ids.to_list()) - set(parent_ids.to_list()):
                raise ValueError(f"{child}.{foreign_key} contains orphan references")
    if "Event" in result and "parentEventID" in result["Event"].columns:
        event = result["Event"]
        if "eventID" not in event.columns:
            raise ValueError("parentEventID requires explicit eventID")
        parents = dict(zip(event["eventID"].to_list(), event["parentEventID"].to_list(), strict=True))
        if set(parents.values()) - {None} - set(parents):
            raise ValueError("Event parentEventID contains orphan references")
        for event_id in parents:
            visited = set()
            current = event_id
            while current is not None:
                if current in visited:
                    raise ValueError("Cyclic parentEventID hierarchy")
                visited.add(current)
                current = parents[current]
    return result
