"""Project-driven entry point: explicit approval, no external config and no guessing."""

import json

import pytest
from typer.testing import CliRunner

from fairmorph_engine.cli import app
from fairmorph_engine.core.project import initialize_project
from fairmorph_engine.core.project_execution import (
    execute_project_run,
    select_project_mapping,
)

SHA = "a" * 64


def test_unselected_project_refuses_to_run(tmp_path, monkeypatch):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    monkeypatch.setattr(
        "fairmorph_engine.core.project_execution.execute_mapping_run",
        lambda *_args, **_kwargs: pytest.fail("Unselected project must not execute"),
    )
    with pytest.raises(ValueError, match="no selected mapping"):
        execute_project_run(project)
    result = CliRunner().invoke(app, ["run-pipeline", "--project", str(project)])
    assert result.exit_code == 1
    assert '"status": "error"' in result.output


def test_selection_requires_review_and_is_atomic(tmp_path, monkeypatch):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    original = (project / "project.json").read_bytes()

    def reject(*_args):
        raise ValueError("RUN requires an approved mapping version")

    monkeypatch.setattr("fairmorph_engine.core.project_execution.mapping_snapshot", reject)
    with pytest.raises(ValueError, match="approved"):
        select_project_mapping(project, SHA)
    assert (project / "project.json").read_bytes() == original
    with pytest.raises(ValueError, match="SHA-256"):
        select_project_mapping(project, "../unsafe")


def test_project_selected_mapping_executes_without_config(tmp_path, monkeypatch):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    seen = []
    monkeypatch.setattr(
        "fairmorph_engine.core.project_execution.mapping_snapshot",
        lambda p, sha: seen.append(("approved", sha)),
    )

    def execute(p, sha, emit):
        seen.append(("executed", sha))
        emit("result", status="success", data={"run_id": "run-test"})
        return {"run_id": "run-test"}

    monkeypatch.setattr("fairmorph_engine.core.project_execution.execute_mapping_run", execute)
    selected = select_project_mapping(project, SHA)
    assert selected["active_mapping_sha256"] == SHA
    assert json.loads((project / "project.json").read_text())["active_mapping_sha256"] == SHA
    assert execute_project_run(project)["run_id"] == "run-test"
    result = CliRunner().invoke(app, ["run-pipeline", "--project", str(project)])
    assert result.exit_code == 0
    assert '"run_id": "run-test"' in result.output
    assert seen == [
        ("approved", SHA),
        ("approved", SHA),
        ("executed", SHA),
        ("approved", SHA),
        ("executed", SHA),
    ]


def test_no_implicit_catalog_mapping_selection(tmp_path):
    project = tmp_path / "survey.fairmorph"
    initialize_project(project)
    descriptor = json.loads((project / "project.json").read_text())
    assert "active_mapping_sha256" not in descriptor
    with pytest.raises(ValueError, match="no selected mapping"):
        execute_project_run(project)
