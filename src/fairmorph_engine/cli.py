"""FairMorph Engine - CLI Entrypoint."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

# 1. Das Subcommand aus dem commands-Paket importieren
from fairmorph_engine.commands.poc import run_poc

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


@app.command(name="export-package")
def export_package_command(
    project: Annotated[Path, typer.Option("--project", help="Existing FAIRmorph project")],
    run_id: Annotated[str, typer.Option("--run-id", help="Verified immutable RUN identifier")],
) -> None:
    """Create an independently versioned Data Package from a verified RUN."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.export import export_data_package

    try:
        export_data_package(project, run_id, emit_event)
    except (ValueError, RuntimeError, OSError, KeyError, ImportError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


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


@app.command(name="stage-csv-mapping")
def stage_csv_mapping_command(
    project: Annotated[Path, typer.Option("--project")],
    resource_id: Annotated[str, typer.Option("--resource-id")],
    profile: Annotated[Path, typer.Option("--profile")],
) -> None:
    """Register an external mapping and field definitions as unapproved drafts."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.profile import stage_csv_mapping

    try:
        emit_event(
            "result", status="success", data=stage_csv_mapping(project, resource_id, profile)
        )
    except (ValueError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="approve-mapping")
def approve_mapping_command(
    project: Annotated[Path, typer.Option("--project")],
    mapping_sha256: Annotated[str, typer.Option("--mapping-sha256")],
    confirmed_by: Annotated[str, typer.Option("--confirmed-by")],
) -> None:
    """Explicitly approve a staged mapping and its field revisions."""
    from fairmorph_engine.core.profile import approve_staged_mapping

    try:
        emit_event(
            "result",
            status="success",
            data=approve_staged_mapping(project, mapping_sha256, confirmed_by),
        )
    except (ValueError, OSError, KeyError) as error:
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


@app.command(name="verify-project")
def verify_project_command(
    project: Annotated[Path, typer.Option("--project", help="Existing FAIRmorph project")],
) -> None:
    """Verify source objects, immutable RUN artifacts and exports."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.export import verify_project

    try:
        emit_event("result", status="success", data=verify_project(project))
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="reconcile-runs")
def reconcile_runs_command(
    project: Annotated[Path, typer.Option("--project", help="Existing FAIRmorph project")],
) -> None:
    """Explicitly recover interrupted RUN publication while no writer is active."""
    from fairmorph_engine.core.run_recovery import reconcile_runs

    try:
        emit_event("result", status="success", data=reconcile_runs(project))
    except (ValueError, OSError, KeyError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="select-mapping")
def select_mapping_command(
    project: Annotated[Path, typer.Option("--project", help="Existing FAIRmorph project")],
    mapping_sha256: Annotated[
        str, typer.Option("--mapping-sha256", help="Explicitly approved mapping revision")
    ],
) -> None:
    """Pin an approved mapping in project.json without changing Data Package descriptors."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.project_execution import select_project_mapping

    try:
        emit_event(
            "result",
            status="success",
            data=select_project_mapping(project, mapping_sha256),
        )
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="run-pipeline")
def run_pipeline_command(
    project: Annotated[
        Path, typer.Option("--project", help="Project with explicitly selected mapping")
    ] = Path("."),
) -> None:
    """Execute the project's approved mapping using the immutable RUN/2 publisher."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.project_execution import execute_project_run

    try:
        execute_project_run(project, emit_event)
    except (ValueError, RuntimeError, OSError, KeyError, ImportError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="register-pipeline")
def register_pipeline_command(
    project: Annotated[Path, typer.Option("--project")],
    definition: Annotated[
        Path, typer.Option("--definition", help="Declarative pipeline JSON to register")
    ],
) -> None:
    """Register a content-addressed pipeline configuration in the project."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.pipeline_run import register_pipeline

    try:
        if not definition.is_file() or definition.is_symlink():
            raise ValueError("Pipeline definition must be a regular file")
        config = json.loads(definition.read_text(encoding="utf-8"))
        emit_event("result", status="success", data=register_pipeline(project, config))
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="select-pipeline")
def select_pipeline_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
) -> None:
    """Bind the project to an immutable, explicitly declared DAG."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.project_execution import select_project_pipeline

    try:
        emit_event(
            "result", status="success", data=select_project_pipeline(project, pipeline_sha256)
        )
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="confirm-projection")
def confirm_projection_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
    confirmed_by: Annotated[str, typer.Option("--confirmed-by")],
) -> None:
    """Confirm version-pinned entity mappings as the responsible user."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.entity_projection import confirm_projection

    try:
        emit_event(
            "result",
            status="success",
            data=confirm_projection(project, pipeline_sha256, confirmed_by),
        )
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="assert-relation")
def assert_relation_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
    predicate: Annotated[str, typer.Option("--predicate")],
    subject_id: Annotated[str, typer.Option("--subject-id")],
    object_id: Annotated[str, typer.Option("--object-id")],
    confirmed_by: Annotated[str, typer.Option("--confirmed-by")],
    source_reference: Annotated[str, typer.Option("--source-reference")],
) -> None:
    """Record a confirmed, versioned relation assertion; no second reviewer."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.relation_assertions import assert_relation

    try:
        data = assert_relation(
            project,
            pipeline_sha256,
            predicate,
            subject_id,
            object_id,
            confirmed_by,
            source_reference,
        )
        emit_event("result", status="success", data=data)
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="replace-relation")
def replace_relation_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
    relation_id: Annotated[str, typer.Option("--relation-id")],
    object_id: Annotated[str, typer.Option("--object-id")],
    confirmed_by: Annotated[str, typer.Option("--confirmed-by")],
    source_reference: Annotated[str, typer.Option("--source-reference")],
) -> None:
    """Revise the target of an active relation by a new assertion."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.relation_assertions import replace_relation

    try:
        data = replace_relation(
            project,
            pipeline_sha256,
            relation_id,
            object_id,
            confirmed_by,
            source_reference,
        )
        emit_event("result", status="success", data=data)
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="retract-relation")
def retract_relation_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
    relation_id: Annotated[str, typer.Option("--relation-id")],
    confirmed_by: Annotated[str, typer.Option("--confirmed-by")],
    source_reference: Annotated[str, typer.Option("--source-reference")],
) -> None:
    """Revoke an active relation without erasing its history."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.relation_assertions import retract_relation

    try:
        data = retract_relation(
            project,
            pipeline_sha256,
            relation_id,
            confirmed_by,
            source_reference,
        )
        emit_event("result", status="success", data=data)
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="show-relations")
def show_relations_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
) -> None:
    """Show the pinned profile and current confirmed relations."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.relation_assertions import relation_snapshot

    try:
        emit_event(
            "result",
            status="success",
            data=relation_snapshot(project, pipeline_sha256),
        )
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="install-profile-contracts")
def install_profile_contracts_command(
    project: Annotated[Path, typer.Option("--project")],
    confirmed_by: Annotated[str, typer.Option("--confirmed-by")],
) -> None:
    """Install explicitly approved local v0.12 schema and metadata contracts."""
    from fairmorph_engine.core.domain_profiles import install_builtin_profiles

    try:
        emit_event(
            "result",
            status="success",
            data=install_builtin_profiles(project, confirmed_by),
        )
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="profile-bindings")
def profile_bindings_command(
    project: Annotated[Path, typer.Option("--project")],
    entities: Annotated[str, typer.Option("--entities")],
) -> None:
    """Show a project-resolved, explicit profile pin template for the DAG."""
    from fairmorph_engine.core.domain_profiles import profile_bindings_for

    try:
        kinds = [value.strip() for value in entities.split(",") if value.strip()]
        emit_event("result", status="success", data=profile_bindings_for(project, kinds))
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="record-metadata")
def record_metadata_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
    entity_type: Annotated[str, typer.Option("--entity-type")],
    entity_id: Annotated[str, typer.Option("--entity-id")],
    attributes: Annotated[Path, typer.Option("--attributes")],
    provenance: Annotated[Path, typer.Option("--provenance")],
    source: Annotated[str, typer.Option("--source")],
    confirmed_by: Annotated[str, typer.Option("--confirmed-by")],
    parent_revision_id: Annotated[str | None, typer.Option("--parent-revision-id")] = None,
) -> None:
    """Append user-approved, schema-validated metadata; no source row duplication."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.metadata_revisions import register_metadata_revision

    try:
        if any(not path.is_file() or path.is_symlink() for path in (attributes, provenance)):
            raise ValueError("Metadata input JSON files must be regular files")
        result = register_metadata_revision(
            project,
            pipeline_sha256,
            entity_type=entity_type,
            entity_id=entity_id,
            attributes=json.loads(attributes.read_text(encoding="utf-8")),
            field_provenance=json.loads(provenance.read_text(encoding="utf-8")),
            source=source,
            confirmed_by=confirmed_by,
            parent_revision_id=parent_revision_id,
        )
        emit_event("result", status="success", data=result)
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="show-metadata-snapshot")
def show_metadata_snapshot_command(
    project: Annotated[Path, typer.Option("--project")],
    pipeline_sha256: Annotated[str, typer.Option("--pipeline-sha256")],
) -> None:
    """Inspect current metadata pins without rewriting any historical RUN."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.metadata_revisions import metadata_snapshot

    try:
        emit_event(
            "result",
            status="success",
            data=metadata_snapshot(project, pipeline_sha256),
        )
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="show-dataset-metadata")
def show_dataset_metadata_command(
    project: Annotated[Path, typer.Option("--project")],
) -> None:
    """Read the current explicitly approved project-level dataset title."""
    from fairmorph_engine.core.project_metadata import show_dataset_metadata

    try:
        emit_event("result", status="success", data=show_dataset_metadata(project))
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="stage-dataset-metadata")
def stage_dataset_metadata_command(
    project: Annotated[Path, typer.Option("--project")],
) -> None:
    """Read project-local draft and register a new immutable, unapproved revision."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.project_metadata import stage_dataset_metadata

    try:
        emit_event("result", status="success", data=stage_dataset_metadata(project))
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
        emit_event("result", status="error", message=str(error))
        raise typer.Exit(code=1) from error


@app.command(name="approve-dataset-metadata")
def approve_dataset_metadata_command(
    project: Annotated[Path, typer.Option("--project")],
) -> None:
    """Read a distinct explicit approval file and commit its staged revision."""
    from jsonschema.exceptions import ValidationError

    from fairmorph_engine.core.project_metadata import approve_dataset_metadata

    try:
        emit_event("result", status="success", data=approve_dataset_metadata(project))
    except (ValueError, RuntimeError, OSError, KeyError, ValidationError) as error:
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
                "stage-csv-mapping",
                "approve-mapping",
                "run-mapping",
                "select-mapping",
                "run-pipeline",
                "register-pipeline",
                "select-pipeline",
                "confirm-projection",
                "assert-relation",
                "replace-relation",
                "retract-relation",
                "show-relations",
                "install-profile-contracts",
                "profile-bindings",
                "record-metadata",
                "show-metadata-snapshot",
                "export-package",
                "verify-project",
                "reconcile-runs",
                "show-dataset-metadata",
                "stage-dataset-metadata",
                "approve-dataset-metadata",
            ],
        },
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
