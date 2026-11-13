# Operations and verification

This document describes **current operational procedures** for the local Python Engine proof of concept, not an approval checklist tied to historical development branches. The system is **not** a production multiuser data service.

## Install, inspect and test

Requires Python **3.11+**. Use [installation instructions](../INSTALL.md) to create a virtual environment and install the Engine.

```bash
fairmorph-engine --help
fairmorph-engine handshake
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
```

The standard pytest suite is configured under `tests/`. The [repository's current GitHub Actions](https://github.com/FAIRmorph/fairmorph-engine/actions) is the evidence for recent revisions; **do not assume historical test counts apply to the current main branch**. Standalone reference-example tests may have separate workflows.

## Normal project lifecycle

1. **Create a project:** `init-project --project PATH`. Select a new path; existing source/project state should not be overwritten.
2. **Import original files:** `import-resource --project PATH --source FILE --role ROLE`. Record the real `resource_id` and SHA-256; technical import does not imply semantic approval.
3. **Declare and review a mapping or pipeline:** choose either the explicit reviewed CSV mapping path or the generic DAG path. Follow [user guide](USER-GUIDE.md) or [project-driven RUN](project-driven-run.md).
4. **Execute:** `run-mapping` or `run-pipeline`, using actual approved/current revision identities where required. Capture the new `run_id`.
5. **Verify:** `verify-project --project PATH`. Check the returned result and the immutable `runs/<run-id>/manifest.json`.
6. **Export if appropriate:** `export-package` creates a Data Package from the eligible verified reference RUN. Publication-specific adapters require their own complete, validated plans and metadata.

Handled CLI operations emit a newline-delimited JSON `result` with `status: "success"` or `status: "error"`; errors return a nonzero exit code. Machine-generated IDs vary across projects, so use returned values rather than copying examples.

## Technical verification vs. scientific approval

**A verified RUN** means configured object, manifest, artifact and reference integrity checks passed. **It does not mean** source authors reviewed AI-added descriptions, ecological interpretation is correct, the user approved field semantics, or the output is publication-ready.

Formal field review binds the decision to a particular immutable SourceFieldDefinition revision and identifiable reviewer. Entity projection approvals require actual approved definition/profile pins. An incomplete or unreviewed declaration can still be stored as a draft without being scientifically usable.

## Interrupted RUNs and safe recovery

Never manually rewrite completed RUN manifests or imported source objects. When no project writer is active, use:

```bash
fairmorph-engine reconcile-runs --project PATH
fairmorph-engine verify-project --project PATH
```

Reconciliation checks completed RUN directories and can repair missing catalog references; it does **not** automatically promote unfinished `.pending-*` directories or guarantee atomic recovery across filesystem and SQLite. Preserve failed staging directories for diagnosis. For details, consult [RUN recovery](RUN-RECOVERY.md).

### Known operational limits

- No production-grade cross-process lock, multiwriter transaction model, or guaranteed fsync-level power-loss durability.
- No stable pre-1.0 migration compatibility contract for arbitrary older PoC project directories.
- Not every media, geographic, domain Entity type or publication workflow is implemented.
- Sparse changed-value audits are **not** exhaustive lineage tables for every unchanged cell.
- Verification checks are not a substitute for a scientist's review or publishing authority.

## Reproduce independent real-data checks

For the original public CS-PHOC research dataset, use the separate [fairmorph-validations reproduction guide](https://github.com/FAIRmorph/fairmorph-validations/blob/main/docs/CS-PHOC-REPRODUCTION-AND-RESULTS.md).

That external test pins the Engine version, imports original source bytes, verifies a generic RUN/2, registers **unreviewed** source-field drafts, and independently audits **dataset-specific** DwC-A, PANGAEA-preparation TSV and GeoJSON test files. Its test exporter is **outside** Engine core. The Workbench was not exercised. This is evidence of a bounded real-data technical test, not generic publication or biological approval.

For source and package contracts see [data contracts](DATA-CONTRACTS.md), and for what v0.13 promises see [framework scope](FRAMEWORK-v0.13-POC-SCOPE.md).
