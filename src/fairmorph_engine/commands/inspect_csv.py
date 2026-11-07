"""Inspect a local CSV dataset and report its structure over NDJSON."""

import csv
import json
from pathlib import Path

import typer


def inspect_csv(
    source: Path = typer.Argument(..., help="Path to a UTF-8 CSV file"),
    output: Path | None = typer.Option(None, "--output", help="Optional summary JSON output"),
) -> None:
    """Read a local CSV incrementally without modifying the source file."""
    from fairmorph_engine.cli import compute_sha256, emit_event

    try:
        if not source.is_file():
            raise ValueError(f"CSV file does not exist: {source}")

        emit_event("progress", stage="READING", percentage=10, message=f"Reading {source.name}")
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            columns = next(reader, None)
            if columns is None or not columns or any(not name.strip() for name in columns):
                raise ValueError("CSV must have non-empty column names")
            if len(set(columns)) != len(columns):
                raise ValueError("CSV column names must be unique")

            records = 0
            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(columns):
                    raise ValueError(
                        f"CSV row {line_number} has {len(row)} fields; expected {len(columns)}"
                    )
                records += 1

        emit_event("progress", stage="HASHING", percentage=85, message="Hashing source file")
        summary = {
            "source_file": str(source.resolve()),
            "columns": columns,
            "processed_records": records,
            "dataset_sha256": compute_sha256(source),
        }

        if output is not None:
            destination = output.resolve()
            if destination == source.resolve():
                raise ValueError("Summary output must differ from source CSV")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            summary["output_file"] = str(destination)

        emit_event("result", status="success", data=summary)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        emit_event("result", status="error", message=str(exc))
        raise typer.Exit(code=1) from exc
