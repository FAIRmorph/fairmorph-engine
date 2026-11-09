"""Dataset-independent execution of reviewed, immutable tabular mappings.

This executor is deliberately limited to the approved wide-to-long count
operation. It does not infer scientific semantics or load example datasets.
"""

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from fairmorph_engine.core.registry import _catalog, canonical_bytes, mapping_snapshot
from fairmorph_engine.processing.tabular import unpivot_csv

RUN_SCHEMA_VERSION = "fairmorph.poc.run/2"
INPUT_SCHEMA_VERSION = "fairmorph.poc.inputs/2"
TRANSFORM_VERSION = "wide-to-long-counts/1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for part in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as target:
        json.dump(value, target, sort_keys=True, indent=2, ensure_ascii=False)
        target.write("\n")


def _validate_contract(name: str, document: dict) -> None:
    target = Path(__file__).resolve().parents[1] / "contracts" / f"{name}.schema.json"
    schema = json.loads(target.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)


def _approved_mapping(project: Path, mapping_sha256: str, snapshot: dict) -> tuple[dict, Path, str]:
    """Resolve one approved input object, not an arbitrary caller-supplied CSV."""
    with _catalog(project) as db:
        row = db.execute(
            "SELECT content_json FROM mapping_versions WHERE mapping_sha256=?",
            (mapping_sha256,),
        ).fetchone()
        if row is None:
            raise ValueError("Unknown mapping revision")
        mapping = json.loads(row[0])
        if hashlib.sha256(canonical_bytes(mapping)).hexdigest() != mapping_sha256:
            raise ValueError("Mapping content differs from approved revision")
        if mapping.get("operation") != TRANSFORM_VERSION:
            raise ValueError("Mapping must explicitly select supported transformation")
        identifier = mapping.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Mapping requires an explicit identifier column")
        if (
            mapping.get("empty_cell_policy") != "omit"
            or mapping.get("zero_cell_policy") != "preserve"
        ):
            raise ValueError("Unsupported or unapproved cell semantics")
        bindings = mapping.get("bindings")
        if not isinstance(bindings, list) or not bindings:
            raise ValueError("Mapping contains no field bindings")
        if (
            not isinstance(mapping.get("source_resource_id"), str)
            or not mapping["source_resource_id"]
        ):
            raise ValueError("Mapping requires one explicit source resource")
        resource_id = mapping["source_resource_id"]
        resource_pins = {
            item["resource_id"]: item["object_sha256"] for item in snapshot["source_resources"]
        }
        expected_resources = {resource_id, *mapping.get("auxiliary_resource_ids", [])}
        if set(resource_pins) != expected_resources:
            raise ValueError("Mapping source resources differ from approved snapshot")
        for auxiliary_id in expected_resources - {resource_id}:
            auxiliary_sha = resource_pins[auxiliary_id]
            auxiliary = project / "objects" / "sha256" / auxiliary_sha[:2] / auxiliary_sha
            if not auxiliary.is_file() or auxiliary.is_symlink() or _sha256(auxiliary) != auxiliary_sha:
                raise ValueError("Missing or modified auxiliary source object")
        source_columns = []
        for binding in bindings:
            column = binding.get("source_column")
            if not isinstance(column, str) or not column or column == identifier:
                raise ValueError("Mapping binding lacks a valid source column")
            if column in source_columns:
                raise ValueError("Duplicate source column in mapping")
            source_columns.append(column)
            field = db.execute(
                "SELECT fd.content_json, sf.field_locator, sf.resource_id, sf.source_field_id "
                "FROM field_definition_revisions fd "
                "JOIN source_fields sf ON fd.source_field_id=sf.source_field_id "
                "WHERE fd.revision_id=?",
                (binding["definition_revision_id"],),
            ).fetchone()
            if (
                field is None
                or field[2] != resource_id
                or field[1] != f"csv:{column}"
                or field[3] != binding.get("source_field_id")
            ):
                raise ValueError("Mapping column has no corresponding approved field revision")
            definition = json.loads(field[0])
            if definition.get("semantic_status") != "defined":
                raise ValueError("Mapping references undefined field semantics")
            if definition.get("counting_unit") != "individual":
                raise ValueError("Approved count mapping requires counting_unit=individual")
            if definition.get("value_semantics", {}).get("zero_meaning") not in (
                "true_zero",
                "absence",
            ):
                raise ValueError("Count mapping requires explicit zero semantics")
        object_sha = resource_pins[resource_id]
        source = project / "objects" / "sha256" / object_sha[:2] / object_sha
        if not source.is_file() or source.is_symlink() or _sha256(source) != object_sha:
            raise ValueError("Missing or modified immutable source object")
    return mapping, source, object_sha


def execute_mapping_run(project: Path, mapping_sha256: str, emit=lambda *_a, **_k: None) -> dict:
    """Execute one reviewed mapping; publish a completed RUN only on success.

    Registry snapshots, source bytes, mapping content and all output artifacts
    are SHA-256-pinned. Failed staging directories are retained for diagnosis.
    """
    # All approval and immutable source checks precede creation of RUN state.
    snapshot = mapping_snapshot(project, mapping_sha256)
    mapping, source, source_hash = _approved_mapping(project, mapping_sha256, snapshot)
    project_file = project / "project.json"
    if not project_file.is_file() or project_file.is_symlink():
        raise ValueError("Project must exist and not be a symbolic link")
    try:
        import polars as pl
    except ImportError as error:
        raise RuntimeError("Polars is required to materialize RUN Parquet artifacts") from error

    started = datetime.now(UTC).isoformat()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    staging = project / "runs" / f".pending-{run_id}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        emit("progress", stage="PROCESSING", percentage=25, message="Executing approved mapping")
        columns = [b["source_column"] for b in mapping["bindings"]]
        binding_by_column = {b["source_column"]: b for b in mapping["bindings"]}
        rows = []
        for item in unpivot_csv(
            source,
            identifier=mapping["identifier"],
            columns=columns,
            empty_cell_policy=mapping["empty_cell_policy"],
            zero_cell_policy=mapping["zero_cell_policy"],
        ):
            record_key = {
                "source_sha256": source_hash,
                "line": item["source_line"],
                "column": item["source_column"],
                "transformation_version": TRANSFORM_VERSION,
                "mapping_sha256": mapping_sha256,
            }
            rows.append(
                {
                    "record_id": hashlib.sha256(canonical_bytes(record_key)).hexdigest(),
                    "source_identifier": item["source_identifier"],
                    "source_line": item["source_line"],
                    "source_column": item["source_column"],
                    "target_field": binding_by_column[item["source_column"]]["target_field"],
                    "value": item["value"],
                }
            )
        if not rows:
            raise ValueError("Approved mapping produced no observation rows")
        # Acceptance criteria belong to the explicitly approved project mapping.
        # Never embed dataset-specific reference values in the Engine.
        observed_metrics = {
            "output_rows": len(rows),
            "explicit_zeros": sum(row["value"] == 0 for row in rows),
            "value_sum": sum(row["value"] for row in rows),
        }
        for metric, expected in mapping.get("acceptance", {}).items():
            if metric not in observed_metrics:
                raise ValueError(f"Unsupported mapping acceptance metric: {metric}")
            if observed_metrics[metric] != expected:
                raise ValueError(
                    f"Mapping acceptance failed for {metric}: "
                    f"expected {expected}, observed {observed_metrics[metric]}"
                )
        output = staging / "outputs" / "observations.parquet"
        lineage = staging / "audit" / "lineage.parquet"
        output.parent.mkdir()
        lineage.parent.mkdir()
        frame = pl.DataFrame(rows)
        frame.write_parquet(output)
        frame.select(
            "record_id", "source_identifier", "source_line", "source_column"
        ).write_parquet(lineage)
        input_snapshot = {
            "schema_version": INPUT_SCHEMA_VERSION,
            "sources": [
                {
                    "resource_id": mapping["source_resource_id"],
                    "sha256": source_hash,
                    "object_path": f"objects/sha256/{source_hash[:2]}/{source_hash}",
                }
            ],
            "mapping_snapshot": snapshot,
            "configuration_sha256": mapping_sha256,
        }
        _validate_contract("inputs.snapshot-v2", input_snapshot)
        _write_json(staging / "inputs.snapshot.json", input_snapshot)
        _write_json(staging / "configuration.snapshot.json", mapping)
        quality = {
            "output_rows": len(rows),
            "explicit_zeros": sum(row["value"] == 0 for row in rows),
            "value_sum": sum(row["value"] for row in rows),
            "transformation": TRANSFORM_VERSION,
        }
        _write_json(staging / "reports" / "quality.json", quality)
        artifacts = []
        for relative in (
            "outputs/observations.parquet",
            "audit/lineage.parquet",
            "reports/quality.json",
            "inputs.snapshot.json",
            "configuration.snapshot.json",
        ):
            target = staging / relative
            artifacts.append(
                {"path": relative, "bytes": target.stat().st_size, "sha256": _sha256(target)}
            )
        manifest = {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "completed",
            "started_at": started,
            "engine_version": "0.1.0",
            "transformation_version": TRANSFORM_VERSION,
            "configuration_sha256": mapping_sha256,
            "input_snapshot_sha256": _sha256(staging / "inputs.snapshot.json"),
            "artifacts": artifacts,
        }
        _validate_contract("run-v2", manifest)
        _write_json(staging / "manifest.json", manifest)
        final = project / "runs" / run_id
        index_before = project_file.read_bytes()
        index = json.loads(index_before)
        if run_id not in index["run_ids"]:
            index["run_ids"].append(run_id)
        interim = project_file.with_name(f".project.{uuid.uuid4().hex}.tmp")
        published = False
        updated_index = False
        try:
            interim.write_text(json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
                db.execute(
                    "INSERT INTO runs VALUES (?, ?, ?)",
                    (run_id, f"runs/{run_id}/manifest.json", "completed"),
                )
                os.replace(staging, final)
                published = True
                os.replace(interim, project_file)
                updated_index = True
            # The SQLite commit succeeds before the completed RUN is reported.
        except Exception:
            # Undo ordinary I/O failures. A system crash between commits still
            # requires catalog/project reconciliation before a production release.
            if updated_index:
                restore = project_file.with_name(f".project.{uuid.uuid4().hex}.restore")
                restore.write_bytes(index_before)
                os.replace(restore, project_file)
            if published and final.is_dir():
                os.replace(final, staging)
            raise
        finally:
            interim.unlink(missing_ok=True)
        emit("result", status="success", data={"run_id": run_id, **quality})
        return manifest
    except Exception:
        if staging.is_dir():
            (staging / "FAILED").write_text("Run incomplete\n", encoding="utf-8")
        raise


def verify_mapping_run(project: Path, run_dir: Path, manifest: dict) -> None:
    """Verify pinned mapping/field revisions and immutable source object bytes."""
    snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text(encoding="utf-8"))
    _validate_contract("inputs.snapshot-v2", snapshot)
    if snapshot["configuration_sha256"] != manifest["configuration_sha256"]:
        raise ValueError("RUN mapping configuration mismatch")
    original = mapping_snapshot(project, snapshot["configuration_sha256"])
    if original != snapshot["mapping_snapshot"]:
        raise ValueError("RUN mapping snapshot differs from approved revisions")
    mapping, source, source_sha = _approved_mapping(
        project, snapshot["configuration_sha256"], original
    )
    sources = snapshot["sources"]
    if len(sources) != 1 or sources[0]["sha256"] != source_sha:
        raise ValueError("RUN source snapshot mismatch")
    if sources[0]["resource_id"] != mapping["source_resource_id"]:
        raise ValueError("RUN source identity mismatch")
    if sources[0]["object_path"] != source.relative_to(project).as_posix():
        raise ValueError("RUN source object path mismatch")
    saved = json.loads((run_dir / "configuration.snapshot.json").read_text(encoding="utf-8"))
    if saved != mapping:
        raise ValueError("RUN mapping configuration was modified")
