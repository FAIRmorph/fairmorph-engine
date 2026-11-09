"""Register an external, reviewed CSV mapping profile without scientific defaults.

Staging a profile is not an approval. Reviewers explicitly approve the exact
field revisions and mapping hash; source bytes are pinned before registration.
"""

import csv
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from fairmorph_engine.core.registry import (
    _catalog,
    _ensure_revision,
    define_field,
    digest,
    mapping_snapshot,
    register_mapping,
)


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _validate(document: dict) -> None:
    target = Path(__file__).resolve().parents[1] / "contracts" / "csv-mapping-profile.schema.json"
    schema = json.loads(target.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)


def stage_csv_mapping(project: Path, resource_id: str, profile_file: Path) -> dict:
    """Stage a dataset-neutral mapping; do not create any review decisions."""
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    _validate(profile)
    with _catalog(project) as db:
        row = db.execute(
            "SELECT object_sha256 FROM source_resources WHERE resource_id=?", (resource_id,)
        ).fetchone()
    if row is None:
        raise ValueError("Mapping source resource is not imported")
    checksum = row[0]
    if checksum != profile["source_sha256"]:
        raise ValueError("Source bytes differ from declared mapping profile")
    source = project / "objects" / "sha256" / checksum[:2] / checksum
    if not source.is_file() or source.is_symlink() or _file_digest(source) != checksum:
        raise ValueError("Imported source object is missing or modified")
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, None)
    required = [profile["identifier"], *(x["source_column"] for x in profile["fields"])]
    if not header or len(header) != len(set(header)) or any(x not in header for x in required):
        raise ValueError("Source header does not contain unique mapping columns")
    if len(required) != len(set(required)):
        raise ValueError("Mapping identifier and field columns must be distinct")
    bindings = []
    for item in profile["fields"]:
        definition = {
            "description": item["description"],
            "semantic_status": "defined",
            "definition_source": item["definition_source"],
            "counting_unit": item["counting_unit"],
            "value_semantics": {
                "missing_values": item["missing_values"],
                "zero_meaning": item["zero_meaning"],
            },
        }
        revision = define_field(project, resource_id, f"csv:{item['source_column']}", definition)
        bindings.append(
            {
                "source_field_id": revision["source_field_id"],
                "definition_revision_id": revision["revision_id"],
                "source_column": item["source_column"],
                "target_field": item["target_field"],
                "attributes": item.get("attributes", {}),
            }
        )
    mapping = {
        "mapping_id": profile["mapping_id"],
        "version": profile["version"],
        "operation": profile["operation"],
        "source_resource_id": resource_id,
        "profile_sha256": _file_digest(profile_file),
        "identifier": profile["identifier"],
        "empty_cell_policy": profile["empty_cell_policy"],
        "zero_cell_policy": profile["zero_cell_policy"],
        "bindings": bindings,
        "acceptance": profile.get("acceptance", {}),
    }
    staged = register_mapping(project, mapping)
    return {
        "mapping_sha256": staged["sha256"],
        "mapping_id": staged["mapping_id"],
        "version": staged["version"],
        "status": "draft",
        "field_definition_revision_ids": [x["definition_revision_id"] for x in bindings],
        "resource_id": resource_id,
        "source_sha256": checksum,
    }


def approve_staged_mapping(project: Path, mapping_sha256: str, reviewer: str) -> dict:
    """Approve matching field revisions and mapping in one SQLite transaction.

    Explicit approval is one action. A failure must not leave half the profile
    approved, and a second approval of the same revision is never implicit.
    """
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Explicit reviewer identity required")
    timestamp = datetime.now(UTC).isoformat()
    mapping_review_id = str(uuid.uuid4())
    with _catalog(project) as db:
        row = db.execute(
            "SELECT content_json FROM mapping_versions WHERE mapping_sha256=?",
            (mapping_sha256,),
        ).fetchone()
        if row is None:
            raise ValueError("Mapping version does not exist")
        mapping = json.loads(row[0])
        if digest(mapping) != mapping_sha256:
            raise ValueError("Mapping revision has been modified")
        if db.execute(
            "SELECT 1 FROM mapping_reviews WHERE mapping_sha256=?", (mapping_sha256,)
        ).fetchone():
            raise ValueError("Mapping version has already been reviewed")
        revision_ids = [x["definition_revision_id"] for x in mapping["bindings"]]
        if len(revision_ids) != len(set(revision_ids)):
            raise ValueError("Multiple bindings refer to one field definition revision")
        for binding in mapping["bindings"]:
            rid = binding["definition_revision_id"]
            field_id, definition = _ensure_revision(db, rid)
            if binding["source_field_id"] != field_id:
                raise ValueError("Mapping field identity mismatch")
            if definition.get("semantic_status") != "defined":
                raise ValueError("Unresolved semantics cannot be approved")
            if (
                not isinstance(definition.get("description"), str)
                or not definition["description"].strip()
            ):
                raise ValueError("Field approval requires substantive description")
            if db.execute(
                "SELECT 1 FROM field_definition_reviews WHERE revision_id=?", (rid,)
            ).fetchone():
                raise ValueError("Field revision has already been reviewed")
            current = db.execute(
                "SELECT revision_id FROM current_field_definitions WHERE source_field_id=?",
                (field_id,),
            ).fetchone()
            if current is None or current[0] != rid:
                raise ValueError("Mapping must bind the current field revision")
            if binding["target_field"] == "individualCount" and (
                definition.get("counting_unit") != "individual"
                or definition["value_semantics"].get("zero_meaning") == "unknown"
            ):
                raise ValueError("individualCount needs explicit count semantics")
        for rid in revision_ids:
            db.execute(
                "INSERT INTO field_definition_reviews VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), rid, "approved", reviewer, timestamp),
            )
        db.execute(
            "INSERT INTO mapping_reviews VALUES (?, ?, ?, ?, ?)",
            (mapping_review_id, mapping_sha256, "approved", reviewer, timestamp),
        )
    # Deriving a verified immutable input snapshot after the committed review
    # does not create or modify any other registry state.
    snapshot = mapping_snapshot(project, mapping_sha256)
    return {
        "mapping_sha256": mapping_sha256,
        "review_id": mapping_review_id,
        "reviewer": reviewer,
        "reviewed_at": timestamp,
        "status": "approved",
        "mapping_snapshot": snapshot,
    }
