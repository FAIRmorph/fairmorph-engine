"""APPLY-ONLY review script. Not intended to be committed.

Copy the six new files, then apply exactly two source-code edits to PR #10.
Aborts if the expected current branch anchors do not match.
"""

from pathlib import Path

root = Path.cwd()


def replace_once(relative: str, old: str, new: str) -> None:
    target = root / relative
    before = target.read_text(encoding="utf-8")
    if before.count(old) != 1:
        raise RuntimeError(f"Unexpected branch content for {relative}: {old[:70]!r}")
    target.write_text(before.replace(old, new, 1), encoding="utf-8")


CLI_NEW_COMMANDS = '@app.command(name="stage-csv-mapping")\ndef stage_csv_mapping_command(\n    project: Annotated[Path, typer.Option("--project")],\n    resource_id: Annotated[str, typer.Option("--resource-id")],\n    profile: Annotated[Path, typer.Option("--profile")],\n) -> None:\n    """Register draft field semantics and mapping from an external JSON profile."""\n    from jsonschema.exceptions import ValidationError\n\n    from fairmorph_engine.core.profile import stage_csv_mapping\n\n    try:\n        draft = stage_csv_mapping(project, resource_id, profile)\n        emit_event("result", status="success", data=draft)\n    except (ValueError, OSError, KeyError, ValidationError) as error:\n        emit_event("result", status="error", message=str(error))\n        raise typer.Exit(code=1) from error\n\n\n@app.command(name="approve-mapping")\ndef approve_mapping_command(\n    project: Annotated[Path, typer.Option("--project")],\n    mapping_sha256: Annotated[str, typer.Option("--mapping-sha256")],\n    reviewer: Annotated[str, typer.Option("--reviewer")],\n) -> None:\n    """Explicitly approve all immutable field revisions and the staged mapping."""\n    from fairmorph_engine.core.profile import approve_staged_mapping\n\n    try:\n        approved = approve_staged_mapping(project, mapping_sha256, reviewer)\n        emit_event("result", status="success", data=approved)\n    except (ValueError, OSError, KeyError) as error:\n        emit_event("result", status="error", message=str(error))\n        raise typer.Exit(code=1) from error\n\n\n'
ACCEPTANCE_CHECK = '        # The engine does not encode scientific acceptance numbers: the exact\n        # expected values come from the reviewed, hash-pinned mapping profile.\n        acceptance = mapping.get("acceptance", {})\n        observed = {\n            "output_rows": len(rows),\n            "explicit_zeros": sum(row["value"] == 0 for row in rows),\n            "value_sum": sum(row["value"] for row in rows),\n        }\n        for metric, expected in acceptance.items():\n            if (\n                metric not in observed\n                or not isinstance(expected, int)\n                or isinstance(expected, bool)\n            ):\n                raise ValueError(f"Unsupported declared acceptance metric: {metric}")\n            if observed[metric] != expected:\n                raise ValueError(\n                    f"Mapping acceptance failed for {metric}: "\n                    f"expected {expected}, observed {observed[metric]}"\n                )\n'

replace_once(
    "src/fairmorph_engine/cli.py",
    '@app.command(name="run-mapping")\n',
    CLI_NEW_COMMANDS + '@app.command(name="run-mapping")\n',
)
replace_once(
    "src/fairmorph_engine/cli.py",
    '                "run-mapping",\n',
    '                "stage-csv-mapping",\n'
    '                "approve-mapping",\n'
    '                "run-mapping",\n',
)
replace_once(
    "src/fairmorph_engine/core/run_executor.py",
    '        output = staging / "outputs" / "observations.parquet"\n',
    ACCEPTANCE_CHECK + '        output = staging / "outputs" / "observations.parquet"\n',
)
print("Applied only reviewed CLI and executor acceptance changes.")
