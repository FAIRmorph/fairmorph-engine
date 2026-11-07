"""Approved CS-PHOC PoC vertical slice. Engine owns all project writes."""

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

COUNT_FIELDS = {
    "ad_female_count": ("adult", "female"),
    "ad_male_count": ("adult", "male"),
    "ad_unk_count": ("adult", "unknown"),
    "juv_female_count": ("juvenile", "female"),
    "juv_male_count": ("juvenile", "male"),
    "juv_unk_count": ("juvenile", "unknown"),
    "pup_count": ("pup", "unspecified"),
    "unk_female_count": ("unknown", "female"),
    "unk_male_count": ("unknown", "male"),
    "unk_unk_count": ("unknown", "unknown"),
}
PROJECT_VERSION = "fairmorph.poc.project/1"
RUN_VERSION = "fairmorph.poc.run/1"
EXPORT_VERSION = "fairmorph.poc.export/1"
TRANSFORM_VERSION = "cs-phoc-unpivot/1"
EXPECTED_SOURCE_HASHES = {
    "events": "4362ae650cb72cc74901f7719920db5c8bbcfdc2ee09842595d04bf5e587bddc",
    "counts": "be4a28aa5036dea103e9e6bbc6af5fef13d80354ef2750e0960bf78e320c3545",
}
EXPECTED_EVENTS = {
    "event_id",
    "season_name",
    "census_date_start",
    "census_date_end",
    "census_days",
    "surveyed_pst",
    "research_program",
}
EXPECTED_COUNTS = {
    "count_id",
    "event_id",
    "location",
    "species",
    "species_common",
    "total_count",
    *COUNT_FIELDS,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def validate_contract(name: str, data: dict) -> None:
    """Validate the persisted PoC contract before publishing it."""
    schema_path = Path(__file__).resolve().parents[3] / "contracts" / f"{name}.schema.json"
    # Wheels and frozen executables carry their schemas as package resources.
    if not schema_path.is_file():
        schema_path = Path(__file__).resolve().parents[1] / "contracts" / f"{name}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def validate_decision(decision: dict) -> None:
    expected = {
        "status": "user-approved",
        "operation": "wide_to_long",
        "source_resource": "counts",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "invalid_nonempty_policy": "preserve_source_and_report",
    }
    if any(decision.get(key) != value for key, value in expected.items()):
        raise ValueError("The static CS-PHOC mapping must be explicitly user-approved")
    if decision.get("source_columns") != list(COUNT_FIELDS):
        raise ValueError("Exactly the ten approved count categories are required")
    if (
        decision.get("target_fields") != {"category": "source_column", "value": "individual_count"}
        or decision.get("approved_expected_rows") != 16940
    ):
        raise ValueError("Approved CS-PHOC semantics or expected row count changed")


def read_rows(path: Path, expected: set[str]):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, restkey="__extra_fields__", strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or set(headers) != expected:
            raise ValueError(f"Unexpected or duplicate CSV headers in {path.name}")
        for line, record in enumerate(reader, 2):
            if None in record or "__extra_fields__" in record:
                raise ValueError(f"Invalid CSV field count at {path.name}:{line}")
            yield line, record


def transform_sources(events: Path, counts: Path, counts_hash: str):
    """Create stable lineage; never coerce empty cells to numeric zero."""
    event_ids = set()
    duplicate_ids = set()
    events_total = 0
    for _line, row in read_rows(events, EXPECTED_EVENTS):
        events_total += 1
        key = row["event_id"]
        if not key:
            raise ValueError("Empty source event_id")
        if key in event_ids:
            duplicate_ids.add(key)
        event_ids.add(key)

    output = []
    findings = []
    lineage = []
    stats = Counter()
    for line, row in read_rows(counts, EXPECTED_COUNTS):
        stats["count_rows"] += 1
        event_id = row["event_id"]
        if not row["count_id"].strip():
            findings.append(
                {
                    "source_line": line,
                    "source_column": "count_id",
                    "source_count_id": row["count_id"],
                    "raw_value": "",
                    "issue": "missing_count_id",
                    "action": "excluded",
                }
            )
            stats["invalid_events"] += 1
            continue
        if event_id not in event_ids or event_id in duplicate_ids:
            findings.append(
                {
                    "source_line": line,
                    "source_column": "event_id",
                    "source_count_id": row["count_id"],
                    "raw_value": event_id,
                    "issue": "missing_or_ambiguous_event",
                    "action": "excluded",
                }
            )
            stats["invalid_events"] += 1
            continue
        for field, (life_stage, sex) in COUNT_FIELDS.items():
            raw = row[field]
            if raw == "":
                stats["empty_cells"] += 1
                continue
            if not raw.isascii() or not raw.isdecimal() or (len(raw) > 1 and raw[0] == "0"):
                findings.append(
                    {
                        "source_line": line,
                        "source_column": field,
                        "source_count_id": row["count_id"],
                        "raw_value": raw,
                        "issue": "invalid_nonnegative_integer",
                        "action": "excluded",
                    }
                )
                stats["invalid_cells"] += 1
                continue
            value = int(raw)
            identity = hashlib.sha256(
                canonical_bytes(
                    {
                        "source_sha256": counts_hash,
                        "row": line,
                        "field": field,
                        "transform": TRANSFORM_VERSION,
                    }
                )
            ).hexdigest()
            output.append(
                {
                    "record_id": identity,
                    "source_count_id": row["count_id"],
                    "event_id": event_id,
                    "species": row["species"],
                    "location": row["location"],
                    "source_line": line,
                    "source_column": field,
                    "source_value": raw,
                    "value": value,
                    "life_stage": life_stage,
                    "sex": sex,
                }
            )
            lineage.append(
                {
                    "record_id": identity,
                    "source_line": line,
                    "source_column": field,
                    "source_count_id": row["count_id"],
                    "event_type": "wide_to_long",
                    "rule_id": TRANSFORM_VERSION,
                    "source_value": raw,
                    "result_value": str(value),
                }
            )
            stats["zero_cells" if value == 0 else "positive_cells"] += 1
    return output, findings, lineage, stats, events_total


def _init_catalog(project: Path) -> None:
    catalog = project / "catalog" / "catalog.sqlite"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(catalog) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS source_objects (
              sha256 TEXT PRIMARY KEY, bytes INTEGER NOT NULL CHECK(bytes >= 0),
              original_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY, manifest_path TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL CHECK(status = 'completed')
            );
        """)
        conn.execute("INSERT OR IGNORE INTO project_meta VALUES ('schema_version', 'poc/1')")
        conn.commit()


def _import_source(project: Path, source: Path) -> tuple[str, str]:
    digest = sha256(source)
    relative = f"objects/sha256/{digest[:2]}/{digest}"
    target = project / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != digest:
            raise RuntimeError(f"Stored source object corrupted: {relative}")
    else:
        staging = target.with_name(f".{digest}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, staging)
            if sha256(staging) != digest:
                raise RuntimeError("Source changed during import")
            os.replace(staging, target)
        finally:
            staging.unlink(missing_ok=True)
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as conn:
        conn.execute(
            "INSERT OR IGNORE INTO source_objects VALUES (?, ?, ?)",
            (digest, target.stat().st_size, source.name),
        )
    return digest, relative


def _record_import(
    project: Path, role: str, original_name: str, digest: str, object_path: str
) -> None:
    """Persist a source-object import record once per role and content hash."""
    import_id = f"{role}-{digest}"
    target = project / "imports" / import_id / "manifest.json"
    record = {
        "schema_version": "fairmorph.poc.import/1",
        "import_id": import_id,
        "role": role,
        "original_name": original_name,
        "sha256": digest,
        "object_path": object_path,
    }
    validate_contract("import", record)
    if target.is_file():
        if json.loads(target.read_text(encoding="utf-8")) != record:
            raise ValueError(f"Existing import record changed: {import_id}")
    else:
        write_json(target, record)


def run_slice(project: Path, events: Path, counts: Path, decision_file: Path, emit):
    """Run a predefined approved transformation, immutable inputs and results."""
    # Read and validate approval before touching the project directory.
    decision = json.loads(decision_file.read_text(encoding="utf-8"))
    validate_decision(decision)
    for role, source in (("events", events), ("counts", counts)):
        if not source.is_file():
            raise ValueError(f"Missing bundled source: {source}")
        if sha256(source) != EXPECTED_SOURCE_HASHES[role]:
            raise ValueError(f"CS-PHOC {role} source differs from approved reference")

    emit("progress", stage="INITIALIZING", percentage=5, message="Verifying CS-PHOC sources")
    if project.exists() and project.is_symlink():
        raise ValueError("Project directory must not be a symbolic link")
    project.mkdir(parents=True, exist_ok=True)
    _init_catalog(project)
    project_file = project / "project.json"
    if not project_file.exists():
        document = {
            "schema_version": PROJECT_VERSION,
            "project_id": str(uuid.uuid4()),
            "name": "CS-PHOC PoC",
            "catalog_schema_version": "poc/1",
            "package_ids": ["cs-phoc"],
            "run_ids": [],
            "input_objects": [],
        }
        validate_contract("project", document)
        write_json(project_file, document)
    else:
        validate_contract("project", json.loads(project_file.read_text(encoding="utf-8")))

    events_hash, events_ref = _import_source(project, events)
    counts_hash, counts_ref = _import_source(project, counts)
    _record_import(project, "events", events.name, events_hash, events_ref)
    _record_import(project, "counts", counts.name, counts_hash, counts_ref)
    package_dir = project / "packages" / "cs-phoc"
    package_dir.mkdir(parents=True, exist_ok=True)
    virtual_descriptor = package_dir / "virtual-descriptor.json"
    if not virtual_descriptor.exists():
        descriptor = {
            "schema_version": "fairmorph.poc.virtual-package/1",
            "package_id": "cs-phoc",
            "virtual": True,
            "resources": [
                {"name": "events", "sha256": events_hash, "object_path": events_ref},
                {"name": "counts", "sha256": counts_hash, "object_path": counts_ref},
            ],
        }
        validate_contract("virtual-package", descriptor)
        write_json(virtual_descriptor, descriptor)
    else:
        prior = json.loads(virtual_descriptor.read_text(encoding="utf-8"))
        validate_contract("virtual-package", prior)
        supplied = {r["name"]: r["sha256"] for r in prior.get("resources", [])}
        if supplied != {"events": events_hash, "counts": counts_hash}:
            raise ValueError("Existing project package sources differ from approved fixture")
    # Store the scholarly publication reference as a pinned project metadata revision.
    from importlib.resources import files

    reference_metadata = json.loads(
        (
            files("fairmorph_engine") / "fixtures" / "cs_phoc" / "publication-metadata.json"
        ).read_text(encoding="utf-8")
    )
    metadata_file = package_dir / "publication-metadata.json"
    if not metadata_file.is_file():
        write_json(metadata_file, reference_metadata)
    elif json.loads(metadata_file.read_text(encoding="utf-8")) != reference_metadata:
        raise ValueError("Stored publication metadata differs from pinned CS-PHOC reference")
    metadata_hash = sha256(metadata_file)
    config_hash = hashlib.sha256(canonical_bytes(decision)).hexdigest()
    config_path = project / "configurations" / config_hash
    config_path.mkdir(parents=True, exist_ok=True)
    approval = {
        "status": "user-approved",
        "config_sha256": config_hash,
        "source": "CS-PHOC TRANSFORMATIONSENTSCHEIDUNG v0.4",
    }
    if not (config_path / "transformation.json").exists():
        write_json(config_path / "transformation.json", decision)
        write_json(config_path / "approval.json", approval)
    else:
        if (
            json.loads((config_path / "transformation.json").read_text(encoding="utf-8"))
            != decision
        ):
            raise ValueError("Stored transformation configuration has changed")
        if json.loads((config_path / "approval.json").read_text(encoding="utf-8")) != approval:
            raise ValueError("Stored transformation approval has changed")
    started_at = datetime.now(UTC).isoformat()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    staging = project / "runs" / f".pending-{run_id}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        emit(
            "progress",
            stage="PROCESSING",
            percentage=30,
            message="Transforming approved count categories",
        )
        records, findings, lineage, stats, event_count = transform_sources(
            project / events_ref, project / counts_ref, counts_hash
        )
        emit(
            "progress", stage="WRITING", percentage=75, message="Writing Parquet and audit outputs"
        )
        import polars as pl

        (staging / "outputs").mkdir()
        (staging / "audit").mkdir()
        (staging / "reports").mkdir()
        if len(records) != decision["approved_expected_rows"] or findings:
            raise ValueError(
                f"CS-PHOC acceptance failed: {len(records)} rows and {len(findings)} findings"
            )
        pl.DataFrame(records).write_parquet(staging / "outputs" / "observations.parquet")
        pl.DataFrame(lineage).write_parquet(staging / "audit" / "lineage.parquet")
        if findings:
            pl.DataFrame(findings).write_parquet(staging / "audit" / "findings.parquet")
        else:
            pl.DataFrame(
                schema={
                    "source_line": pl.Int64,
                    "source_column": pl.String,
                    "source_count_id": pl.String,
                    "raw_value": pl.String,
                    "issue": pl.String,
                    "action": pl.String,
                }
            ).write_parquet(staging / "audit" / "findings.parquet")
        inputs_snapshot = {
            "schema_version": "fairmorph.poc.inputs/1",
            "sources": [
                {"role": "events", "sha256": events_hash, "object_path": events_ref},
                {"role": "counts", "sha256": counts_hash, "object_path": counts_ref},
            ],
            "package_revisions": [],
            "metadata_revisions": [
                {
                    "path": "packages/cs-phoc/publication-metadata.json",
                    "sha256": metadata_hash,
                    "provenance": "pinned_cs_phoc_published_reference",
                }
            ],
            "configuration_sha256": config_hash,
        }
        validate_contract("inputs.snapshot", inputs_snapshot)
        write_json(staging / "inputs.snapshot.json", inputs_snapshot)
        write_json(staging / "configuration.snapshot.json", decision)
        report = {
            "schema_version": "fairmorph.poc.quality/1",
            "events": event_count,
            "count_rows": stats["count_rows"],
            "output_rows": len(records),
            "omitted_empty_cells": stats["empty_cells"],
            "explicit_zeros": stats["zero_cells"],
            "positive_cells": stats["positive_cells"],
            "invalid_nonempty_cells": stats["invalid_cells"],
            "invalid_event_references": stats["invalid_events"],
            "finding_rows": len(findings),
            "audit_scope": "structural_lineage_and_findings",
        }
        validate_contract("quality", report)
        write_json(staging / "reports" / "quality.json", report)
        artifact_paths = [
            "outputs/observations.parquet",
            "audit/lineage.parquet",
            "audit/findings.parquet",
            "reports/quality.json",
            "inputs.snapshot.json",
            "configuration.snapshot.json",
        ]
        artifacts = [
            {
                "path": path,
                "bytes": (staging / path).stat().st_size,
                "sha256": sha256(staging / path),
            }
            for path in artifact_paths
        ]
        manifest = {
            "schema_version": RUN_VERSION,
            "run_id": run_id,
            "status": "completed",
            "started_at": started_at,
            "engine_version": "0.1.0",
            "transformation_version": TRANSFORM_VERSION,
            "configuration_sha256": config_hash,
            "input_snapshot_sha256": sha256(staging / "inputs.snapshot.json"),
            "artifacts": artifacts,
        }
        validate_contract("run", manifest)
        write_json(staging / "manifest.json", manifest)
        final = project / "runs" / run_id
        staging.rename(final)
        with sqlite3.connect(project / "catalog" / "catalog.sqlite") as conn:
            conn.execute(
                "INSERT INTO runs VALUES (?, ?, ?)",
                (run_id, f"runs/{run_id}/manifest.json", "completed"),
            )
        # Update the project index atomically after successful publication.
        # The run manifest itself is immutable and remains the source of truth.
        index = json.loads(project_file.read_text(encoding="utf-8"))
        index.setdefault("run_ids", []).append(run_id)
        known = {item["sha256"] for item in index.setdefault("input_objects", [])}
        for digest, path in ((events_hash, events_ref), (counts_hash, counts_ref)):
            if digest not in known:
                index["input_objects"].append({"sha256": digest, "object_path": path})
        validate_contract("project", index)
        updated = project_file.with_name(f".project.{uuid.uuid4().hex}.tmp")
        updated.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(updated, project_file)
        emit(
            "result",
            status="success",
            data={
                "project_path": str(project.resolve()),
                "run_id": run_id,
                "run_path": str(final.resolve()),
                "manifest_path": str((final / "manifest.json").resolve()),
                "quality_report_path": str((final / "reports" / "quality.json").resolve()),
                **report,
            },
        )
        return report
    except Exception:
        # Failed runs never masquerade as complete; preserve staging for diagnosis.
        (staging / "FAILED").write_text("Run incomplete\n", encoding="utf-8")
        raise
