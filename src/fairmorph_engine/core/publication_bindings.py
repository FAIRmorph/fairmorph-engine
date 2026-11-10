"""Cross-check external publication mappings without embedding project semantics."""

import json
from pathlib import Path

from fairmorph_engine.core.publication import validate_publication_intent
from fairmorph_engine.core.publication_projection import validate_publication_projection


def validate_publication_binding_columns(
    project: Path,
    run_id: str,
    profile_file: Path,
    metadata_file: Path,
    projection_file: Path,
) -> dict:
    """Require all declared DwC terms to reference pinned projection columns."""
    intent = validate_publication_intent(project, run_id, profile_file, metadata_file)
    projection = validate_publication_projection(project, run_id, projection_file)
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    plan = json.loads(projection_file.read_text(encoding="utf-8"))
    if profile["run_manifest_sha256"] != plan["run_manifest_sha256"]:
        raise ValueError("Publication and projection RUN pins differ")
    if "dwca/1" not in profile["formats"]:
        raise ValueError("Binding column validation requires declared DwC-A intent")

    dwca = profile["dwca"]
    bindings = {dwca["core"]: dwca["core_fields"]}
    bindings.update(
        {extension["row_type"]: extension["fields"] for extension in dwca.get("extensions", [])}
    )
    tables = {table["row_type"]: set(table["columns"]) for table in plan["tables"]}
    if set(bindings) != set(tables):
        raise ValueError("Publication and projection row types differ")
    for row_type, fields in bindings.items():
        missing = {field["source_field"] for field in fields} - tables[row_type]
        if missing:
            raise ValueError(f"Publication bindings missing from {row_type}: {sorted(missing)}")
    return {
        "status": "validated",
        "run_id": run_id,
        "profile_id": intent["profile_id"],
        "row_types": projection["row_types"],
        "binding_columns_verified": True,
        "publication_ready": False,
    }
