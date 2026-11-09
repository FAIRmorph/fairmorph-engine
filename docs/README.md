# FAIRmorph Engine — Technical Project Documentation

**Documentation scope:** Framework v0.12 development branch `refactor/framework-v012-foundation` (Draft PR #10). The Python package version is currently `0.1.0` in `pyproject.toml`; “v0.12” describes the framework development milestone, **not** a released package version.

FAIRmorph Engine is an **offline-first, dataset-independent data transformation and curation engine**. It preserves source bytes, records reviewed field semantics and versioned mappings, generates auditable RUN artifacts, and supports verified exports. It is neither a scientific data repository nor a system that infers scientific meaning from column names.

## Documentation index

| Document | Coverage |
| --- | --- |
| [User Guide](USER-GUIDE.md) | Input configuration, example CSV and mapping JSON, contracts, project structure, processing and verification |
| [Architecture and Concepts](ARCHITECTURE.md) | Components, storage, execution flow, immutable pins, RUN/2, security boundaries |
| [CLI and Python API Reference](API-REFERENCE.md) | Commands, signatures, parameters, return values and integration contracts |
| [Data Contracts and Publication](DATA-CONTRACTS.md) | JSON Schemas, mapping semantics, Parquet, Data Packages, EML and DwC-A |
| [Operations and Quality Assurance](OPERATIONS.md) | Installation, operations, testing, recovery and acceptance criteria |
| [RUN Recovery](RUN-RECOVERY.md) | Interrupted publication, repair and fault-injection matrix |

Additional technical notes: [Foundation](FRAMEWORK-v0.12-FOUNDATION.md), [Generic RUN](FRAMEWORK-v0.12-GENERIC-RUN.md), [Mapping Profile](FRAMEWORK-v0.12-MAPPING-PROFILE.md), [CS-PHOC reference](CS-PHOC-POC.md). The source code on this branch is authoritative if documentation differs from implementation.

## Quick start

Python **3.11+** and local write permissions are required. From the repository root:

```bash
python -m pip install -e ".[dev]"
fairmorph-engine --help
fairmorph-engine init-project --project ./demo.fairmorph --name "Demo"
fairmorph-engine import-resource --project ./demo.fairmorph --source ./measurements.csv --role measurements
```

The import returns a `resource_id` and SHA-256 digest. An **explicit external mapping profile** and a named reviewer are required before execution:

```bash
fairmorph-engine stage-csv-mapping --project ./demo.fairmorph --resource-id RESOURCE_ID --profile ./mapping.json
fairmorph-engine approve-mapping --project ./demo.fairmorph --mapping-sha256 MAPPING_SHA256 --reviewer reviewer
fairmorph-engine run-mapping --project ./demo.fairmorph --mapping-sha256 MAPPING_SHA256
fairmorph-engine export-package --project ./demo.fairmorph --run-id RUN_ID
fairmorph-engine verify-project --project ./demo.fairmorph
```

Replace placeholders with IDs returned by previous commands. The profile must conform to its versioned JSON Schema. CLI output is **NDJSON**; consumers should parse `result` events instead of guessing IDs from filenames. See the [User Guide](USER-GUIDE.md) for a complete configuration example.

## Design principles

1. **No implicit scientific interpretation.** Field definitions, missing/zero semantics and publication bindings are explicit, reviewable inputs.
2. **Immutable source bytes.** Imported files are SHA-256-addressed and checked for integrity.
3. **Approval before execution.** Mappings and referenced field definitions require explicit review.
4. **Auditable evidence.** RUN manifests pin source data, configuration and output artifacts.
5. **Verification is separate from recovery.** Verification is read-only; reconciliation is an explicit maintenance operation.
6. **Dataset independence.** CS-PHOC is an optional external reference under `examples/cs-phoc/`, not a built-in engine default or required regular CI step.

## Maturity and limitations

This is a **PoC/Draft branch**. Formal PoC acceptance requires green CI and a documented end-to-end acceptance record. SQLite and `project.json` do not share an atomic transaction. Cross-process locking, complete power-loss durability, backup/restore and a stable remote API have not been established as production guarantees. See [Operations](OPERATIONS.md).
