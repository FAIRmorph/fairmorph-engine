"""Regression tests for the dataset-independent project foundation."""

import json
import sqlite3
import subprocess
import sys

import pytest

from fairmorph_engine.core.project import initialize_project, import_resource, register_package
from fairmorph_engine.core.export import verify_project


def test_arbitrary_import_and_virtual_package(tmp_path):
    project = tmp_path / "research.fairmorph"
    index = initialize_project(project, "Independent research")
    assert index["package_ids"] == []
    a, b = tmp_path / "one.txt", tmp_path / "two.txt"
    a.write_bytes(b"same bytes\n")
    b.write_bytes(b"same bytes\n")
    first = import_resource(project, a, "measurements")
    second = import_resource(project, b, "records")
    assert first["sha256"] == second["sha256"]
    assert first["resource_id"] != second["resource_id"]
    assert first["state"] == "imported_unmapped"
    assert len(list((project / "objects/sha256").glob("*/*"))) == 1
    with sqlite3.connect(project / "catalog/catalog.sqlite") as connection:
        assert connection.execute("SELECT count(*) FROM source_resources").fetchone()[0] == 2
    package = register_package(project, "field-campaign", {"measurements": first, "records": second})
    assert len(package["resources"]) == 2
    assert register_package(project, "field-campaign", {"measurements": first, "records": second}) == package
    assert verify_project(project)["completed_runs"] == 0
    updated = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert updated["package_ids"] == ["field-campaign"]
    assert len(updated["input_objects"]) == 1
    assert initialize_project(project)["project_id"] == index["project_id"]


def test_detect_corrupted_immutable_object(tmp_path):
    project = tmp_path / "research.fairmorph"
    initialize_project(project)
    sample = tmp_path / "table.csv"
    sample.write_bytes(b"x,y\n1,2\n")
    entry = import_resource(project, sample, "table")
    (project / entry["object_path"]).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="corrupted"):
        import_resource(project, sample, "table")


def test_headless_cli(tmp_path):
    project = tmp_path / "headless.fairmorph"
    init = subprocess.run([sys.executable, "-m", "fairmorph_engine.cli", "init-project",
                           "--project", str(project)], capture_output=True, text=True, check=True)
    assert json.loads(init.stdout.splitlines()[-1])["status"] == "success"
    sample = tmp_path / "arbitrary.txt"
    sample.write_text("not a census", encoding="utf-8")
    imported = subprocess.run([sys.executable, "-m", "fairmorph_engine.cli", "import-resource",
                               "--project", str(project), "--source", str(sample), "--role",
                               "arbitrary"], capture_output=True, text=True, check=True)
    assert json.loads(imported.stdout.splitlines()[-1])["data"]["state"] == "imported_unmapped"
