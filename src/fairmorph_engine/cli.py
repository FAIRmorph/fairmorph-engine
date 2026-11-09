"""FairMorph Engine - CLI Entrypoint."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

# 1. Das Subcommand aus dem commands-Paket importieren
from fairmorph_engine.commands.poc import run_poc
from fairmorph_engine.commands.slice import (
    run_csphoc_export,
    run_dwca_export,
    run_dwca_preflight,
    verify_csphoc_project,
)

app = typer.Typer(
    name="fairmorph",
    help="FairMorph Data Transformation and Curation Engine",
    no_args_is_help=True,
)


def emit_event(event: str, **kwargs) -> None:
    """Schreibt ein NDJSON-Event ungepuffert auf stdout."""
    sys.stdout.write(json.dumps({"event": event, **kwargs}) + "\n")
    sys.stdout.flush()


def compute_sha256(file_path: Path) -> str:
    """Berechnet die SHA-256 Prüfsumme einer Datei."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


@app.callback()
def main_callback() -> None:
    """FairMorph Data Transformation and Curation Engine."""
    pass


# 2. Den importierten Befehl an der Typer-App registrieren
app.command(name="poc", help="Führt den PoC-IPC-Benchmark aus")(run_poc)
app.command(name="export-package", help="Export a validated CS-PHOC RUN as a Data Package")(
    run_csphoc_export
)
app.command(name="dwca-preflight", help="Describe the approved DwC-A target profile")(
    run_dwca_preflight
)
app.command(name="export-dwca", help="Export validated CS-PHOC Event/Occurrence archive")(
    run_dwca_export
)
app.command(name="verify-project", help="Verify project sources, RUNs and exports")(
    verify_csphoc_project
)


@app.command(name="init-project")
def init_project_command(
    project: Annotated[Path, typer.Option("--project")],
    name: Annotated[str, typer.Option("--name")] = "FAIRmorph project",
) -> None:
    """Create an empty dataset-independent project."""
    from fairmorph_engine.core.project import initialize_project

    try:
        index = initialize_project(project, name)
        emit_event(
            "result",
            status="success",
            data={"project_id": index["project_id"], "project_path": str(project.resolve())},
        )
    except (ValueError, OSError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="import-resource")
def import_resource_command(
    project: Annotated[Path, typer.Option("--project")],
    source: Annotated[Path, typer.Option("--source")],
    role: Annotated[str, typer.Option("--role")],
) -> None:
    """Import original source bytes without an implicit mapping."""
    from fairmorph_engine.core.project import import_resource

    try:
        emit_event("result", status="success", data=import_resource(project, source, role))
    except (ValueError, OSError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="run-mapping")
def run_mapping_command(
    project: Annotated[Path, typer.Option("--project", help="Initialized FAIRmorph project")],
    mapping_sha256: Annotated[
        str, typer.Option("--mapping-sha256", help="Approved mapping SHA-256")
    ],
) -> None:
    """Execute a reviewed mapping and publish a checksummed RUN."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.run_executor import execute_mapping_run

    try:
        execute_mapping_run(project, mapping_sha256, emit_event)
    except (ValueError, RuntimeError, OSError, KeyError, ImportError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="handshake")
def handshake() -> None:
    """Advertise the supported PoC contract without changing any project data."""
    emit_event(
        "result",
        status="success",
        data={
            "protocol_version": "fairmorph.poc.ndjson/1",
            "project_schema_version": "fairmorph.poc.project/1",
            "run_schema_version": "fairmorph.poc.run/2",
            "engine_version": "0.1.0",
            "commands": [
                "poc",
                "init-project",
                "import-resource",
                "run-mapping",
                "export-package",
                "dwca-preflight",
                "export-dwca",
                "verify-project",
            ],
        },
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
