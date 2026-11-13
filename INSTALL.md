# Installation

FAIRmorph Engine is a **Python package and command-line application**. It does not require Node.js, Rust, Tauri, Svelte or the FAIRmorph Workbench to run. Those technologies belong to the separate optional Workbench repository.

## Requirements

- Python **3.11+** and `pip`
- Git, when cloning the source repository or reproducing pinned external datasets
- A writable directory for local FAIRmorph projects
- An internet connection to fetch dependencies initially; subsequent project processing is local

Linux, macOS and Windows are supported as development platforms. This is a pre-1.0 proof of concept: package/build compatibility and production deployment guarantees are limited.

## Installation from source

```bash
git clone https://github.com/FAIRmorph/fairmorph-engine.git
cd fairmorph-engine
python -m venv .venv
```

Activate the virtual environment:

- **Linux/macOS (Bash):** `source .venv/bin/activate`
- **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`

Then install the package:

```bash
python -m pip install -e ".[dev]"
fairmorph-engine --help
fairmorph-engine handshake
```

Use `python -m pip install -e .` if you do not need development/testing dependencies. If a console script is not on your PATH, confirm that you activated the environment and installed the package in that same Python interpreter.

## Verify the installation

```bash
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
```

The ordinary pytest suite is configured under `tests/`. Additional reference examples can have their own test procedures. Passing tests verifies technical behavior, **not scientific approval of an external dataset**.

## Next: run a complete example

Continue with the [worked CSV-to-RUN user guide](docs/USER-GUIDE.md). It supplies a small synthetic CSV, expected count values, explicit mapping declarations, separate approval, a verified RUN and Data Package export. Keeping the worked example in one guide avoids conflicting copies of commands or test data.

If you want only to initialize a project before proceeding, use:

```bash
fairmorph-engine init-project --project ./survey.fairmorph --name "Example Survey"
```

The Engine will create a **new** project directory; do not reuse an existing path. Importing a file or creating a project does not mean its scientific contents have been reviewed. For project lifecycle and safe recovery, see [operations](docs/OPERATIONS.md).

## Separate Workbench

The desktop user interface is developed in [fairmorph-workbench](https://github.com/FAIRmorph/fairmorph-workbench). Install it using **that repository's** instructions; it is not bundled by this Engine installation guide, and its feature coverage is not identical to the Engine CLI.
