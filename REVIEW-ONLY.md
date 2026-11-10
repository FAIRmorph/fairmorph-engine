# PR #10 – next increment: external CS-PHOC mapping profile

## Exact scope

Six **new** repository files, with their exact paths and SHA-256 bytes listed
in `MANIFEST.json`; only two **modified** existing files:

- `src/fairmorph_engine/cli.py`: add `stage-csv-mapping` and `approve-mapping`
  and advertise both commands in the NDJSON handshake.
- `src/fairmorph_engine/core/run_executor.py`: enforce generic, optional,
  explicitly declared `output_rows`, `explicit_zeros`, `value_sum` acceptance
  values *before* a RUN is published.

`apply-profile-step.py` is review/application material, **not a repository file**.
No scientific CSV, current RUN/1 contract, DwC-A code, or `main` files change.

## Repository and review

- Repository: `FAIRmorph/fairmorph-engine`
- Branch: `refactor/framework-v012-foundation`
- PR: #10, keep Draft, no merge
- Checked branch HEAD: `a7b7e6f27d9b8d8077a4f2f862f05e0ea8132140`
- Proposed commit: `feat: register external scientific mapping profiles`
- Do **not** push without user approval of this exact change scope.

## Test evidence

Local reconstructed test harness, Python 3.13:

- `pytest tests/test_profile_registry.py`: **11 passed**
- Combined `pytest tests/test_profile_registry.py tests/test_generic_run_executor.py`:
  **16 passed, 1 skipped**. The skipped test needs real Polars.
- Real imported CS-PHOC source: **16,940** long rows, **11,599** explicit zeros,
  and value sum **79,232**.
- Real CI on Python 3.11 Linux/Windows, Ruff, Parquet and the actual project
  catalog: **not yet executed for this proposed increment**.

## Remaining architecture work

The old `csphoc` command still runs the special-purpose path; events and
publication metadata are not yet frozen in the generic RUN snapshot; the DwC-A
export has not yet been converted to consume that completed generic RUN.
RUN/1 and RUN/2 contract consolidation must happen **with** this migration,
not as an unsafe partial change. There are no earlier scientific RUNs to migrate.

The profile's draft status is intentional. The responsible user must explicitly
confirm each mapping revision; the engine does not accept a bundled example as
implicit authorisation. No Workbench changes or publication action.
