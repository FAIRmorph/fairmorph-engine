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
