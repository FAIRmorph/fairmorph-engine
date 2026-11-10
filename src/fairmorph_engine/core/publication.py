"""Validate external publication intent against an immutable generic RUN/2."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from fairmorph_engine.core.export import sha256, verified_run


def validate_publication_intent(
    project: Path, run_id: str, profile_file: Path, metadata_file: Path
) -> dict:
    """Preflight only: does not approve a profile or generate EML/DwC-A."""
    schema_path = (
        Path(__file__).resolve().parents[1] / "contracts" / "publication-profile.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not profile_file.is_file() or profile_file.is_symlink():
        raise ValueError("Publication profile must be an existing regular file")
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(profile)
    if "dwca/1" in profile["formats"]:
        dwca = profile["dwca"]
        tables = [(dwca["core"], dwca["core_id_field"], dwca["core_fields"])]
        tables.extend(
            (extension["row_type"], extension["core_id_field"], extension["fields"])
            for extension in dwca.get("extensions", [])
        )
        if len({name for name, _, _ in tables}) != len(tables):
            raise ValueError("Duplicate Darwin Core row type")
        for row_type, identifier, bindings in tables:
            source_fields = [item["source_field"] for item in bindings]
            terms = [item["term"] for item in bindings]
            if len(source_fields) != len(set(source_fields)) or len(terms) != len(set(terms)):
                raise ValueError(f"Duplicate {row_type} source field or Darwin Core term")
            id_term = f"http://rs.tdwg.org/dwc/terms/{row_type.lower()}ID"
            matches = [item for item in bindings if item["term"] == id_term]
            if len(matches) != 1 or matches[0]["source_field"] != identifier:
                raise ValueError(f"{row_type} must bind its identifier to {id_term}")
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
        "field_bindings_verified": False,
        "publication_ready": False,
    }
