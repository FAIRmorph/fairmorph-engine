"""FairMorph Engine - CLI Entrypoint."""

import hashlib
import json
import sys
from pathlib import Path

import typer

# 1. Das Subcommand aus dem commands-Paket importieren
from fairmorph_engine.commands.inspect_csv import inspect_csv
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
app.command(name="inspect-csv", help="Inspect a local CSV dataset")(inspect_csv)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
