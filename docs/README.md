# FAIRmorph Engine — Technical Project Documentation

**Documentation scope:** Full technical framework **v0.13** (v0.12 architecture retained plus PoC policy), under-1.0 **vertical PoC**. The Python package version remains `0.1.0`; framework and package versions are separate. The implementation baseline is PR #10 and the tested P0.1–P0.5 vertical slice; full v0.12 product compliance is **not** claimed.

FAIRmorph Engine is an **offline-first, dataset-independent data transformation and curation engine**. It preserves source bytes, records reviewed field semantics and versioned mappings, generates auditable RUN artifacts, and supports verified exports. It is neither a scientific data repository nor a system that infers scientific meaning from column names.

## Documentation index

| Document | Coverage |
| --- | --- |
| [v0.13 PoC development policy and v0.12 conformance gaps](FRAMEWORK-v0.13-POC-SCOPE.md) | Three binding rules, implemented scope, unresolved contracts and next milestones |
| [Chapter-by-chapter v0.12 coverage matrix](FRAMEWORK-v0.12-COVERAGE-MATRIX.md) | Mapping of framework chapters 01–15 to P0.1–P0.5 evidence and open gaps |
| [P0.2–P0.5 checkpoints](P0.5-CHECKPOINT.md) | Reviewed source semantics, sparse change audit, versioned relations and schema-pinned curated metadata |
| [Project-selected DAG/Entity RUN](project-driven-run.md) | Generic DAG pipeline, confirmed entity profiles and historical RUN snapshots |
| [User Guide](USER-GUIDE.md) | Input configuration, example CSV and mapping JSON, contracts, project structure, processing and verification |
| [Architecture and Concepts](ARCHITECTURE.md) | Components, storage, execution flow, immutable pins, RUN/2, security boundaries |
| [CLI and Python API Reference](API-REFERENCE.md) | Commands, signatures, parameters, return values and integration contracts |
| [Data Contracts and Publication](DATA-CONTRACTS.md) | JSON Schemas, mapping semantics, Parquet, Data Packages, EML and DwC-A |
| [Operations and Quality Assurance](OPERATIONS.md) | Installation, operations, testing, recovery and acceptance criteria |
| [PoC Acceptance Report](POC-ACCEPTANCE-REPORT.md) | Pinned CI baseline, expected/actual E2E evidence, fault-injection results and residual risks |
| [RUN Recovery](RUN-RECOVERY.md) | Interrupted publication, repair and fault-injection matrix |

Older stage notes remain as **historical progress snapshots**, not current status: [Foundation](FRAMEWORK-v0.12-FOUNDATION.md), [Generic RUN](FRAMEWORK-v0.12-GENERIC-RUN.md), [Old next step](FRAMEWORK-v0.12-NEXT-STEP.md), [Mapping Profile](FRAMEWORK-v0.12-MAPPING-PROFILE.md), [CS-PHOC reference](CS-PHOC-POC.md). Verify code, contracts and current CI rather than treating a frozen stage note as final authority.

## Quick start

Python **3.11+** and local write permissions are required. From the repository root:

```bash
python -m pip install -e ".[dev]"
fairmorph-engine --help
fairmorph-engine init-project --project ./demo.fairmorph --name "Demo"
fairmorph-engine import-resource --project ./demo.fairmorph --source ./measurements.csv --role measurements
```

The import returns a `resource_id` and SHA-256 digest. For the **CSV-profile mapping path**, an explicit external mapping profile and a named confirming user are required before execution:

```bash
fairmorph-engine stage-csv-mapping --project ./demo.fairmorph --resource-id RESOURCE_ID --profile ./mapping.json
fairmorph-engine approve-mapping --project ./demo.fairmorph --mapping-sha256 MAPPING_SHA256 --confirmed-by reviewer
fairmorph-engine run-mapping --project ./demo.fairmorph --mapping-sha256 MAPPING_SHA256
fairmorph-engine export-package --project ./demo.fairmorph --run-id RUN_ID
fairmorph-engine verify-project --project ./demo.fairmorph
```

Replace placeholders with returned IDs. This is a **distinct** CSV mapping workflow, not the generic Entity pipeline. For semantic Entity RUNs, local `install-profile-contracts` approval and complete exact `profile_bindings` are **mandatory**; see [Project-driven RUN](project-driven-run.md). CLI output is **NDJSON**; consume `result` events.

## Design principles

1. **No implicit scientific interpretation.** Field definitions, missing/zero semantics and publication bindings are explicit, reviewable inputs.
2. **Immutable source bytes.** Imported files are SHA-256-addressed and checked for integrity.
3. **Approval before execution.** Mappings and referenced field definitions require explicit review.
4. **Auditable evidence.** RUN manifests pin source data, configuration and output artifacts.
5. **Verification is separate from recovery.** Verification is read-only; reconciliation is an explicit maintenance operation.
6. **Dataset independence.** CS-PHOC is an optional external reference under `examples/cs-phoc/`, not a built-in engine default or required regular CI step.

## Maturity and limitations

This is a **vertical PoC**, not a production release. The verified P0.1–P0.5 code baseline is CI [42858754662](https://github.com/FAIRmorph/fairmorph-engine/actions/runs/42858754662), **129 tests passing each on Linux/Windows**, Ruff green. New documentation commits require their own final CI. Full v0.12 scientific acceptance, Workbench, expanded profiles and publication E2E are still open. SQLite and `project.json` do not share an atomic transaction. Cross-process locking, complete power-loss durability, backup/restore and a stable remote API have not been established as production guarantees. See [Operations](OPERATIONS.md).
\n## Forward-only PoC contract\n\nBefore framework documentation version **1.0**, there is **no required backward compatibility** with prior experimental project files, SQLite states, RUN artifacts or APIs. Evolve executable schemas, fixtures, code, tests and docs **together**; never silently overwrite immutable source objects or an already valid completed RUN. The PoC must fulfill **core** scientific and technical contracts but need not implement a fully differentiated product. [Authoritative v0.13 policy](FRAMEWORK-v0.13-POC-SCOPE.md).\n