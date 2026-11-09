# Framework v0.12 – generic RUN executor (integration increment)

This implementation supplies a dataset-neutral **wide-to-long count** executor
that consumes a project-local, explicitly reviewed mapping and field-definition
revisions. It never accesses bundled scientific example data and never infers
counting units, category meaning, missing-value or zero semantics.

The executor pins the source object's exact SHA-256, the approved mapping, all
relevant field-definition revisions and the field-definition schema. It writes
an immutable input and configuration snapshot, Parquet observations, Parquet
lineage, a quality report and a checksummed RUN manifest. Failed operations
retain staging diagnostics instead of publishing a completed RUN.

## Migration policy

**There are no previously created CS-PHOC RUNs to migrate.** The old PoC `/1`
manifest shape is not a compatibility requirement. This increment stages
`/2` contracts alongside `/1` **only until the CS-PHOC-specific execution path
is converted**. This is not the intended final dual-contract architecture.
In the subsequent integration, promote `/2` to the sole `run.schema.json` and
`inputs.snapshot.schema.json` contract, update the CS-PHOC example to execute
through approved field definitions and mappings, then delete the `/1` contract
and temporary `*-v2` filenames. Do not merge the increment as complete v0.12
architecture before that migration.

## Scope and constraints

- The supported operation is `wide-to-long-counts/1` with exactly one imported
  resource. A second source, a join or a different operation requires a reviewed
  executor capability, not an implicit fallback.
- Exactly approved `csv:<column>` field definitions must belong to that source.
  `counting_unit=individual` and explicit zero/missing policies are enforced.
- SQLite and `project.json` are separate mutable indexes and do not share an
  ACID transaction. Ordinary failures are rolled back; abrupt termination needs
  a manifest-based recovery/reconciliation flow before production deployment.
- The staged project is a test harness in local development; do not copy its
  `core/project.py` into the repository. Use PR #10's real project module.
- Real Parquet integration must be confirmed on CI with Polars installed. Tests
  with a fake Parquet writer verify publication/integrity control flow only.
- Author-defined CS-PHOC DwC-A semantics and Frictionless mapping/export
  materialization are not yet migrated onto this generic executor.

## Local checks and CI gate

Run `ruff check src tests`, `ruff format --check src tests` and
`pytest tests/test_generic_run_executor.py` in the *real* PR #10 checkout.
Then run the full Linux/Windows matrix; confirm no regression of the authors'
CS-PHOC Event/Occurrence fingerprints and source checksums. PR #10 stays Draft.
