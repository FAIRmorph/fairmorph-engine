"""Offline versioned JSON Schema registry, with immutable local content pins.

New profiles do not require a SQLite core migration. Remote $refs are refused:
all schema dependencies must be shipped and reviewed locally.
"""

import json
import os
import re
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

from fairmorph_engine.core.registry import _catalog, canonical_bytes, digest

_ALLOWED_KINDS = frozenset({"core", "domain", "source", "export", "extension"})


def register_schema(
    project: Path,
    *,
    schema_id: str,
    schema_version: str,
    kind: str,
    schema: dict,
    status: str = "draft",
    reviewer: str | None = None,
) -> dict:
    """Store immutable schema bytes under their canonical hash in the project."""
    if not isinstance(schema_id, str) or not schema_id.startswith("https://"):
        raise ValueError("Schema ID must be an explicit HTTPS URI")
    if not isinstance(schema_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", schema_version):
        raise ValueError("Schema version must be SemVer")
    if kind not in _ALLOWED_KINDS or status not in {"draft", "approved", "deprecated"}:
        raise ValueError("Invalid schema kind or status")
    if status != "draft" and (reviewer is None or not reviewer.strip()):
        raise ValueError("Schema approval/deprecation requires an explicit reviewer")
    if not isinstance(schema, dict):
        raise ValueError("Schema must be a JSON object")
    if schema.get("$id") != schema_id:
        raise ValueError("Schema $id differs from registry identity")
    Draft202012Validator.check_schema(schema)
    for remote in _remote_refs(schema):
        raise ValueError(f"Remote or unsupported schema reference: {remote}")
    checksum = digest(schema)
    relative = f"registry/schemas/{checksum}.json"
    target = project / relative
    payload = canonical_bytes(schema)
    with _catalog(project) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS schema_versions (
            schema_id TEXT NOT NULL, schema_version TEXT NOT NULL,
            schema_sha256 TEXT NOT NULL PRIMARY KEY, kind TEXT NOT NULL,
            status TEXT NOT NULL, schema_path TEXT NOT NULL,
            reviewer TEXT, UNIQUE(schema_id, schema_version))"""
        )
        existing = db.execute(
            "SELECT schema_sha256, status FROM schema_versions WHERE schema_id=? AND schema_version=?",
            (schema_id, schema_version),
        ).fetchone()
        if existing and (existing[0] != checksum or existing[1] != status):
            raise ValueError(
                "Schema identity/version is immutable: content or review status differs"
            )
        if target.exists():
            if target.is_symlink() or target.read_bytes() != payload:
                raise ValueError("Stored registry schema bytes have changed")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = target.with_name(f".{uuid.uuid4().hex}.pending")
            try:
                with staging.open("xb") as stream:
                    stream.write(payload)
                os.replace(staging, target)
            finally:
                staging.unlink(missing_ok=True)
        db.execute(
            "INSERT OR IGNORE INTO schema_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (schema_id, schema_version, checksum, kind, status, relative, reviewer),
        )
    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "schema_sha256": checksum,
        "status": status,
        "schema_path": relative,
    }


def _remote_refs(document):
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "$ref" and (not isinstance(value, str) or not value.startswith("#")):
                yield value
            else:
                yield from _remote_refs(value)
    elif isinstance(document, list):
        for item in document:
            yield from _remote_refs(item)


def get_schema(project: Path, *, schema_id: str, schema_version: str) -> tuple[dict, str]:
    """Fetch only an exact pinned version, never 'latest'."""
    with _catalog(project) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS schema_versions (
            schema_id TEXT NOT NULL, schema_version TEXT NOT NULL,
            schema_sha256 TEXT NOT NULL PRIMARY KEY, kind TEXT NOT NULL,
            status TEXT NOT NULL, schema_path TEXT NOT NULL,
            reviewer TEXT, UNIQUE(schema_id, schema_version))"""
        )
        row = db.execute(
            "SELECT schema_sha256, schema_path FROM schema_versions WHERE schema_id=? AND schema_version=?",
            (schema_id, schema_version),
        ).fetchone()
    if row is None:
        raise ValueError("Requested schema version not found")
    checksum, relative = row
    path = project / relative
    if (
        not path.is_file()
        or path.is_symlink()
        or path.resolve().parent != (project / "registry" / "schemas").resolve()
    ):
        raise ValueError("Registry schema path invalid")
    payload = path.read_bytes()
    schema = json.loads(payload)
    if digest(schema) != checksum or canonical_bytes(schema) != payload:
        raise ValueError("Registry schema is not the immutable registered revision")
    return schema, checksum
