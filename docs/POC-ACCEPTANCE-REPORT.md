# FAIRmorph Engine v0.12 — Technical PoC Acceptance Record

**Evidence status:** Automated CI and synthetic end-to-end acceptance criteria **PASSED** for the pinned code baseline below. **Governance status:** Formal human approval / merge **NOT GRANTED**. This record is a test-evidence document, not a release authorization.

## 1. Immutable test baseline and traceability

| Item | Recorded value |
| --- | --- |
| Repository | `FAIRmorph/fairmorph-engine` |
| Pull request | [PR #10](https://github.com/FAIRmorph/fairmorph-engine/pull/10), Draft |
| Development branch | `refactor/framework-v012-foundation` |
| **Code baseline (tested SHA)** | **`afce838ba236ab27fab9441c8dfd94dde6cc5641`** |
| CI evidence | [GitHub Actions run #42722783074](https://github.com/FAIRmorph/fairmorph-engine/actions/runs/42722783074) |
| Workflow result | **completed / success** |
| Ubuntu | `ubuntu-latest`, Python **3.11.18**, **94 passed** in **8.08 s** |
| Windows | `windows-latest`, Python **3.11.9**, **94 passed** in **35.58 s** |
| Test collection | Standard `tests/` suite; CS-PHOC reference workflow not required |
| Evidence source | CI job logs, source tests and versioned project contracts at the tested SHA |

**Baseline rule:** This SHA identifies the exact code revision that passed. Adding this document to the branch creates a **different documentation commit** and does not retroactively make the new SHA the tested baseline. Any subsequent code changes require a fresh CI result before claiming that the changed revision passed.

## 2. Scope and method

The tests use synthetic, dataset-independent CSV inputs and exercise the public Typer CLI through `CliRunner`, as well as lower-level Python APIs where necessary. They verify the generic engine without installing CS-PHOC-specific scientific fixtures. The normal GitHub Actions jobs also run Ruff checks and formatting before pytest; both jobs concluded successfully.

The following table distinguishes **expected assertions** in the source tests from **observed CI evidence**. The job logs report individual test cases as `PASSED`, but they do not publish a separate artifact containing the entire generated temporary project or its individual RUN/manifest hashes. Therefore, these are **automated E2E acceptance results**, not an independently archived production-data validation.

## 3. Generic end-to-end acceptance — expected versus actual

### 3.1 Independent survey: full public-CLI lifecycle

**Test:** `tests/test_independent_survey_e2e.py::test_independent_survey_full_lifecycle`

Synthetic input:

```csv
sample,small,large
S1,0,4
S2,,7
```

The test performs: `init-project` → `import-resource` → `stage-csv-mapping` → `approve-mapping` → `run-mapping` → `export-package` → `verify-project`.

| Acceptance criterion | Expected | Actual evidence |
| --- | --- | --- |
| CLI stages and approves an external count mapping | All commands exit successfully and return success events | **PASS** — test passed on both platforms |
| RUN schema version | `fairmorph.poc.run/2` | **PASS** — asserted in test |
| Normalized observation rows | **3** | **PASS** — asserted Parquet row count |
| Sorted observation values | **[0, 4, 7]** | **PASS** — asserted Parquet values |
| Lineage rows | **3** | **PASS** — asserted Parquet row count |
| Data Package descriptor | `datapackage.json` exists | **PASS** — asserted |
| Completed RUNs after project verification | **1** | **PASS** — asserted |

**Interpretation:** The missing `small` cell is omitted while explicit zero is retained. The resulting three observations are traced and exported.

### 3.2 External profile, auxiliary relationship and generic Data Package

**Test:** `tests/test_cli_external_profile_e2e.py::test_external_profile_cli_review_and_run`, parameterized for `counting_unit = individual` and `sampling_event`.

Synthetic source:

```csv
station,juveniles,adults
A,0,2
B,,3
```

Auxiliary source:

```csv
station,region
A,north
B,south
```

| Acceptance criterion | Expected | Actual evidence |
| --- | --- | --- |
| Mapping after staging | `draft` | **PASS** — asserted |
| Mapping after reviewer approval | `approved` | **PASS** — asserted |
| Output observation rows | **3** | **PASS** — asserted |
| Explicit zeros | **1** (mapping acceptance expectation) | **PASS** — RUN succeeded under acceptance gate |
| Value sum | **5** (mapping acceptance expectation) | **PASS** — RUN succeeded under acceptance gate |
| Source pins in input snapshot | **2** | **PASS** — asserted |
| Relationship in snapshot | `survey-station` | **PASS** — asserted |
| Data Package resource paths | `observations.csv`, `lineage.csv`, `quality.json` | **PASS** — asserted |
| Exported CSV observation rows | **3** | **PASS** — asserted |
| Sorted exported values | **[0, 2, 3]** | **PASS** — asserted |
| Completed RUNs after verification | **1** | **PASS** — asserted |
| No dataset-specific package title | `CS-PHOC` absent | **PASS** — asserted |

Both counting-unit parameterizations passed in CI. The relationship is preflight-validated and pinned, **not** silently applied as a join.

### 3.3 Publication integrity and deterministic materialization

**Test:** `tests/test_cli_external_profile_e2e.py::test_generic_publication_integrity_against_real_verified_run`

| Acceptance criterion | Expected | Actual evidence |
| --- | --- | --- |
| Integrity verification | `integrity_verified = true` | **PASS** |
| No automatic publication authorization | `publication_ready = false` | **PASS** |
| Materialized table rows | **3** | **PASS** |
| Projected DwC column | `occurrenceID` | **PASS** |
| Determinism across two destinations | Equal results and identical CSV bytes | **PASS** |

This test uses a real verified synthetic RUN, not a mocked RUN verification result. It does **not** establish that arbitrary publication metadata is scientifically valid or that an external repository accepted the archive.

## 4. RUN/2 fault-injection and recovery acceptance

**Test module:** `tests/test_run_publication_fault_injection.py`

| Test case / injected boundary | Required behavior | Ubuntu | Windows |
| --- | --- | --- | --- |
| `publish_directory` | Failed staging-to-final rename leaves no completed RUN/index entries; pending failure evidence retained | PASS | PASS |
| `publish_index` | Failed project-index replacement rolls back SQLite and RUN publication | PASS | PASS |
| `directory_only` | Recovery reconstructs both missing indexes from a valid published RUN | PASS | PASS |
| `index_only` | Recovery restores the missing catalog entry | PASS | PASS |
| `catalog_only` | Recovery restores the missing JSON index entry | PASS | PASS |
| `recovery_index_replace_failure` | Recovery index I/O error rolls back catalog changes; retry succeeds | PASS | PASS |
| `missing_indexed_run` | Invalid completed RUN is rejected without deleting catalog/index references | PASS | PASS |

**Idempotency:** The three index-reconciliation test cases also assert that a second reconciliation returns no newly recovered RUNs. The fault-injection suite simulates deterministic exceptions and persisted-state interruptions; it is **not a physical power-loss test**.

Further coverage in `test_generic_run_executor.py` rejects unapproved mappings, modified source objects, undeclared mapping columns, and corrupted RUN artifacts. These tests also passed within the 94-test suite.

## 5. CI quality gates

| Gate | Ubuntu | Windows | Evidence |
| --- | --- | --- | --- |
| Ruff lint / import sorting | PASS | PASS | Successful workflow jobs |
| Ruff format check | PASS | PASS | Successful workflow jobs |
| Pytest suite | **94 passed** | **94 passed** | Job log summaries |
| Coverage report generation | `coverage.xml` written | `coverage.xml` written | Job log summaries |
| Minimum coverage percentage | **Not established** | **Not established** | No percentage/threshold is asserted in this record |
| Optional CS-PHOC reference regression | **Not part of this run** | **Not part of this run** | Manually triggered separate workflow |

## 6. Known limitations and residual risks

1. **No cross-process writer lock:** concurrent imports, RUN publication, export or recovery are not proven safe. Run recovery only after stopping all writers.
2. **No atomic transaction across filesystem, `project.json` and SQLite:** recovery reconciles verified completed directories but cannot guarantee uninterrupted atomic visibility to concurrent readers.
3. **No fsync-level or power-loss durability guarantee:** the simulated crash tests do not reproduce storage-controller or physical machine failure.
4. **No automatically promoted pending RUNs:** `.pending-*` entries remain for forensic review; invalid completed RUNs fail closed.
5. **No stable public remote API or general project migration contract:** the Python API and v0.12 milestone remain Draft.
6. **No implicit scientific semantics or publication approval:** field definitions, counting units, missing/zero policies and Darwin Core bindings require explicit review.
7. **No optional CS-PHOC regression evidence in this CI run:** the project-specific workflow remains separate and manual.
8. **No archived, independently reproduced deployment E2E:** acceptance values above are verified by automated assertions in CI, not by a separate operator-run validation with signed artifact manifests.
9. **No independently documented minimum coverage threshold:** generation of `coverage.xml` is confirmed; a numeric percentage is not claimed.

## 7. Acceptance decision and next gate

**Automated generic PoC test gate: PASS** for baseline `afce838ba236ab27fab9441c8dfd94dde6cc5641` on Ubuntu and Windows, including public-CLI E2E and RUN publication/recovery fault injection.

**Formal human PoC sign-off: PENDING.** This document supplies the technical evidence for review but does not approve deployment, remove the Draft designation or authorize merging PR #10. Formal sign-off should explicitly accept the limitations above and, if required by project governance, request an independent operator-run E2E with archived artifacts.

**No merge, release or PR-ready transition is performed by creating this record.**

## 8. Reproduction

From a clean checkout of the **pinned baseline SHA**:

```bash
python -m pip install -e ".[dev]"
ruff check src tests
ruff format --check src tests
pytest --cov=fairmorph_engine --cov-report=xml
```

For focused E2E and recovery regression:

```bash
pytest -q tests/test_independent_survey_e2e.py tests/test_cli_external_profile_e2e.py tests/test_run_publication_fault_injection.py
```

See [User Guide](USER-GUIDE.md), [Architecture](ARCHITECTURE.md), [API Reference](API-REFERENCE.md), [Data Contracts](DATA-CONTRACTS.md), [Operations](OPERATIONS.md), and [RUN Recovery](RUN-RECOVERY.md).
