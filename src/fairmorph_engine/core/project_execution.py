"""Project-selected execution entry point; Data Package descriptors remain data-only.

The project must explicitly pin an approved mapping revision. No mapping is
inferred from catalog ordering, and no caller-supplied runtime config is used.
The generic DAG publisher is a separate, still-open vertical integration task.
"""

import json
import os
import re
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from fairmorph_engine.core.registry import mapping_snapshot
from fairmorph_engine.core.run_executor import execute_mapping_run


def _project_descriptor(project: Path) -> tuple[Path, dict]:
    path = project / "project.json"
    if project.is_symlink() or not path.is_file() or path.is_symlink():
        raise ValueError("Expected a regular FAIRmorph project descriptor")
    value = json.loads(path.read_text(encoding="utf-8"))
    schema_path = Path(__file__).resolve().parents[1] / "contracts" / "project.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    return path, value


def select_project_mapping(project: Path, mapping_sha256: str) -> dict:
    """Bind a reviewed mapping revision to the project; do not create a RUN."""
    if not re.fullmatch(r"[0-9a-f]{64}", mapping_sha256):
        raise ValueError("Mapping SHA-256 must be 64 lowercase hex digits")
    # This verifies the independent mapping and field-definition review events.
    mapping_snapshot(project, mapping_sha256)
    path, descriptor = _project_descriptor(project)
    descriptor["active_mapping_sha256"] = mapping_sha256
    temporary = path.with_name(f".project.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(descriptor, output, indent=2, sort_keys=True, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"project_id": descriptor["project_id"], "active_mapping_sha256": mapping_sha256}


def execute_project_run(project: Path, emit=lambda *_a, **_k: None) -> dict:
    """Run only the explicitly pinned and approved project mapping.

    Reuse the existing immutable RUN/2 publisher and its input/configuration
    snapshots, checksums, audit artifacts and recovery behavior.
    """
    _, descriptor = _project_descriptor(project)
    mapping_sha256 = descriptor.get("active_mapping_sha256")
    if not mapping_sha256:
        raise ValueError("Project has no selected mapping; use select-mapping first")
    mapping_snapshot(project, mapping_sha256)
    return execute_mapping_run(project, mapping_sha256, emit)
