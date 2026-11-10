"""Architecture regression: the public CLI has no dataset-specific RUN entry point."""

from typer.testing import CliRunner

from fairmorph_engine.cli import app


def test_only_generic_run_entry_point_is_advertised():
    runner = CliRunner()
    response = runner.invoke(app, ["--help"])
    assert response.exit_code == 0
    assert "run-mapping" in response.stdout
    assert "csphoc" not in response.stdout.lower()


def test_removed_dataset_specific_command_cannot_execute():
    response = CliRunner().invoke(app, ["csphoc"])
    assert response.exit_code != 0


def test_generic_mapping_commands_are_public():
    runner = CliRunner()
    response = runner.invoke(app, ["--help"])
    assert response.exit_code == 0
    assert "stage-csv-mapping" in response.stdout
    assert "approve-mapping" in response.stdout


def test_mapping_approval_requires_reviewer_option(tmp_path):
    response = CliRunner().invoke(
        app,
        ["approve-mapping", "--project", str(tmp_path), "--mapping-sha256", "a" * 64],
    )
    assert response.exit_code != 0
