"""Project-pinned generic DAG to immutable RUN/2."""

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from jsonschema import Draft202012Validator

from fairmorph_engine.core.lineage import lineage_frame, trace_entities, trace_pipeline
from fairmorph_engine.core.pipeline import execute_pipeline
from fairmorph_engine.core.project import digest
from fairmorph_engine.core.registry import canonical_bytes
from fairmorph_engine.core.run_executor import _validate_contract, _write_json


def pipeline_path(project, sha):
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Invalid pipeline SHA-256")
    return project / "configurations" / "pipelines" / f"{sha}.json"


def validate_pipeline(config):
    if not isinstance(config, dict) or set(config) not in (
        {"schema_version", "steps", "resources", "outputs"},
        {"schema_version", "steps", "resources", "outputs", "entities"},
    ):
        raise ValueError("Pipeline requires schema_version, steps, resources and outputs")
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "contracts" / "pipeline.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(
        {"schema_version": config["schema_version"], "steps": config["steps"]}
    )
    resources = config["resources"]
    if "entities" in config:
        from fairmorph_engine.core.entity_projection import validate_entities

        validate_entities(config)
    if not isinstance(resources, dict) or not resources:
        raise ValueError("Pipeline requires explicit resource bindings")
    for name, binding in resources.items():
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name)
            or not isinstance(binding, dict)
            or set(binding) != {"resource_id", "format"}
        ):
            raise ValueError("Invalid resource binding")
        if (
            not isinstance(binding["resource_id"], str)
            or not binding["resource_id"]
            or binding["format"] not in ("csv", "parquet")
        ):
            raise ValueError("Unsupported source binding")
    outputs = config["outputs"]
    if (
        not isinstance(outputs, list)
        or not outputs
        or any(not isinstance(n, str) for n in outputs)
        or len(outputs) != len(set(outputs))
    ):
        raise ValueError("Invalid published outputs")
    if not set(outputs).issubset({s["output"] for s in config["steps"]}):
        raise ValueError("Published outputs must be produced by DAG steps")
    if "entities" in config and set(outputs) & {kind.lower() for kind in config["entities"]}:
        raise ValueError("Entity output names are reserved for approved projections")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", n) for n in outputs):
        raise ValueError("Invalid output filename")


def register_pipeline(project, config):
    if not (project / "project.json").is_file() or (project / "project.json").is_symlink():
        raise ValueError("Initialize project before registering a pipeline")
    validate_pipeline(config)
    sha = hashlib.sha256(canonical_bytes(config)).hexdigest()
    path = pipeline_path(project, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Configuration symlink forbidden")
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != config:
            raise ValueError("Configuration collision")
    else:
        _write_json(path, config)
    return {"pipeline_sha256": sha}


def load_pipeline(project, sha):
    path = pipeline_path(project, sha)
    if not path.is_file() or path.is_symlink():
        raise ValueError("Pinned pipeline missing")
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_pipeline(config)
    if hashlib.sha256(canonical_bytes(config)).hexdigest() != sha:
        raise ValueError("Pipeline configuration checksum mismatch")
    return config


def resolve_resources(project, config):
    frames, pins = {}, []
    catalog = project / "catalog" / "catalog.sqlite"
    if not catalog.is_file() or catalog.is_symlink():
        raise ValueError("Catalog missing")
    with sqlite3.connect(f"file:{catalog.resolve()}?mode=ro", uri=True) as db:
        for name, binding in sorted(config["resources"].items()):
            row = db.execute(
                "SELECT object_sha256 FROM source_resources WHERE resource_id=?",
                (binding["resource_id"],),
            ).fetchone()
            if row is None:
                raise ValueError("Resource not imported")
            sha = row[0]
            if not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise ValueError("Invalid resource hash")
            relative = f"objects/sha256/{sha[:2]}/{sha}"
            path = project / relative
            if not path.is_file() or path.is_symlink() or digest(path) != sha:
                raise ValueError("Immutable source missing or modified")
            frames[name] = (
                pl.read_csv(path) if binding["format"] == "csv" else pl.read_parquet(path)
            )
            pins.append(
                {
                    "name": name,
                    "resource_id": binding["resource_id"],
                    "sha256": sha,
                    "object_path": relative,
                    "format": binding["format"],
                }
            )
    return frames, pins


def execute_pipeline_run(project, sha, emit=lambda *_a, **_k: None):
    config = load_pipeline(project, sha)
    confirmation = None
    if "entities" in config:
        from fairmorph_engine.core.entity_projection import require_confirmation

        confirmation = require_confirmation(project, sha)
    frames, pins = resolve_resources(project, config)
    tables = execute_pipeline(
        {"schema_version": config["schema_version"], "steps": config["steps"]}, frames
    )
    entity_frames = {}
    if "entities" in config:
        from fairmorph_engine.core.entity_projection import (
            project_entities,
            verify_projection_evidence,
        )

        verify_projection_evidence(project, config, tables, confirmation)
        entity_frames = project_entities(config, tables)
    # Trace original source rows and cells through the same DAG and entity bindings.
    # These are physical source locations, never inferred biological identities.
    traces = trace_pipeline(config, tables, pins)
    traces.update(trace_entities(config, traces))
    published = {name: tables[name] for name in config["outputs"]}
    published.update({kind.lower(): frame for kind, frame in entity_frames.items()})
    lineage = lineage_frame(published, traces)
    started = datetime.now(UTC).isoformat()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    staging = project / "runs" / f".pending-{run_id}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        (staging / "outputs").mkdir()
        (staging / "audit").mkdir()
        (staging / "reports").mkdir()
        lineage.write_parquet(staging / "audit" / "lineage.parquet")
        metrics = []
        for name in config["outputs"]:
            frame = tables[name]
            frame.write_parquet(staging / "outputs" / f"{name}.parquet")
            metrics.append({"name": name, "rows": frame.height, "columns": frame.columns})
        for kind, frame in entity_frames.items():
            frame.write_parquet(staging / "outputs" / f"{kind.lower()}.parquet")
            metrics.append({"name": kind.lower(), "rows": frame.height, "columns": frame.columns})
        snapshot = {
            "schema_version": "fairmorph.pipeline.inputs/1",
            "configuration_sha256": sha,
            "sources": pins,
        }
        if confirmation is not None:
            snapshot["projection_confirmation"] = confirmation
        _write_json(staging / "inputs.snapshot.json", snapshot)
        _write_json(staging / "configuration.snapshot.json", config)
        _write_json(
            staging / "audit" / "pipeline.json",
            {
                "configuration_sha256": sha,
                "steps": config["steps"],
                "source_bindings": pins,
                "outputs": metrics,
            },
        )
        _write_json(staging / "reports" / "quality.json", {"outputs": metrics})
        paths = [
            *(f"outputs/{n}.parquet" for n in config["outputs"]),
            *(f"outputs/{k.lower()}.parquet" for k in entity_frames),
            "audit/pipeline.json",
            "audit/lineage.parquet",
            "reports/quality.json",
            "inputs.snapshot.json",
            "configuration.snapshot.json",
        ]
        artifacts = [
            {"path": p, "bytes": (staging / p).stat().st_size, "sha256": digest(staging / p)}
            for p in paths
        ]
        manifest = {
            "schema_version": "fairmorph.poc.run/2",
            "run_id": run_id,
            "status": "completed",
            "started_at": started,
            "engine_version": "0.1.0",
            "transformation_version": "fairmorph.pipeline/1",
            "configuration_sha256": sha,
            "input_snapshot_sha256": digest(staging / "inputs.snapshot.json"),
            "artifacts": artifacts,
        }
        _validate_contract("run-v2", manifest)
        _write_json(staging / "manifest.json", manifest)
        project_file = project / "project.json"
        original = project_file.read_bytes()
        index = json.loads(original)
        index["run_ids"].append(run_id)
        temp = project_file.with_name(f".project.{uuid.uuid4().hex}.tmp")
        published = False
        indexed = False
        try:
            temp.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
                db.execute(
                    "INSERT INTO runs VALUES (?, ?, ?)",
                    (run_id, f"runs/{run_id}/manifest.json", "completed"),
                )
                os.replace(staging, project / "runs" / run_id)
                published = True
                os.replace(temp, project_file)
                indexed = True
        except Exception:
            if indexed:
                restore = project_file.with_name(f".project.{uuid.uuid4().hex}.restore")
                restore.write_bytes(original)
                os.replace(restore, project_file)
            if published:
                os.replace(project / "runs" / run_id, staging)
            raise
        finally:
            temp.unlink(missing_ok=True)
        emit("result", status="success", data={"run_id": run_id, "outputs": metrics})
        return manifest
    except Exception:
        if staging.is_dir():
            (staging / "FAILED").write_text("Run incomplete\n", encoding="utf-8")
        raise


def verify_pipeline_run(project, run_dir, manifest):
    sha = manifest["configuration_sha256"]
    config = load_pipeline(project, sha)
    saved = json.loads((run_dir / "configuration.snapshot.json").read_text(encoding="utf-8"))
    if saved != config:
        raise ValueError("RUN configuration mismatch")
    _, pins = resolve_resources(project, config)
    confirmation = None
    if "entities" in config:
        from fairmorph_engine.core.entity_projection import require_confirmation

        confirmation = require_confirmation(project, sha)
    snapshot = json.loads((run_dir / "inputs.snapshot.json").read_text(encoding="utf-8"))
    expected_snapshot = {
        "schema_version": "fairmorph.pipeline.inputs/1",
        "configuration_sha256": sha,
        "sources": pins,
    }
    if confirmation is not None:
        expected_snapshot["projection_confirmation"] = confirmation
    if snapshot != expected_snapshot:
        raise ValueError("RUN source pins mismatch")
    if "audit/lineage.parquet" not in {item["path"] for item in manifest["artifacts"]}:
        raise ValueError("RUN manifest must pin the source-lineage artifact")
    # Reconstruct physical provenance from the pinned source bytes and DAG.
    frames, _ = resolve_resources(project, config)
    tables = execute_pipeline(
        {"schema_version": config["schema_version"], "steps": config["steps"]}, frames
    )
    traces = trace_pipeline(config, tables, pins)
    reconstructed = {name: tables[name] for name in config["outputs"]}
    if "entities" in config:
        from fairmorph_engine.core.entity_projection import (
            project_entities,
            verify_projection_evidence,
        )

        verify_projection_evidence(project, config, tables, confirmation)
        reconstructed.update(
            {kind.lower(): frame for kind, frame in project_entities(config, tables).items()}
        )
        traces.update(trace_entities(config, traces))
    for name, frame in reconstructed.items():
        if not frame.equals(pl.read_parquet(run_dir / "outputs" / f"{name}.parquet")):
            raise ValueError("RUN output differs from pinned DAG input")
    expected_lineage = lineage_frame(reconstructed, traces)
    recorded_lineage = pl.read_parquet(run_dir / "audit" / "lineage.parquet")
    if not expected_lineage.equals(recorded_lineage):
        raise ValueError("RUN source-cell lineage mismatch")
    audit = json.loads((run_dir / "audit" / "pipeline.json").read_text(encoding="utf-8"))
    if (
        audit["configuration_sha256"] != sha
        or audit["steps"] != config["steps"]
        or audit["source_bindings"] != pins
    ):
        raise ValueError("RUN DAG audit mismatch")
    expected_outputs = config["outputs"] + (
        [kind.lower() for kind in config["entities"]] if "entities" in config else []
    )
    if [item["name"] for item in audit["outputs"]] != expected_outputs:
        raise ValueError("RUN output binding mismatch")
    for item in audit["outputs"]:
        frame = pl.read_parquet(run_dir / "outputs" / f"{item['name']}.parquet")
        if frame.height != item["rows"] or frame.columns != item["columns"]:
            raise ValueError("RUN output metrics mismatch")
