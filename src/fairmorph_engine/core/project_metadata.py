"""Minimal project-file dataset title: draft -> immutable revision -> explicit approval.

The Workbench edits files, never passes scientific values to the Engine process.
SQLite is the Engine-owned decision register; finished RUN snapshots pin revisions.
"""
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from fairmorph_engine.core.registry import canonical_bytes, digest

CONTRACT = "fairmorph.dataset-metadata/1"
APPROVAL_CONTRACT = "fairmorph.dataset-metadata-approval/1"
DRAFT = Path("configurations/drafts/dataset-metadata.json")
APPROVAL = Path("configurations/drafts/dataset-metadata-approval.json")


def _read_json_file(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing or unsafe project configuration: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _validate(document: dict, contract: str) -> None:
    schema = _read_json_file(
        Path(__file__).resolve().parents[1] / "contracts" / f"{contract}.schema.json"
    )
    Draft202012Validator(schema).validate(document)


def _database(project: Path) -> sqlite3.Connection:
    if project.is_symlink() or not (project / "project.json").is_file():
        raise ValueError("FAIRmorph project missing")
    path = project / "catalog" / "catalog.sqlite"
    if not path.is_file() or path.is_symlink():
        raise ValueError("Project catalog missing")
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS dataset_metadata_revisions (
            revision_sha256 TEXT PRIMARY KEY,
            parent_revision_sha256 TEXT,
            content_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dataset_metadata_approvals (
            revision_sha256 TEXT PRIMARY KEY REFERENCES dataset_metadata_revisions(revision_sha256),
            confirmed_by TEXT NOT NULL,
            confirmed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS current_dataset_metadata (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            revision_sha256 TEXT NOT NULL REFERENCES dataset_metadata_approvals(revision_sha256)
        );
        CREATE TRIGGER IF NOT EXISTS dataset_metadata_revisions_no_update
            BEFORE UPDATE ON dataset_metadata_revisions
            BEGIN SELECT RAISE(ABORT, 'Dataset metadata revisions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS dataset_metadata_revisions_no_delete
            BEFORE DELETE ON dataset_metadata_revisions
            BEGIN SELECT RAISE(ABORT, 'Dataset metadata revisions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS dataset_metadata_approvals_no_update
            BEFORE UPDATE ON dataset_metadata_approvals
            BEGIN SELECT RAISE(ABORT, 'Dataset metadata approvals are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS dataset_metadata_approvals_no_delete
            BEFORE DELETE ON dataset_metadata_approvals
            BEGIN SELECT RAISE(ABORT, 'Dataset metadata approvals are immutable'); END;
        """
    )
    return connection


def _current(db: sqlite3.Connection) -> str | None:
    row = db.execute(
        "SELECT revision_sha256 FROM current_dataset_metadata WHERE singleton=1"
    ).fetchone()
    return row[0] if row else None


def _verified_revision(project: Path, db: sqlite3.Connection, sha: str) -> dict:
    row = db.execute(
        "SELECT content_json, parent_revision_sha256 FROM dataset_metadata_revisions "
        "WHERE revision_sha256=?", (sha,)
    ).fetchone()
    if row is None:
        raise ValueError("Unknown dataset metadata revision")
    document = json.loads(row[0])
    path = project / "configurations" / "dataset-metadata" / f"{sha}.json"
    if (
        digest(document) != sha
        or canonical_bytes(document).decode() != row[0]
        or not path.is_file()
        or path.is_symlink()
        or path.read_bytes() != canonical_bytes(document)
        or document["parent_revision_sha256"] != row[1]
    ):
        raise ValueError("Dataset metadata revision changed or missing")
    _validate(document, "dataset-metadata")
    return document


def show_dataset_metadata(project: Path) -> dict:
    """Read the effective approved revision, never use an unapproved draft."""
    with _database(project) as db:
        sha = _current(db)
        if sha is None:
            return {"status": "unconfigured", "revision_sha256": None, "title": None}
        doc = _verified_revision(project, db, sha)
        approval = db.execute(
            "SELECT confirmed_by, confirmed_at FROM dataset_metadata_approvals "
            "WHERE revision_sha256=?", (sha,)
        ).fetchone()
        if approval is None:
            raise ValueError("Active dataset metadata lacks approval")
        return {
            "status": "approved",
            "revision_sha256": sha,
            "title": doc["title"],
            "confirmed_by": approval[0],
            "confirmed_at": approval[1],
        }


def stage_dataset_metadata(project: Path) -> dict:
    """Register one immutable project-file draft, without approving it."""
    doc = _read_json_file(project / DRAFT)
    _validate(doc, "dataset-metadata")
    sha = digest(doc)
    with _database(project) as db:
        parent = _current(db)
        if doc["parent_revision_sha256"] != parent:
            raise ValueError("Stale dataset metadata draft; refresh the parent revision")
        if sha == parent:
            raise ValueError("Metadata draft has no changes")
        path = project / "configurations" / "dataset-metadata" / f"{sha}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError("Unsafe revision path")
        raw = canonical_bytes(doc)
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("Dataset metadata revision hash collision")
        else:
            temporary = path.with_name(f".{sha}.{uuid.uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        db.execute(
            "INSERT OR IGNORE INTO dataset_metadata_revisions VALUES (?, ?, ?, ?)",
            (sha, parent, raw.decode(), datetime.now(UTC).isoformat()),
        )
        _verified_revision(project, db, sha)
    return {"status": "staged", "revision_sha256": sha, "title": doc["title"]}


def approve_dataset_metadata(project: Path) -> dict:
    """Approve a specific staged hash from a separate explicit project-file decision."""
    decision = _read_json_file(project / APPROVAL)
    _validate(decision, "dataset-metadata-approval")
    sha = decision["revision_sha256"]
    with _database(project) as db:
        db.execute("BEGIN IMMEDIATE")
        doc = _verified_revision(project, db, sha)
        parent = _current(db)
        if doc["parent_revision_sha256"] != parent or sha == parent:
            raise ValueError("Stale or already active dataset metadata approval")
        if db.execute(
            "SELECT 1 FROM dataset_metadata_approvals WHERE revision_sha256=?", (sha,)
        ).fetchone():
            raise ValueError("Revision has already been approved")
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO dataset_metadata_approvals VALUES (?, ?, ?)",
            (sha, decision["confirmed_by"].strip(), now),
        )
        db.execute(
            "INSERT INTO current_dataset_metadata VALUES (1, ?) "
            "ON CONFLICT(singleton) DO UPDATE SET revision_sha256=excluded.revision_sha256",
            (sha,),
        )
    return {
        "status": "approved", "revision_sha256": sha, "title": doc["title"],
        "confirmed_by": decision["confirmed_by"].strip(), "confirmed_at": now,
    }


def dataset_metadata_snapshot(project: Path, revision_sha256: str | None = None) -> dict | None:
    """Verify historical revision independently of current pointer."""
    with _database(project) as db:
        sha = revision_sha256 if revision_sha256 is not None else _current(db)
        if sha is None:
            return None
        doc = _verified_revision(project, db, sha)
        approval = db.execute(
            "SELECT confirmed_by, confirmed_at FROM dataset_metadata_approvals "
            "WHERE revision_sha256=?", (sha,)
        ).fetchone()
        if approval is None:
            raise ValueError("Dataset metadata revision is unapproved")
        return {
            "schema_version": CONTRACT,
            "revision_sha256": sha,
            "parent_revision_sha256": doc["parent_revision_sha256"],
            "title": doc["title"],
            "confirmed_by": approval[0],
            "confirmed_at": approval[1],
        }
