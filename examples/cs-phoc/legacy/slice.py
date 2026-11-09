"""Fixed CS-PHOC PoC transformation entry point (no interactive data selection)."""

from pathlib import Path
from typing import Annotated

import typer
from jsonschema.exceptions import ValidationError

from csphoc import run_slice


def run_csphoc(
    project: Annotated[Path, typer.Option("--project", help="Local FAIRmorph project directory")],
    events: Annotated[
        Path | None, typer.Option("--events", help="Unmodified CS-PHOC events CSV")
    ] = None,
    counts: Annotated[
        Path | None, typer.Option("--counts", help="Unmodified CS-PHOC counts CSV")
    ] = None,
    decision: Annotated[
        Path | None, typer.Option("--decision", help="Approved static mapping JSON")
    ] = None,
) -> None:
    """Transform the approved CS-PHOC fixture and publish an immutable PoC run."""
    # Import locally: the event writer is owned by the CLI, avoiding duplicate protocols.
    from fairmorph_engine.cli import emit_event

    try:
        # Explicitly select the example resources; no data bundled with the engine.
        if events is None or counts is None or decision is None:
            raise ValueError(
                "CS-PHOC requires --events, --counts and --decision from an example project"
            )
        run_slice(project, events, counts, decision, emit_event)
    except (ValueError, RuntimeError, OSError, KeyError, ImportError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


def run_csphoc_export(
    project: Annotated[Path, typer.Option("--project", help="Existing FAIRmorph PoC project")],
    run_id: Annotated[str, typer.Option("--run-id", help="Completed, immutable RUN identifier")],
) -> None:
    """Materialize a standalone Data Package from a validated RUN."""
    from fairmorph_engine.cli import emit_event
    from fairmorph_engine.core.export import export_data_package

    try:
        export_data_package(project, run_id, emit_event)
    except (ValueError, RuntimeError, OSError, KeyError, ImportError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


def run_dwca_preflight() -> None:
    """Describe the author-defined, offline CS-PHOC DwC-A target profile."""
    from fairmorph_engine.cli import emit_event
    from fairmorph_engine.core.export import dwca_profile

    emit_event("result", status="success", data=dwca_profile())


def run_dwca_export(
    project: Annotated[Path, typer.Option("--project", help="Existing CS-PHOC project")],
    run_id: Annotated[str, typer.Option("--run-id", help="Completed CS-PHOC RUN identifier")],
) -> None:
    """Write an independently checksummed Event/Occurrence Darwin Core Archive."""
    from fairmorph_engine.cli import emit_event
    from fairmorph_engine.core.export import export_dwca

    try:
        export_dwca(project, run_id, emit_event)
    except (ValueError, RuntimeError, OSError, KeyError, ImportError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


def verify_csphoc_project(
    project: Annotated[
        Path, typer.Option("--project", help="Existing FAIRmorph project directory")
    ],
) -> None:
    """Verify local source, RUN, and export integrity without modifying the project."""
    from fairmorph_engine.cli import emit_event
    from fairmorph_engine.core.export import verify_project

    try:
        emit_event("result", status="success", data=verify_project(project))
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error
