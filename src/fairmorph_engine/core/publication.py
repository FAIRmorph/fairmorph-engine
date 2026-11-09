"""Validate external publication intent against an immutable generic RUN/2."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from fairmorph_engine.core.export import verified_run, sha256


def validate_publication_intent(project: Path, run_id: str, profile_file: Path, metadata_file: Path) -> dict:
    """Preflight only: does not approve a profile or generate EML/DwC-A."""
    schema_path = Path(__file__).resolve().parents[1] / "contracts" / "publication-profile.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(profile)
    run_dir, manifest = verified_run(project, run_id)
    if manifest["schema_version"] != "fairmorph.poc.run/2":
        raise ValueError("Publication intent requires a generic RUN/2")
    if sha256(run_dir / "manifest.json") != profile["run_manifest_sha256"]:
        raise ValueError("Publication intent RUN manifest SHA-256 mismatch")
    if not metadata_file.is_file() or metadata_file.is_symlink():
        raise ValueError("Publication metadata must be an existing regular file")
    if sha256(metadata_file) != profile["metadata_sha256"]:
        raise ValueError("Publication metadata SHA-256 mismatch")
    return {
        "status": "validated",
        "run_id": run_id,
        "profile_id": profile["profile_id"],
        "formats": profile["formats"],
        "publication_ready": False,
    }
