"""Materialize an independently versioned PoC data package from an immutable RUN."""

import json
import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from fairmorph_engine.core.project import digest as sha256
from fairmorph_engine.core.project import write_json

EXPORT_VERSION = "fairmorph.poc.export/1"
RUN_VERSION = "fairmorph.poc.run/1"


def validate_contract(name: str, document: dict) -> None:
    """Validate a versioned generic artifact contract."""
    path = Path(__file__).resolve().parents[1] / "contracts" / f"{name}.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)


_RUN_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")


def verified_run(project: Path, run_id: str) -> tuple[Path, dict]:
    """Reject incomplete, tampered, or escaped RUNs before exporting."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid RUN identifier")
    run_dir = project / "runs" / run_id
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ValueError("Completed RUN not found")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") == "fairmorph.poc.run/2":
        from fairmorph_engine.core.run_executor import _validate_contract

        _validate_contract("run-v2", manifest)
    else:
        validate_contract("run", manifest)
        if manifest["schema_version"] != RUN_VERSION:
            raise ValueError("RUN manifest mismatch")
    if manifest["run_id"] != run_id:
        raise ValueError("RUN manifest mismatch")
    for item in manifest["artifacts"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("RUN artifact path escapes RUN directory")
        path = run_dir / relative
        if not path.resolve().is_relative_to(run_dir.resolve()):
            raise ValueError("RUN artifact path escapes RUN directory")
        if not path.is_file() or path.is_symlink() or path.stat().st_size != item["bytes"]:
            raise ValueError(f"Missing or modified RUN artifact: {relative}")
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Checksum mismatch for RUN artifact: {relative}")
    if sha256(run_dir / "inputs.snapshot.json") != manifest["input_snapshot_sha256"]:
        raise ValueError("RUN input snapshot mismatch")
    if manifest["schema_version"] == "fairmorph.poc.run/2":
        from fairmorph_engine.core.run_executor import verify_mapping_run

        verify_mapping_run(project, run_dir, manifest)
    return run_dir, manifest


def export_data_package(project: Path, run_id: str, emit):
    """Export CSV resources and checksums without modifying the source RUN."""
    run_dir, _ = verified_run(project, run_id)
    emit("progress", stage="EXPORTING", percentage=10, message="Verifying immutable RUN")
    from polars import read_parquet

    export_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    staging = project / "exports" / f".pending-{export_id}"
    package = staging / "package"
    package.mkdir(parents=True, exist_ok=False)
    try:
        for source, name in (
            (run_dir / "outputs" / "observations.parquet", "observations.csv"),
            (run_dir / "audit" / "lineage.parquet", "lineage.csv"),
        ):
            read_parquet(source).write_csv(package / name)
        shutil.copyfile(run_dir / "reports" / "quality.json", package / "quality.json")
        resources = [
            {
                "name": "observations",
                "path": "observations.csv",
                "format": "csv",
                "mediatype": "text/csv",
            },
            {"name": "lineage", "path": "lineage.csv", "format": "csv", "mediatype": "text/csv"},
            {
                "name": "quality",
                "path": "quality.json",
                "format": "json",
                "mediatype": "application/json",
            },
        ]
        descriptor = {
            "profile": "data-package",
            "name": "fairmorph-run",
            "title": "FAIRmorph verified RUN",
            "description": "Verified immutable RUN observations and lineage; not a Darwin Core Archive.",
            "resources": resources,
        }
        write_json(package / "datapackage.json", descriptor)
        emit("progress", stage="EXPORTING", percentage=75, message="Hashing data package")
        files = sorted(package.iterdir())
        artifacts = [
            {"path": f"package/{file.name}", "bytes": file.stat().st_size, "sha256": sha256(file)}
            for file in files
        ]
        manifest = {
            "schema_version": EXPORT_VERSION,
            "export_id": export_id,
            "source_run_id": run_id,
            "profile_id": "frictionless-data-package",
            "profile_version": "poc/1",
            "created_at": datetime.now(UTC).isoformat(),
            "source_run_manifest_sha256": sha256(run_dir / "manifest.json"),
            "artifacts": artifacts,
        }
        validate_contract("export", manifest)
        write_json(staging / "export-manifest.json", manifest)
        final = project / "exports" / export_id
        os.replace(staging, final)
        emit(
            "result",
            status="success",
            data={
                "export_id": export_id,
                "source_run_id": run_id,
                "export_path": str(final.resolve()),
                "manifest_path": str((final / "export-manifest.json").resolve()),
                "artifacts": artifacts,
            },
        )
        return manifest
    except Exception:
        (staging / "FAILED").write_text("Export incomplete\n", encoding="utf-8")
        raise


def verify_project(project: Path) -> dict:
    """Audit project references and completed RUN/export files without changing anything."""
    import sqlite3

    project_file = project / "project.json"
    manifest = json.loads(project_file.read_text(encoding="utf-8"))
    validate_contract("project", manifest)
    objects = []
    for item in manifest["input_objects"]:
        path = project / item["object_path"]
        if not path.resolve().is_relative_to(project.resolve()):
            raise ValueError("Object path escapes project")
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError(f"Missing or corrupt source object: {item['object_path']}")
        objects.append(item["sha256"])
    import_entries = {}
    imports_root = project / "imports"
    if imports_root.is_dir():
        for entry in imports_root.iterdir():
            if not entry.is_dir() or entry.is_symlink():
                raise ValueError("Unexpected import directory entry")
            record = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
            validate_contract("import", record)
            if record["import_id"] != entry.name:
                raise ValueError("Import record identifier differs from directory")
            relative = Path(record["object_path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Import object path escapes project")
            target = project / relative
            if not target.is_file() or target.is_symlink() or sha256(target) != record["sha256"]:
                raise ValueError("Import record points to missing or corrupt object")
            import_entries[entry.name] = record
    for package_id in manifest["package_ids"]:
        if not package_id or any(ch in package_id for ch in "/\\"):
            raise ValueError("Invalid package identifier")
        package_file = project / "packages" / package_id / "virtual-descriptor.json"
        descriptor = json.loads(package_file.read_text(encoding="utf-8"))
        validate_contract("virtual-package", descriptor)
        if descriptor["package_id"] != package_id:
            raise ValueError("Package identifier differs from manifest")
        for resource in descriptor["resources"]:
            if not any(
                entry["role"] == resource["name"]
                and entry["sha256"] == resource["sha256"]
                and entry["object_path"] == resource["object_path"]
                for entry in import_entries.values()
            ):
                raise ValueError("Package resource is not imported")
    runs = []
    for run_id in manifest["run_ids"]:
        run_dir, _ = verified_run(project, run_id)
        snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text(encoding="utf-8"))
        for revision in snapshot.get("metadata_revisions", []):
            relative = Path(revision["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Metadata revision path escapes project")
            target = project / relative
            if not target.is_file() or target.is_symlink() or sha256(target) != revision["sha256"]:
                raise ValueError("RUN metadata revision differs from project")
        runs.append(run_id)
    catalog = project / "catalog" / "catalog.sqlite"
    if not catalog.is_file():
        raise ValueError("Project catalog is missing")
    with sqlite3.connect(f"file:{catalog.resolve()}?mode=ro", uri=True) as connection:
        catalog_runs = {row[0] for row in connection.execute("SELECT run_id FROM runs")}
    if catalog_runs != set(runs):
        raise ValueError("Project RUN index differs from SQLite catalog")

    exports = []
    export_root = project / "exports"
    if export_root.is_dir():
        for export in export_root.iterdir():
            if export.name.startswith(".pending-"):
                continue
            if not export.is_dir() or export.is_symlink():
                raise ValueError("Unexpected export directory entry")
            doc = json.loads((export / "export-manifest.json").read_text(encoding="utf-8"))
            validate_contract("export", doc)
            if doc["export_id"] != export.name or doc["source_run_id"] not in runs:
                raise ValueError("Export manifest references unknown RUN")
            source_run = project / "runs" / doc["source_run_id"] / "manifest.json"
            if doc["source_run_manifest_sha256"] != sha256(source_run):
                raise ValueError("Export source RUN manifest changed")
            for item in doc["artifacts"]:
                relative = Path(item["path"])
                path = export / relative
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not path.resolve().is_relative_to(export.resolve())
                ):
                    raise ValueError("Export path escapes export directory")
                if (
                    not path.is_file()
                    or path.stat().st_size != item["bytes"]
                    or sha256(path) != item["sha256"]
                ):
                    raise ValueError(f"Missing or modified export artifact: {relative}")
            exports.append(export.name)
    return {
        "project_path": str(project.resolve()),
        "source_objects": len(objects),
        "completed_runs": len(runs),
        "exports": len(exports),
        "status": "verified",
    }
