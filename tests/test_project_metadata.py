"""P0.6 dataset metadata revision contract – project files, no scientific CLI arguments."""
import json

import pytest

from fairmorph_engine.core.project import initialize_project
from fairmorph_engine.core.project_metadata import (
    approve_dataset_metadata,
    dataset_metadata_snapshot,
    show_dataset_metadata,
    stage_dataset_metadata,
)


def draft(project, title, parent=None):
    path = project / "configurations" / "drafts" / "dataset-metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "schema_version": "fairmorph.dataset-metadata/1",
            "title": title,
            "parent_revision_sha256": parent,
        }), encoding="utf-8",
    )


def approval(project, sha, reviewer="researcher"):
    path = project / "configurations" / "drafts" / "dataset-metadata-approval.json"
    path.write_text(json.dumps({
        "schema_version": "fairmorph.dataset-metadata-approval/1",
        "decision": "approve",
        "revision_sha256": sha,
        "confirmed_by": reviewer,
    }), encoding="utf-8")


def test_draft_stage_approve_and_historical_revision(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    assert show_dataset_metadata(project)["status"] == "unconfigured"
    assert dataset_metadata_snapshot(project) is None

    draft(project, "User-defined scientific dataset title")
    staged = stage_dataset_metadata(project)
    sha1 = staged["revision_sha256"]
    assert staged["status"] == "staged"
    assert show_dataset_metadata(project)["status"] == "unconfigured"
    assert dataset_metadata_snapshot(project) is None

    approval(project, sha1)
    assert approve_dataset_metadata(project)["status"] == "approved"
    old = dataset_metadata_snapshot(project)
    assert old["revision_sha256"] == sha1
    assert old["title"] == "User-defined scientific dataset title"
    assert old["confirmed_by"] == "researcher"

    draft(project, "Revised scientific dataset title", sha1)
    sha2 = stage_dataset_metadata(project)["revision_sha256"]
    assert sha2 != sha1
    assert show_dataset_metadata(project)["revision_sha256"] == sha1
    approval(project, sha2)
    approve_dataset_metadata(project)
    assert show_dataset_metadata(project)["revision_sha256"] == sha2
    assert dataset_metadata_snapshot(project, sha1) == old
    assert dataset_metadata_snapshot(project)["title"] == "Revised scientific dataset title"
    assert (project / "configurations/dataset-metadata" / f"{sha1}.json").exists()


def test_stale_drafts_and_double_approval_are_rejected(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    draft(project, "First scientific title")
    sha = stage_dataset_metadata(project)["revision_sha256"]
    approval(project, sha)
    approve_dataset_metadata(project)
    with pytest.raises(ValueError, match="already active|Stale"):
        approve_dataset_metadata(project)
    draft(project, "Outdated revised title", None)
    with pytest.raises(ValueError, match="Stale"):
        stage_dataset_metadata(project)
    draft(project, "First scientific title", sha)
    staged = stage_dataset_metadata(project)
    assert staged["revision_sha256"] != sha


def test_unapproved_and_invalid_files_are_rejected(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    draft(project, "A descriptive dataset title")
    sha = stage_dataset_metadata(project)["revision_sha256"]
    approval(project, sha, "  ")
    with pytest.raises(Exception):
        approve_dataset_metadata(project)
    approval(project, "f" * 64)
    with pytest.raises(ValueError, match="Unknown"):
        approve_dataset_metadata(project)
    assert show_dataset_metadata(project)["status"] == "unconfigured"
    draft(project, "x")
    with pytest.raises(Exception):
        stage_dataset_metadata(project)


def test_tampered_staged_revision_is_detected(tmp_path):
    project = tmp_path / "project"
    initialize_project(project)
    draft(project, "A scientific dataset title")
    sha = stage_dataset_metadata(project)["revision_sha256"]
    revision = project / "configurations/dataset-metadata" / f"{sha}.json"
    revision.write_text('{"title":"tampered"}', encoding="utf-8")
    approval(project, sha)
    with pytest.raises(ValueError, match="changed or missing"):
        approve_dataset_metadata(project)


def test_sqlite_revisions_and_approval_are_append_only(tmp_path):
    import sqlite3

    project = tmp_path / "project"
    initialize_project(project)
    draft(project, "A scientific dataset title")
    sha = stage_dataset_metadata(project)["revision_sha256"]
    approval(project, sha)
    approve_dataset_metadata(project)
    with sqlite3.connect(project / "catalog/catalog.sqlite") as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM dataset_metadata_revisions WHERE revision_sha256=?", (sha,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE dataset_metadata_approvals SET confirmed_by='other'")


def test_generic_run_pins_approved_title_and_preserves_older_run(tmp_path):
    from fairmorph_engine.core.export import verify_project
    from fairmorph_engine.core.pipeline_run import register_pipeline
    from fairmorph_engine.core.project import import_resource
    from fairmorph_engine.core.project_execution import (
        execute_project_run,
        select_project_pipeline,
    )

    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source.csv"
    source.write_text("sample,count\nS1,0\nS2,3\n", encoding="utf-8")
    resource = import_resource(project, source, "survey")
    pipeline = {
        "schema_version": "fairmorph.pipeline/1",
        "resources": {
            "survey": {"resource_id": resource["resource_id"], "format": "csv"},
        },
        "steps": [{
            "id": "choose", "operator": "table.select/1",
            "inputs": ["survey"], "output": "selected",
            "parameters": {"columns": ["sample", "count"]},
        }],
        "outputs": ["selected"],
    }
    sha = register_pipeline(project, pipeline)["pipeline_sha256"]
    select_project_pipeline(project, sha)

    first = execute_project_run(project)
    assert first["schema_version"] == "fairmorph.poc.run/2"
    first_snapshot = json.loads(
        (project / "runs" / first["run_id"] / "inputs.snapshot.json").read_text()
    )
    assert "dataset_metadata_snapshot" not in first_snapshot

    draft(project, "Title of approved survey dataset")
    rev1 = stage_dataset_metadata(project)["revision_sha256"]
    approval(project, rev1)
    approve_dataset_metadata(project)
    second = execute_project_run(project)
    second_snapshot = json.loads(
        (project / "runs" / second["run_id"] / "inputs.snapshot.json").read_text()
    )
    assert second_snapshot["dataset_metadata_snapshot"]["title"] == "Title of approved survey dataset"
    assert second_snapshot["dataset_metadata_snapshot"]["revision_sha256"] == rev1

    draft(project, "Later revised title of survey dataset", rev1)
    rev2 = stage_dataset_metadata(project)["revision_sha256"]
    approval(project, rev2)
    approve_dataset_metadata(project)

    assert verify_project(project)["completed_runs"] == 2
    assert json.loads(
        (project / "runs" / second["run_id"] / "inputs.snapshot.json").read_text()
    ) == second_snapshot

    revision_file = project / "configurations" / "dataset-metadata" / f"{rev1}.json"
    revision_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="changed or missing"):
        verify_project(project)
