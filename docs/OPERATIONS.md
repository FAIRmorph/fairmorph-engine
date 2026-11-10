# Operations, Testing, Error Handling and PoC Acceptance (Framework v0.13)

## 1. Installation and checks

```bash
python -m pip install -e ".[dev]"
ruff check src tests
ruff format --check src tests
pytest --cov=fairmorph_engine --cov-report=xml
```

Python 3.11+ is required. Standard pytest discovery is configured in `pyproject.toml` with `testpaths = ["tests"]`. The ordinary CI matrix covers Ubuntu and Windows. CS-PHOC reference tests under `examples/cs-phoc/tests/` are not automatically part of that regular suite.

## 2. Operating sequence — reference CSV mapping path

1. **Initialize:** `init-project` creates an empty project without scientific interpretation.
2. **Import:** `import-resource` stores original SHA-256-addressed bytes and returns `resource_id`.
3. **Stage:** `stage-csv-mapping` validates external field definitions, policies and relationships.
4. **Approve:** `approve-mapping` records reviewer identity and the mapping hash.
5. **Execute:** `run-mapping` generates RUN/2 with Parquet, lineage and quality metrics.
6. **Verify:** `verify-project` checks indexed project/RUN/export consistency.
7. **Export:** `export-package` creates a generic Data Package from a verified RUN.
8. **Optional publication:** validate external publication declarations and call EML/DwC-A Python adapters.

The CLI writes NDJSON. Automation should parse `event = result` and `status = success`, not infer success from directory existence.

## 2a. Generic semantic Entity RUN (P0.1–P0.5)\n\nThe distinct generic DAG path is `register-pipeline` → `confirm-projection` → `select-pipeline` → `run-pipeline` → `verify-project`. Entity pipelines require **explicitly approved** local schema pins: install once with `install-profile-contracts --confirmed-by USER`, use `profile-bindings --entities SamplingEvent,MeasurementOrFact`, then include the returned `profile_bindings` in the registered DAG config. Optionally register `assert-relation`, `replace-relation`, `retract-relation`, and `record-metadata` decisions. Generic RUNs write named Parquet outputs, a DAG/row-count audit and optional sparse changed-values evidence; they **do not** write the CSV reference lineage file. The technical input import needs no domain profile.\n\n## 3. Interrupted RUN publication

Execution starts in `runs/.pending-<run_id>/`, then publishes to `runs/<run_id>/` and updates `project.json` and SQLite. Process interruption may leave a complete directory missing from one or both indexes.

**Recovery procedure:** stop all writers, back up the project, execute `reconcile-runs --project PATH`, then run `verify-project --project PATH`. Reconciliation verifies completed RUN directories and restores missing index entries. It does not delete missing references or automatically promote `.pending-*` directories. Failed staging directories remain available for investigation.

**Limitations:** no cross-process lock, no guaranteed fsync-level power-loss durability and no atomic transaction across filesystem and SQLite. See [RUN Recovery](RUN-RECOVERY.md).

## 4. Test coverage

| Test module/family | Coverage |
| --- | --- |
| `test_framework_foundation.py` | Project initialization, imports and infrastructure |
| `test_profile_registry.py`, `test_registry_mapping.py` | Field definitions, reviews and mapping states |
| `test_relationship_integrity.py`, `test_relationship_preflight_malformed.py` | CSV relationships, cardinality and malformed rows |
| `test_tabular_primitive.py`, `test_typed_tabular_poc.py` | Count and typed transformations |
| `test_generic_run_executor.py` | RUN/2, approval, verification and failure handling |
| `test_run_publication_fault_injection.py` | Injected RUN publication/recovery failures |
| `test_independent_survey_e2e.py`, `test_cli_external_profile_e2e.py` | Dataset-independent synthetic end-to-end flows |
| `test_publication_*.py`, `test_official_eml_schema.py` | Publication contracts, integrity and EML/DwC-A |
| `test_schema_registry.py` | Immutable local schema versions |\n| `test_entity_projection_run.py`, `test_pipeline_change_audit.py` | P0.2 entity projections and P0.3 sparse changed-value auditing |\n| `test_relation_assertions_run.py`, `test_domain_profile_metadata.py` | P0.4 versioned relations, P0.5 mandatory schemas, curated metadata, historical RUN snapshot |

**Recovery acceptance criteria:** failed directory publication creates no completed RUN; ordinary index-write errors roll back; simulated crashes after directory publication can be reconciled; corrupt RUNs are rejected; reconciliation is idempotent; tests pass on both Ubuntu and Windows.

**Important:** Test presence does not establish test success. PoC acceptance requires successful CI for a named commit and a recorded end-to-end acceptance result with expected/actual values and known limitations. The P0.1–P0.5 technical/synthetic CI was last verified for code commit `c8480ba36bbac55245cce69fd94db58c1adafcbe` at [run #307](https://github.com/FAIRmorph/fairmorph-engine/actions/runs/42858754662), **129 tests each on Linux/Windows**, Ruff green. This is **not** a scientific real-data acceptance or product-readiness certification. The updated documentation commit has a separate CI result.

## 5. Troubleshooting

- **Mapping not approved:** inspect mapping hash and review status; never approve implicitly.
- **Modified source:** compare bytes with import SHA-256; do not edit checksums to suppress an error.
- **Malformed CSV or relationship:** correct rows, keys or declared cardinality and restage.
- **Corrupt RUN artifact:** do not export or mark it completed; investigate checksum mismatch.
- **Index mismatch after interruption:** stop writers, back up, then reconcile explicitly.
- **Pending staging directory:** retain diagnostics; investigate before manual cleanup.
- **EML/DwC-A validation failure:** check external metadata, projection, integrity rules and local XSDs.

## 6. Non-production guarantees

Cross-process locking, atomic multi-store publication, power-loss durability, systematic backup/restore, stable public Python/remote APIs, automatic project migration and scientific validation across arbitrary domains are **not** claimed as implemented production guarantees. The CS-PHOC reference is an optional manually triggered regression.

## 7. Acceptance evidence

A final acceptance report should record Git commit SHA, OS/Python versions, Ruff and pytest outcomes, synthetic E2E results, mapping/RUN/export hashes, fault-injection matrix, known limitations and an explicit approval decision. Until those checks pass, PoC acceptance remains open.
\n## 8. v0.13 development policy\n\nBefore framework documentation version **1.0**, deliver a **vertical PoC** only, while actually satisfying the selected core contracts. Fully differentiated validation breadth, UI, migration, security and production operations remain explicitly deferred. **Do not build backward compatibility for earlier experimental PoC states**: evolve schema versions, code, fixtures, tests and docs forward together. Do not silently mutate immutable source data or validated completed RUN evidence. See [v0.13 policy](FRAMEWORK-v0.13-POC-SCOPE.md).\n