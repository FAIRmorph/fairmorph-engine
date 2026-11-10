"""Dataset-independent project, object store, resource import and package catalog."""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def connection(project: Path):
    db = sqlite3.connect(project / "catalog" / "catalog.sqlite")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def update_index(project: Path, object_entry=None, package_id=None) -> None:
    path = project / "project.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if object_entry and object_entry["sha256"] not in {v["sha256"] for v in value["input_objects"]}:
        value["input_objects"].append(object_entry)
    if package_id and package_id not in value["package_ids"]:
        value["package_ids"].append(package_id)
    temp = path.with_name(f".project.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def initialize_project(project: Path, name: str = "FAIRmorph project") -> dict:
    """Create a project without interpreting or importing data."""
    if not name.strip() or project.is_symlink():
        raise ValueError("Invalid project name or symbolic link")
    project.mkdir(parents=True, exist_ok=True)
    for subdir in (
        "objects/sha256",
        "imports",
        "packages",
        "configurations",
        "runs",
        "exports",
        "catalog",
    ):
        (project / subdir).mkdir(parents=True, exist_ok=True)
    with connection(project) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.executescript("""
          CREATE TABLE IF NOT EXISTS project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS source_objects (sha256 TEXT PRIMARY KEY, bytes INTEGER NOT NULL CHECK(bytes >= 0), original_name TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, manifest_path TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status = 'completed'));
          CREATE TABLE IF NOT EXISTS source_resources (
            resource_id TEXT PRIMARY KEY, original_name TEXT NOT NULL,
            object_sha256 TEXT NOT NULL REFERENCES source_objects(sha256),
            import_id TEXT NOT NULL UNIQUE, state TEXT NOT NULL DEFAULT 'imported_unmapped');
          CREATE INDEX IF NOT EXISTS source_resources_hash ON source_resources(object_sha256);
          CREATE TABLE IF NOT EXISTS packages (
            package_id TEXT PRIMARY KEY, descriptor_path TEXT NOT NULL UNIQUE,
            revision_sha256 TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS package_resources (
            package_id TEXT NOT NULL REFERENCES packages(package_id),
            resource_id TEXT NOT NULL REFERENCES source_resources(resource_id),
            role TEXT NOT NULL, PRIMARY KEY (package_id, role));
        """)
        db.execute("INSERT OR IGNORE INTO project_meta VALUES ('schema_version', 'poc/1')")
    target = project / "project.json"
    if not target.exists():
        write_json(
            target,
            {
                "schema_version": "fairmorph.poc.project/1",
                "project_id": str(uuid.uuid4()),
                "name": name,
                "catalog_schema_version": "poc/1",
                "package_ids": [],
                "run_ids": [],
                "input_objects": [],
            },
        )
    return json.loads(target.read_text(encoding="utf-8"))


def import_resource(project: Path, source: Path, role: str) -> dict:
    """Import immutable source bytes without assigning scientific semantics."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", role) or role in (".", ".."):
        raise ValueError("Invalid resource role")
    if not source.is_file() or source.is_symlink():
        raise ValueError("Source must be a regular file")
    if not (project / "project.json").is_file():
        raise ValueError("Initialize project before importing")
    checksum = digest(source)
    relative = f"objects/sha256/{checksum[:2]}/{checksum}"
    target = project / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or digest(target) != checksum:
            raise ValueError("Stored source object corrupted")
    else:
        staging = target.with_name(f".{checksum}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, staging)
            if digest(staging) != checksum:
                raise ValueError("Source changed during import")
            os.replace(staging, target)
        finally:
            staging.unlink(missing_ok=True)
    import_id = f"{role}-{checksum}"
    manifest = {
        "schema_version": "fairmorph.poc.import/1",
        "import_id": import_id,
        "role": role,
        "original_name": source.name,
        "sha256": checksum,
        "object_path": relative,
    }
    path = project / "imports" / import_id / "manifest.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Existing import manifest changed")
    else:
        write_json(path, manifest)
    resource_id = f"resource-{import_id}"
    with connection(project) as db:
        db.execute(
            "INSERT OR IGNORE INTO source_objects VALUES (?, ?, ?)",
            (checksum, target.stat().st_size, source.name),
        )
        db.execute(
            "INSERT OR IGNORE INTO source_resources VALUES (?, ?, ?, ?, ?)",
            (resource_id, source.name, checksum, import_id, "imported_unmapped"),
        )
    update_index(project, object_entry={"sha256": checksum, "object_path": relative})
    return {**manifest, "resource_id": resource_id, "state": "imported_unmapped"}


def register_package(project: Path, package_id: str, resources: dict[str, dict]) -> dict:
    """Register a virtual package without copying original objects."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", package_id) or package_id in (".", ".."):
        raise ValueError("Invalid package ID")
    if not resources:
        raise ValueError("Package must contain resources")
    entries = []
    for role, resource in sorted(resources.items()):
        if role != resource["role"]:
            raise ValueError("Role mismatch")
        entries.append(
            {"name": role, "sha256": resource["sha256"], "object_path": resource["object_path"]}
        )
    descriptor = {
        "schema_version": "fairmorph.poc.virtual-package/1",
        "package_id": package_id,
        "virtual": True,
        "resources": entries,
    }
    path = project / "packages" / package_id / "virtual-descriptor.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != descriptor:
            raise ValueError("Existing package revision differs")
    else:
        write_json(path, descriptor)
    with connection(project) as db:
        db.execute(
            "INSERT OR IGNORE INTO packages VALUES (?, ?, ?)",
            (package_id, f"packages/{package_id}/virtual-descriptor.json", digest(path)),
        )
        for role, resource in sorted(resources.items()):
            db.execute(
                "INSERT OR IGNORE INTO package_resources VALUES (?, ?, ?)",
                (package_id, resource["resource_id"], role),
            )
    update_index(project, package_id=package_id)
    return descriptor



def register_package_from_project_draft(project: Path) -> dict:
    """Register a virtual package from a validated project-local draft.

    The Engine resolves imported resources and immutable original bytes on its
    own; callers cannot supply scientific values or source hashes via CLI.
    """
    from jsonschema import Draft202012Validator, FormatChecker

    project = Path(project)
    draft_path = project / "configurations" / "drafts" / "package-registration.json"
    if (
        not (project / "project.json").is_file()
        or (project / "project.json").is_symlink()
        or not draft_path.is_file()
        or draft_path.is_symlink()
    ):
        raise ValueError("Expected an initialized project and regular package-registration draft")
    spec = json.loads(draft_path.read_text(encoding="utf-8"))
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "package-registration.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(spec)
    roles = [entry["role"] for entry in spec["resources"]]
    resource_ids = [entry["resource_id"] for entry in spec["resources"]]
    if len(roles) != len(set(roles)) or len(resource_ids) != len(set(resource_ids)):
        raise ValueError("Duplicate role or resource_id in package draft")

    manifest_by_role = {}
    catalog = project / "catalog" / "catalog.sqlite"
    if not catalog.is_file() or catalog.is_symlink():
        raise ValueError("Project catalog missing")
    with sqlite3.connect(f"file:{catalog.resolve()}?mode=ro", uri=True) as db:
        for entry in spec["resources"]:
            role, resource_id = entry["role"], entry["resource_id"]
            record = db.execute(
                "SELECT import_id, original_name, object_sha256 FROM source_resources "
                "WHERE resource_id=?", (resource_id,),
            ).fetchone()
            if record is None:
                raise ValueError(f"Unregistered source resource: {resource_id}")
            import_id, original_name, object_sha = record
            import_path = project / "imports" / import_id / "manifest.json"
            if not import_path.is_file() or import_path.is_symlink():
                raise ValueError("Missing immutable import record")
            manifest = json.loads(import_path.read_text(encoding="utf-8"))
            expected_path = f"objects/sha256/{object_sha[:2]}/{object_sha}"
            if (
                manifest.get("import_id") != import_id
                or manifest.get("original_name") != original_name
                or manifest.get("role") != role
                or manifest.get("sha256") != object_sha
                or manifest.get("object_path") != expected_path
            ):
                raise ValueError("Package resource does not match registered import identity")
            stored = project / expected_path
            if not stored.is_file() or stored.is_symlink() or digest(stored) != object_sha:
                raise ValueError("Immutable source object missing or corrupted")
            manifest_by_role[role] = {**manifest, "resource_id": resource_id}

    return register_package(project, spec["package_id"], manifest_by_role)
