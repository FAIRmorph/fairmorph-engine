"""Explicit reconciliation of interrupted RUN publication.

The RUN directory and its checksummed manifest are the durable publication
authority. Recovery never promotes pending staging or alters RUN contents.
Call only while no writer is active; this PoC has no cross-process lock.
"""

import json
import os
import re
import sqlite3
import uuid
from pathlib import Path

_RUN_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")


def reconcile_runs(project: Path) -> dict:
    """Restore SQLite and project.json indexes from verified completed RUNs.

    Fail closed if a published RUN is invalid. An unindexed, valid completed
    directory is a committed publication interrupted before index commit.
    Pending staging directories remain untouched for forensic inspection.
    """
    from fairmorph_engine.core.export import verified_run

    project_file = project / "project.json"
    catalog = project / "catalog" / "catalog.sqlite"
    runs_root = project / "runs"
    if (
        not project_file.is_file()
        or project_file.is_symlink()
        or not catalog.is_file()
        or catalog.is_symlink()
        or not runs_root.is_dir()
        or runs_root.is_symlink()
    ):
        raise ValueError("Project RUN recovery requires an initialized, safe project")
    index = json.loads(project_file.read_text(encoding="utf-8"))
    existing = index["run_ids"]
    if len(existing) != len(set(existing)) or any(not _RUN_ID.fullmatch(x) for x in existing):
        raise ValueError("Invalid or duplicate RUN index entries")
    completed = set()
    pending = []
    for entry in runs_root.iterdir():
        if entry.name.startswith(".pending-"):
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError("Unsafe pending RUN entry")
            pending.append(entry.name)
            continue
        if not _RUN_ID.fullmatch(entry.name) or entry.is_symlink() or not entry.is_dir():
            raise ValueError("Unexpected RUN directory entry")
        verified_run(project, entry.name)
        completed.add(entry.name)
    # Never silently discard an indexed RUN that has disappeared or become corrupt.
    if set(existing) - completed:
        raise ValueError("Indexed RUN missing from completed RUN directories")
    with sqlite3.connect(catalog) as db:
        db.execute("PRAGMA foreign_keys=ON")
        catalog_ids = {row[0] for row in db.execute("SELECT run_id FROM runs")}
        if catalog_ids - completed:
            raise ValueError("Catalog RUN missing from completed RUN directories")
        missing_catalog = sorted(completed - catalog_ids)
        missing_index = sorted(completed - set(existing))
        if not missing_catalog and not missing_index:
            return {"recovered": [], "pending": sorted(pending), "status": "consistent"}
        # Prepare the atomic file replacement before committing SQLite changes.
        updated = {**index, "run_ids": sorted(completed)}
        temporary = project_file.with_name(f".project.{uuid.uuid4().hex}.recovery")
        before = project_file.read_bytes()
        try:
            temporary.write_text(
                json.dumps(updated, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            db.execute("BEGIN IMMEDIATE")
            for run_id in missing_catalog:
                db.execute(
                    "INSERT INTO runs VALUES (?, ?, ?)",
                    (run_id, f"runs/{run_id}/manifest.json", "completed"),
                )
            os.replace(temporary, project_file)
            try:
                db.commit()
            except Exception:
                restore = project_file.with_name(f".project.{uuid.uuid4().hex}.restore")
                restore.write_bytes(before)
                os.replace(restore, project_file)
                raise
        finally:
            temporary.unlink(missing_ok=True)
    return {
        "recovered": sorted(set(missing_catalog) | set(missing_index)),
        "pending": sorted(pending),
        "status": "consistent",
    }
