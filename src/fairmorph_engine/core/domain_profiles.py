"""Local v0.12 domain-profile contracts and exact schema-version pins.

A profile is a user-selected JSON Schema, not an instruction to infer
scientific meaning or to assign a Darwin Core publication profile.
"""

import json
import math
from datetime import date, datetime
from pathlib import Path

import polars as pl
from jsonschema import Draft202012Validator, FormatChecker

from fairmorph_engine.core.registry import _catalog, digest
from fairmorph_engine.core.schema_registry import get_schema, register_schema

_BUNDLE = Path(__file__).resolve().parents[1] / "contracts" / "profile-bundle.v012.json"
_TECHNICAL_FIELDS = frozenset({
    "entity_id",
    "parent_event_ref",
    "sampling_event_ref",
    "occurrence_ref",
})
_PIN_FIELDS = frozenset({"schema_id", "schema_version", "schema_sha256"})


def profile_bundle() -> dict:
    """Load the checked-in v0.12 schemas; never fetch remote references."""
    bundle = json.loads(_BUNDLE.read_text(encoding="utf-8"))
    if bundle["schema_version"] != "fairmorph.poc.profile-bundle/1":
        raise ValueError("Unsupported bundled profile contract")
    for schema in [*bundle["domains"].values(), bundle["envelope"]]:
        Draft202012Validator.check_schema(schema)
    return bundle


def install_builtin_profiles(project: Path, confirmed_by: str) -> dict:
    """Explicitly install and approve the locally bundled v0.12 draft profiles."""
    if not isinstance(confirmed_by, str) or not confirmed_by.strip():
        raise ValueError("Profile installation needs an explicit confirming user")
    bundle = profile_bundle()
    pins = {}
    for kind, schema in bundle["domains"].items():
        pins[kind] = register_schema(
            project,
            schema_id=schema["$id"],
            schema_version=bundle["domain_version"],
            schema=schema,
            kind="domain",
            status="approved",
            reviewer=confirmed_by.strip(),
        )
    pins["metadata-envelope"] = register_schema(
        project,
        schema_id=bundle["envelope"]["$id"],
        schema_version=bundle["envelope_version"],
        schema=bundle["envelope"],
        kind="core",
        status="approved",
        reviewer=confirmed_by.strip(),
    )
    return pins


def _validate_pin_shape(pin: dict) -> None:
    if not isinstance(pin, dict) or set(pin) != _PIN_FIELDS:
        raise ValueError("Profile pin requires schema_id, schema_version and schema_sha256")
    if not all(isinstance(v, str) and v.strip() for v in pin.values()):
        raise ValueError("Profile pins cannot be empty")


def validate_profile_bindings(config: dict) -> None:
    """Check the explicit shape without project access (pipeline registration preflight)."""
    selected = config.get("profile_bindings")
    if selected is None:
        return  # Legacy P0.2 config remains executable without a P0.5 profile claim.
    if (
        "entities" not in config
        or not isinstance(selected, dict)
        or set(selected) != {"envelope", "entities"}
        or not isinstance(selected["entities"], dict)
        or set(selected["entities"]) != set(config["entities"])
    ):
        raise ValueError("Profile bindings must cover every selected entity and the envelope")
    _validate_pin_shape(selected["envelope"])
    for pin in selected["entities"].values():
        _validate_pin_shape(pin)


def _registered_schema(project: Path, pin: dict, expected_kind: str) -> dict:
    _validate_pin_shape(pin)
    with _catalog(project) as db:
        row = db.execute(
            "SELECT kind, status FROM schema_versions WHERE schema_id=? AND schema_version=?",
            (pin["schema_id"], pin["schema_version"]),
        ).fetchone()
    if row != (expected_kind, "approved"):
        raise ValueError("Profile schema is not an explicitly approved registry version")
    schema, checksum = get_schema(
        project, schema_id=pin["schema_id"], schema_version=pin["schema_version"]
    )
    if checksum != pin["schema_sha256"]:
        raise ValueError("Profile schema SHA-256 pin differs from registry content")
    return schema


def resolve_profiles(project: Path, config: dict) -> dict | None:
    """Resolve only the explicit schema IDs/versions/hashes in a pipeline config."""
    validate_profile_bindings(config)
    pins = config.get("profile_bindings")
    if pins is None:
        return None
    bundle = profile_bundle()
    envelope = _registered_schema(project, pins["envelope"], "core")
    if envelope["$id"] != bundle["envelope"]["$id"]:
        raise ValueError("Unsupported metadata envelope identity for this vertical PoC")
    domains = {}
    for kind, pin in pins["entities"].items():
        schema = _registered_schema(project, pin, "domain")
        if schema["$id"] != bundle["domains"][kind]["$id"]:
            raise ValueError("Profile schema does not match its selected entity kind")
        domains[kind] = schema
    return {"envelope": envelope, "entities": domains}


def profile_bindings_for(project: Path, entity_types: list[str]) -> dict:
    """Build an explicit mapping template using already approved v0.12 versions."""
    bundle = profile_bundle()
    if not entity_types or set(entity_types) - set(bundle["domains"]):
        raise ValueError("Unknown domain profile selection")
    pins = {}
    for kind in [*entity_types, "metadata-envelope"]:
        schema = bundle["envelope"] if kind == "metadata-envelope" else bundle["domains"][kind]
        version = bundle["envelope_version"] if kind == "metadata-envelope" else bundle["domain_version"]
        db_kind = "core" if kind == "metadata-envelope" else "domain"
        _registered_schema(
            project,
            {"schema_id": schema["$id"], "schema_version": version, "schema_sha256": digest(schema)},
            db_kind,
        )
        pins[kind] = {
            "schema_id": schema["$id"],
            "schema_version": version,
            "schema_sha256": digest(schema),
        }
    return {
        "envelope": pins["metadata-envelope"],
        "entities": {kind: pins[kind] for kind in entity_types},
    }


def _compatible_json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numeric profile values cannot be serialized as JSON")
    if isinstance(value, dict):
        return {key: _compatible_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compatible_json(item) for item in value]
    return value


def validate_attributes(schema: dict, attributes: dict, *, context: str) -> None:
    """Validate a single logical entity's declared attributes, including formats."""
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(attributes)
    except Exception as error:
        from jsonschema.exceptions import ValidationError

        if not isinstance(error, ValidationError):
            raise
        location = "/".join(str(part) for part in error.absolute_path)
        raise ValueError(f"{context} profile validation failed at {location or '/'}: {error.message}") from error
    if schema["title"] == "SamplingEvent" and "event_time" in attributes:
        value = attributes["event_time"]
        if "start" in value and "end" in value:
            start = datetime.fromisoformat(value["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(value["end"].replace("Z", "+00:00"))
            if start.tzinfo is None or end.tzinfo is None or start > end:
                raise ValueError(f"{context} event_time start must precede end with timezones")


def validate_entity_profiles(
    resolved: dict | None, entity_frames: dict[str, pl.DataFrame]
) -> None:
    """Validate concrete projected rows; technical IDs and FKs are separate fields."""
    if resolved is None:
        return
    for kind, frame in entity_frames.items():
        schema = resolved["entities"][kind]
        for row_index, row in enumerate(frame.to_dicts()):
            attributes = _compatible_json({
                name: value for name, value in row.items()
                if name not in _TECHNICAL_FIELDS
            })
            validate_attributes(schema, attributes, context=f"{kind} row {row_index}")


def validate_metadata_envelope(resolved: dict, kind: str, envelope: dict) -> None:
    """Both JSON Schemas are required; field-provenance pointers must be real."""
    Draft202012Validator(
        resolved["envelope"], format_checker=FormatChecker()
    ).validate(envelope)
    if envelope["entity_type"] != kind:
        raise ValueError("Metadata envelope entity_type differs from selected domain profile")
    validate_attributes(
        resolved["entities"][kind], envelope["attributes"], context=f"{kind} metadata"
    )
    attributes = envelope["attributes"]
    pointers = {"/attributes/" + k.replace("~", "~0").replace("/", "~1") for k in attributes}
    declared = set(envelope["field_provenance"])
    if pointers != declared:
        raise ValueError("Metadata field_provenance must cover exact attribute pointers")
