"""Version-pinned field semantics and approved mapping registry (v0.12 foundation).

A technical import can exist without definitions or a mapping. Each definition
revision is append-only; review is a separate event and never an implicit default.
"""

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def canonical_bytes(document: dict) -> bytes:
    """PoC canonical UTF-8 serialization, not yet an external RFC 8785 claim."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest(document: dict) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def _catalog(project: Path) -> sqlite3.Connection:
    if not (project / "project.json").is_file():
        raise ValueError("Project must be initialized before registry use")
    db = project / "catalog" / "catalog.sqlite"
    if not db.is_file():
        raise ValueError("Project SQLite catalog missing")
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_fields (
          source_field_id TEXT PRIMARY KEY,
          resource_id TEXT NOT NULL REFERENCES source_resources(resource_id),
          field_locator TEXT NOT NULL,
          UNIQUE (resource_id, field_locator)
        );
        CREATE TABLE IF NOT EXISTS field_definition_revisions (
          revision_id TEXT PRIMARY KEY,
          source_field_id TEXT NOT NULL REFERENCES source_fields(source_field_id),
          parent_revision_id TEXT REFERENCES field_definition_revisions(revision_id),
          content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE (source_field_id, content_sha256)
        );
        CREATE TABLE IF NOT EXISTS field_definition_reviews (
          review_id TEXT PRIMARY KEY,
          revision_id TEXT NOT NULL REFERENCES field_definition_revisions(revision_id),
          decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
          reviewer TEXT NOT NULL, reviewed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS current_field_definitions (
          source_field_id TEXT PRIMARY KEY REFERENCES source_fields(source_field_id),
          revision_id TEXT NOT NULL REFERENCES field_definition_revisions(revision_id)
        );
        CREATE TABLE IF NOT EXISTS mapping_versions (
          mapping_sha256 TEXT PRIMARY KEY,
          mapping_id TEXT NOT NULL, version TEXT NOT NULL,
          content_json TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('draft', 'approved')),
          created_at TEXT NOT NULL, approved_by TEXT,
          UNIQUE (mapping_id, version)
        );
        CREATE TABLE IF NOT EXISTS mapping_reviews (
          review_id TEXT PRIMARY KEY,
          mapping_sha256 TEXT NOT NULL REFERENCES mapping_versions(mapping_sha256),
          decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
          reviewer TEXT NOT NULL, reviewed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mapping_field_bindings (
          mapping_sha256 TEXT NOT NULL REFERENCES mapping_versions(mapping_sha256),
          revision_id TEXT NOT NULL REFERENCES field_definition_revisions(revision_id),
          target_field TEXT NOT NULL,
          PRIMARY KEY(mapping_sha256, target_field)
        );
        """
    )
    return connection


def _ensure_revision(db: sqlite3.Connection, revision_id: str) -> tuple[str, dict]:
    row = db.execute(
        "SELECT source_field_id, content_json, content_sha256 FROM field_definition_revisions "
        "WHERE revision_id=?", (revision_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Unknown field definition revision")
    doc = json.loads(row[1])
    if digest(doc) != row[2]:
        raise ValueError("Corrupted field definition revision")
    return row[0], doc


def _field_schema() -> dict:
    source = Path(__file__).resolve().parents[1] / "contracts" / "SourceFieldDefinition.schema.json"
    return json.loads(source.read_text(encoding="utf-8"))


def define_field(project: Path, resource_id: str, locator: str, definition: dict,
                 parent_revision_id: str | None = None) -> dict:
    """Persist an immutable, schema-validated v0.12 field semantic draft."""
    if not locator or not isinstance(definition, dict):
        raise ValueError("Field locator and definition are required")
    if definition.get("review_status", "unreviewed") != "unreviewed":
        raise ValueError("Approval requires an independent review event")
    field_id = "field-" + hashlib.sha256(f"{resource_id}\0{locator}".encode()).hexdigest()
    project_id = json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"]
    field_locator = {"kind": "column", "path": locator}
    content = {
        "contract_version": "1.0.0",
        "dataset_id": project_id,
        "source_resource_id": resource_id,
        "source_field_id": field_id,
        "field_locator": field_locator,
        "semantic_status": "unresolved",
        "review_status": "unreviewed",
        "definition_source": "unknown",
        "description": None,
        "value_semantics": {"missing_values": [], "zero_meaning": "unknown"},
        **definition,
    }
    schema = _field_schema()
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(content)
    if content["source_field_id"] != field_id or content["source_resource_id"] != resource_id:
        raise ValueError("Source identity must not be overridden")
    if content["dataset_id"] != project_id or content["field_locator"] != field_locator:
        raise ValueError("Field locator and dataset identity must not be overridden")
    checksum = digest(content)
    revision_id = "definition-" + checksum
    now = datetime.now(UTC).isoformat()
    with _catalog(project) as db:
        if db.execute("SELECT 1 FROM source_resources WHERE resource_id=?", (resource_id,)).fetchone() is None:
            raise ValueError("Field must belong to an imported resource")
        previous = db.execute("SELECT revision_id FROM current_field_definitions WHERE source_field_id=?",
                              (field_id,)).fetchone()
        if previous and previous[0] != revision_id and parent_revision_id != previous[0]:
            raise ValueError("New definition must name current parent revision")
        if parent_revision_id and not previous:
            raise ValueError("Cannot specify a parent for the first revision")
        db.execute("INSERT OR IGNORE INTO source_fields VALUES (?, ?, ?)", (field_id, resource_id, locator))
        db.execute(
            "INSERT OR IGNORE INTO field_definition_revisions VALUES (?, ?, ?, ?, ?, ?)",
            (revision_id, field_id, parent_revision_id, canonical_bytes(content).decode(), checksum, now),
        )
        db.execute("INSERT INTO current_field_definitions VALUES (?, ?) ON CONFLICT(source_field_id) "
                   "DO UPDATE SET revision_id=excluded.revision_id", (field_id, revision_id))
    return {"source_field_id": field_id, "revision_id": revision_id,
            "content_sha256": checksum, "status": content["semantic_status"]}


def review_field(project: Path, revision_id: str, reviewer: str, decision: str) -> dict:
    """Append a review; approval requires useful semantics and an explicit reviewer."""
    if decision not in ("approved", "rejected") or not reviewer.strip():
        raise ValueError("A reviewer and an explicit review decision are required")
    with _catalog(project) as db:
        _, definition = _ensure_revision(db, revision_id)
        if decision == "approved":
            if not isinstance(definition.get("description"), str) or not definition["description"].strip():
                raise ValueError("A substantive description is required for approval")
            if definition["semantic_status"] != "defined":
                raise ValueError("Unresolved value semantics cannot be approved")
        prior = db.execute("SELECT decision FROM field_definition_reviews WHERE revision_id=? ORDER BY reviewed_at DESC",
                           (revision_id,)).fetchone()
        if prior is not None:
            raise ValueError("Revision already reviewed; create a new revision for a changed decision")
        review_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        db.execute("INSERT INTO field_definition_reviews VALUES (?, ?, ?, ?, ?)",
                   (review_id, revision_id, decision, reviewer, timestamp))
    return {"review_id": review_id, "revision_id": revision_id, "decision": decision,
            "reviewer": reviewer, "reviewed_at": timestamp}


def register_mapping(project: Path, mapping: dict) -> dict:
    """Register an immutable mapping draft; approval is a separate review event."""
    mapping_id, version = mapping.get("mapping_id"), mapping.get("version")
    bindings = mapping.get("bindings")
    if not isinstance(mapping_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", mapping_id):
        raise ValueError("Invalid mapping identifier")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Mapping version must be SemVer")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("Mapping must declare nonempty field bindings")
    targets = [b.get("target_field") for b in bindings]
    if len(set(targets)) != len(targets) or any(not isinstance(t, str) or not t for t in targets):
        raise ValueError("Duplicate or invalid mapping target")
    checksum = digest(mapping)
    with _catalog(project) as db:
        for binding in bindings:
            rid = binding.get("definition_revision_id")
            field_id, _ = _ensure_revision(db, rid)
            if binding.get("source_field_id") != field_id:
                raise ValueError("Binding points to another source field")
        existing = db.execute("SELECT mapping_sha256 FROM mapping_versions WHERE mapping_id=? AND version=?",
                              (mapping_id, version)).fetchone()
        if existing and existing[0] != checksum:
            raise ValueError("Mapping version is immutable; publish a new version")
        db.execute("INSERT OR IGNORE INTO mapping_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (checksum, mapping_id, version, canonical_bytes(mapping).decode(), "draft",
                    datetime.now(UTC).isoformat(), None))
        for binding in bindings:
            db.execute("INSERT OR IGNORE INTO mapping_field_bindings VALUES (?, ?, ?)",
                       (checksum, binding["definition_revision_id"], binding["target_field"]))
    return {"mapping_id": mapping_id, "version": version, "sha256": checksum, "status": "draft"}


def approve_mapping(project: Path, mapping_sha256: str, reviewer: str) -> dict:
    """Approve an unchanged mapping version after all field semantics were reviewed."""
    if not reviewer.strip():
        raise ValueError("Mapping approval needs reviewer")
    with _catalog(project) as db:
        row = db.execute("SELECT content_json FROM mapping_versions WHERE mapping_sha256=?",
                         (mapping_sha256,)).fetchone()
        if row is None:
            raise ValueError("Unknown mapping version")
        mapping = json.loads(row[0])
        if digest(mapping) != mapping_sha256:
            raise ValueError("Corrupted mapping version")
        if db.execute("SELECT 1 FROM mapping_reviews WHERE mapping_sha256=?", (mapping_sha256,)).fetchone():
            raise ValueError("Mapping version already reviewed; create a new version")
        for binding in mapping["bindings"]:
            rid = binding["definition_revision_id"]
            field_id, definition = _ensure_revision(db, rid)
            if field_id != binding["source_field_id"]:
                raise ValueError("Mapping field binding mismatch")
            reviews = db.execute("SELECT decision FROM field_definition_reviews WHERE revision_id=?",
                                 (rid,)).fetchall()
            if not reviews or reviews[-1][0] != "approved":
                raise ValueError("Mapping requires approved field definition revisions")
            current = db.execute("SELECT revision_id FROM current_field_definitions WHERE source_field_id=?",
                                 (field_id,)).fetchone()
            if current is None or current[0] != rid:
                raise ValueError("Mapping approval requires current field definitions")
            if binding["target_field"] == "individualCount":
                if definition.get("counting_unit") != "individual" or definition["value_semantics"]["zero_meaning"] == "unknown":
                    raise ValueError("individualCount requires confirmed count unit and zero semantics")
        review_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        db.execute("INSERT INTO mapping_reviews VALUES (?, ?, ?, ?, ?)",
                   (review_id, mapping_sha256, "approved", reviewer, timestamp))
    return {"mapping_sha256": mapping_sha256, "review_id": review_id,
            "reviewer": reviewer, "reviewed_at": timestamp, "status": "approved"}


def mapping_snapshot(project: Path, mapping_sha256: str) -> dict:
    """Produce an immutable RUN input reference; reject draft mappings."""
    with _catalog(project) as db:
        row = db.execute("SELECT content_json, status FROM mapping_versions WHERE mapping_sha256=?",
                         (mapping_sha256,)).fetchone()
        if row is None:
            raise ValueError("RUN requires an approved mapping version")
        approved = db.execute("SELECT decision FROM mapping_reviews WHERE mapping_sha256=?",
                              (mapping_sha256,)).fetchone()
        if not approved or approved[0] != "approved":
            raise ValueError("RUN requires an approved mapping version")
        mapping = json.loads(row[0])
        if digest(mapping) != mapping_sha256:
            raise ValueError("Mapping content hash mismatch")
        revisions = []
        source_resources = {}
        for binding in mapping["bindings"]:
            rid = binding["definition_revision_id"]
            _, definition = _ensure_revision(db, rid)
            reviews = db.execute("SELECT decision FROM field_definition_reviews WHERE revision_id=?", (rid,)).fetchall()
            if not reviews or reviews[-1][0] != "approved":
                raise ValueError("RUN mapping depends on unapproved definitions")
            resource_id = definition["source_resource_id"]
            source = db.execute("SELECT object_sha256 FROM source_resources WHERE resource_id=?",
                                (resource_id,)).fetchone()
            if source is None:
                raise ValueError("Mapped source resource is missing")
            source_resources[resource_id] = source[0]
            revisions.append({"revision_id": rid, "sha256": digest(definition)})
    return {"mapping_id": mapping["mapping_id"], "mapping_version": mapping["version"],
            "mapping_sha256": mapping_sha256, "field_definition_schema_sha256": digest(_field_schema()),
            "field_definition_revisions": revisions,
            "source_resources": [{"resource_id": rid, "object_sha256": checksum}
                                 for rid, checksum in sorted(source_resources.items())]}
