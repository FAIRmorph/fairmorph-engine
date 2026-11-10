#!/usr/bin/env python3
"""Prepare a CS-PHOC project using existing FAIRmorph Engine contracts only.

This file is specific to the CS-PHOC reference project. It is NOT an Engine
operator, Workbench IPC command, migration or scientific approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from fairmorph_engine.core.export import verify_project
from fairmorph_engine.core.pipeline_run import validate_pipeline
from fairmorph_engine.core.project import import_resource, initialize_project, register_package

UPSTREAM_REVISION = "64f0b77e631c711c681306bbb56a7636ae91a471"
ORIGINALS = {
    "events": (
        "cs-phoc-events.csv",
        "d129fa00d10fa11caf5f2f0481681ea5c22cb8a6",
    ),
    "counts": (
        "cs-phoc-counts.csv",
        "d81e36792cad4de0108f7d0bcd0cef4e89d103a0",
    ),
}
EVENT_FIELDS = [
    "event_id", "season_name", "census_date_start", "census_date_end",
    "census_days", "surveyed_pst", "research_program",
]
COUNT_FIELDS = [
    "count_id", "event_id", "location", "species", "species_common",
    "total_count", "ad_female_count", "ad_male_count", "ad_unk_count",
    "juv_female_count", "juv_male_count", "juv_unk_count", "pup_count",
    "unk_female_count", "unk_male_count", "unk_unk_count",
]
THIS_DIRECTORY = Path(__file__).resolve().parent


def git_blob_sha1(path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content,
        usedforsecurity=False,
    ).hexdigest()


def source_files(source_root: Path) -> dict[str, Path]:
    root = source_root / "data" / "manuscript"
    sources = {}
    for role, (filename, expected_blob) in ORIGINALS.items():
        path = root / filename
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or symlinked source file: {path}")
        if git_blob_sha1(path) != expected_blob:
            raise ValueError(
                f"Upstream source mismatch: {filename}; expected blob {expected_blob} "
                f"from {UPSTREAM_REVISION}"
            )
        sources[role] = path
    return sources


def table_fields(names: list[str], integers: set[str]) -> list[dict]:
    return [
        {"name": name, "type": "integer" if name in integers else "string"}
        for name in names
    ]


def data_package_descriptor(imported: dict[str, dict]) -> dict:
    def resource(role: str, names: list[str], integers: set[str],
                 primary_key: str, foreign_keys: list[dict] | None = None) -> dict:
        info = imported[role]
        schema = {
            "fields": table_fields(names, integers),
            "missingValues": [""],
            "primaryKey": primary_key,
        }
        if foreign_keys:
            schema["foreignKeys"] = foreign_keys
        return {
            "name": role,
            "type": "table",
            "path": info["object_path"],
            "format": "csv",
            "mediatype": "text/csv",
            "schema": schema,
        }

    counts_fk = {
        "fields": ["event_id"],
        "reference": {"resource": "events", "fields": ["event_id"]},
    }
    return {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        "name": "cs-phoc-fairmorph-source",
        "title": "CS-PHOC source CSV resources (unreviewed FAIRmorph reference project)",
        "description": (
            "Source-level Data Package descriptor for the unchanged CS-PHOC "
            "manuscript CSV files, not a FAIRmorph RUN/export or semantic approval."
        ),
        "resources": [
            resource("events", EVENT_FIELDS, {"census_days"}, "event_id"),
            resource(
                "counts", COUNT_FIELDS,
                set(COUNT_FIELDS[5:]), "count_id", [counts_fk],
            ),
        ],
    }


def prepare(source_root: Path, project: Path) -> dict:
    if project.exists() or project.is_symlink():
        raise ValueError("Refusing to overwrite or reinitialize any existing project path")
    original = source_files(source_root)
    initialize_project(project, "CS-PHOC reference (v0.13)")
    imported = {
        role: import_resource(project, file, role)
        for role, file in original.items()
    }
    package = register_package(project, "cs-phoc-manuscript-sources", imported)
    if {entry["name"] for entry in package["resources"]} != {"events", "counts"}:
        raise ValueError("Virtual package does not reference both imported resources")

    drafts = project / "configurations" / "drafts"
    drafts.mkdir(parents=True, exist_ok=False)
    template = json.loads(
        (THIS_DIRECTORY / "configurations/drafts/pipeline-technical.json")
        .read_text(encoding="utf-8")
    )
    for role in imported:
        template["resources"][role]["resource_id"] = imported[role]["resource_id"]
    validate_pipeline(template)
    with (drafts / "pipeline-technical.json").open("x", encoding="utf-8") as stream:
        json.dump(template, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    shutil.copyfile(
        THIS_DIRECTORY / "configurations/drafts/dataset-metadata.json",
        drafts / "dataset-metadata.json",
    )

    # Data Package describes the SAME imported source objects; it is not
    # the FAIRmorph virtual descriptor and is not an approved export.
    descriptor = data_package_descriptor(imported)
    with (project / "datapackage.json").open("x", encoding="utf-8") as stream:
        json.dump(descriptor, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    verification = verify_project(project)
    if verification["source_objects"] != 2 or verification["completed_runs"] != 0:
        raise ValueError("Unexpected FAIRmorph project inventory")
    return {
        "upstream_revision": UPSTREAM_REVISION,
        "project": str(project.resolve()),
        "package_id": package["package_id"],
        "imported": imported,
        "project_verification": verification,
        "next": "Review mappings and title; register pipeline only after inspecting draft.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.source_root, arguments.project), indent=2))


if __name__ == "__main__":
    main()
