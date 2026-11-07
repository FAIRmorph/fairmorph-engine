"""Materialize an independently versioned PoC data package from an immutable RUN."""

import json
import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fairmorph_engine.core.csphoc import (
    EXPORT_VERSION,
    RUN_VERSION,
    sha256,
    validate_contract,
    write_json,
)

_RUN_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")


def verified_run(project: Path, run_id: str) -> tuple[Path, dict]:
    """Reject incomplete, tampered, or escaped RUNs before exporting."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid RUN identifier")
    run_dir = project / "runs" / run_id
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ValueError("Completed RUN not found")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    validate_contract("run", manifest)
    if manifest["schema_version"] != RUN_VERSION or manifest["run_id"] != run_id:
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
            "name": "cs-phoc-poc",
            "title": "FAIRmorph CS-PHOC PoC",
            "description": "Approved wide-to-long output; not a Darwin Core Archive.",
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


def dwca_profile() -> dict:
    """Report the selected author-defined CS-PHOC publication contract."""
    return {
        "profile_id": "darwin-core-archive-event-occurrence",
        "profile_version": "cs-phoc-published/1",
        "source_doi": "https://doi.org/10.48361/gklk1u",
        "core": "Event",
        "core_rows": 536,
        "extension": "Occurrence",
        "extension_rows": 16940,
        "zero_status": "absent",
        "positive_status": "present",
        "missing_category_cells": "omit",
        "metadata_provenance": "FAIRmorph-derived, not the publisher's original EML",
    }


def export_dwca(project: Path, run_id: str, emit) -> dict:
    """Materialize a new immutable DwC-A export from a verified completed RUN."""
    from fairmorph_engine.core.csphoc import EXPECTED_SOURCE_HASHES, transform_sources
    from fairmorph_engine.core.dwca import published_records, write_archive

    run_dir, _ = verified_run(project, run_id)
    emit("progress", stage="EXPORTING", percentage=10, message="Verifying RUN and pinned inputs")
    snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text(encoding="utf-8"))
    sources = {entry["role"]: entry for entry in snapshot["sources"]}
    if {key: value["sha256"] for key, value in sources.items()} != EXPECTED_SOURCE_HASHES:
        raise ValueError("RUN does not reference the approved CS-PHOC source snapshot")
    # The metadata revision used by this RUN must match the pinned project reference.
    from importlib.resources import files as package_files

    reference_metadata = json.loads(
        (
            package_files("fairmorph_engine") / "fixtures" / "cs_phoc" / "publication-metadata.json"
        ).read_text(encoding="utf-8")
    )
    metadata_relative = "packages/cs-phoc/publication-metadata.json"
    metadata_path = project / metadata_relative
    if (
        not metadata_path.is_file()
        or metadata_path.is_symlink()
        or json.loads(metadata_path.read_text(encoding="utf-8")) != reference_metadata
    ):
        raise ValueError("Pinned CS-PHOC publication metadata is missing or altered")
    if snapshot["metadata_revisions"] != [
        {
            "path": metadata_relative,
            "sha256": sha256(metadata_path),
            "provenance": "pinned_cs_phoc_published_reference",
        }
    ]:
        raise ValueError("RUN publication metadata revision differs from project")

    files = {}
    for role, entry in sources.items():
        relative = Path(entry["object_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("RUN source path escapes project")
        source = project / relative
        if not source.is_file() or source.is_symlink() or sha256(source) != entry["sha256"]:
            raise ValueError(f"Missing or modified RUN source object: {role}")
        files[role] = source

    source_records, findings, _, _, _ = transform_sources(
        files["events"], files["counts"], EXPECTED_SOURCE_HASHES["counts"]
    )
    if findings or len(source_records) != 16940:
        raise ValueError("Source transformation no longer matches approved RUN")
    # Compare persisted Parquet content, not just self-consistent manifest hashes.
    from polars import read_parquet

    observed = read_parquet(run_dir / "outputs" / "observations.parquet")
    stored = {
        (row["source_count_id"], row["source_column"]): (row["record_id"], row["value"])
        for row in observed.to_dicts()
    }
    expected = {
        (row["source_count_id"], row["source_column"]): (row["record_id"], row["value"])
        for row in source_records
    }
    if len(stored) != len(source_records) or stored != expected:
        raise ValueError("RUN output differs from approved source transformation")
    events, occurrences = published_records(files["events"], files["counts"])
    emit(
        "progress", stage="EXPORTING", percentage=55, message="Writing Event and Occurrence tables"
    )

    export_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    staging = project / "exports" / f".pending-{export_id}"
    package = staging / "package"
    package.mkdir(parents=True, exist_ok=False)
    try:
        profile = write_archive(package, export_id, events, occurrences)
        write_json(
            package / "mapping-profile.json",
            {
                **dwca_profile(),
                "publication_reference": "https://github.com/us-amlr/cs-phoc/blob/main/R/data_to_dwca.R",
                "reference_limitations": [
                    "WoRMS identifiers are pinned to the published 2026-11-07 reference snapshot, not refreshed online.",
                    "EML is a provenance-labelled FAIRmorph derivative, not a byte-copy of IPT EML.",
                    "event/occurrence record order and archive byte content are not asserted identical.",
                ],
            },
        )
        artifacts = [
            {"path": f"package/{file.name}", "bytes": file.stat().st_size, "sha256": sha256(file)}
            for file in sorted(package.iterdir())
        ]
        manifest = {
            "schema_version": EXPORT_VERSION,
            "export_id": export_id,
            "source_run_id": run_id,
            "profile_id": "darwin-core-archive-event-occurrence",
            "profile_version": "cs-phoc-published/1",
            "created_at": datetime.now(UTC).isoformat(),
            "source_run_manifest_sha256": sha256(run_dir / "manifest.json"),
            "artifacts": artifacts,
        }
        validate_contract("export", manifest)
        write_json(staging / "export-manifest.json", manifest)
        destination = project / "exports" / export_id
        os.replace(staging, destination)
        result = {
            "export_id": export_id,
            "source_run_id": run_id,
            "export_path": str(destination.resolve()),
            "manifest_path": str((destination / "export-manifest.json").resolve()),
            **profile,
        }
        emit("result", status="success", data=result)
        return result
    except Exception:
        (staging / "FAILED").write_text("Darwin Core Archive export incomplete\n", encoding="utf-8")
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
    from fairmorph_engine.core.csphoc import EXPECTED_SOURCE_HASHES

    expected_imports = {f"{role}-{digest}" for role, digest in EXPECTED_SOURCE_HASHES.items()}
    imports_root = project / "imports"
    imports = set()
    if imports_root.is_dir():
        for entry in imports_root.iterdir():
            record = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
            validate_contract("import", record)
            if (
                record["import_id"] != entry.name
                or record["sha256"] != EXPECTED_SOURCE_HASHES[record["role"]]
            ):
                raise ValueError("Import record does not match approved source")
            object_path = project / record["object_path"]
            if not object_path.is_file() or sha256(object_path) != record["sha256"]:
                raise ValueError("Import record points to missing or corrupt object")
            imports.add(entry.name)
    if imports != expected_imports:
        raise ValueError("Project source imports are incomplete")
    virtual = json.loads(
        (project / "packages" / "cs-phoc" / "virtual-descriptor.json").read_text(encoding="utf-8")
    )
    validate_contract("virtual-package", virtual)
    if {item["name"]: item["sha256"] for item in virtual["resources"]} != EXPECTED_SOURCE_HASHES:
        raise ValueError("Virtual package resources do not match approved sources")
    if objects and set(objects) != set(EXPECTED_SOURCE_HASHES.values()):
        raise ValueError("Project object index is incomplete")
    from importlib.resources import files

    published = json.loads(
        (
            files("fairmorph_engine") / "fixtures" / "cs_phoc" / "publication-metadata.json"
        ).read_text(encoding="utf-8")
    )
    metadata = project / "packages" / "cs-phoc" / "publication-metadata.json"
    if (
        not metadata.is_file()
        or metadata.is_symlink()
        or json.loads(metadata.read_text(encoding="utf-8")) != published
    ):
        raise ValueError("Pinned CS-PHOC publication metadata is missing or altered")
    metadata_hash = sha256(metadata)
    runs = []
    for run_id in manifest["run_ids"]:
        run_dir, _ = verified_run(project, run_id)
        snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text(encoding="utf-8"))
        expected_revision = [
            {
                "path": "packages/cs-phoc/publication-metadata.json",
                "sha256": metadata_hash,
                "provenance": "pinned_cs_phoc_published_reference",
            }
        ]
        if snapshot["metadata_revisions"] != expected_revision:
            raise ValueError("RUN publication metadata revision differs from project")
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
