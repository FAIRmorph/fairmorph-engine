# FAIRmorph Engine

**Local-first, headless biodiversity data curation and transformation engine.**

> **Development status:** Vertical **Proof of Concept** under the technical framework **v0.13** (full v0.12 foundation plus PoC policy); Python package version `0.1.0`. This is **not** a feature-complete, production-ready FAIRmorph product or a claim of full v0.12 conformance.

## Current functional vertical slice (P0.1–P0.5)

- **P0.1 – Project and DAG:** Import original CSV/Parquet bytes into an immutable SHA-256 object store; use a project-selected, version-pinned declarative Polars DAG to publish checksum-verified RUN/2 Parquet artifacts.
- **P0.2 – Scientific field semantics:** Versioned `SourceFieldDefinition` records and explicit responsible-user confirmation; project `SamplingEvent`, optionally `Occurrence` and `MeasurementOrFact`. Never infer taxonomic or counting semantics from a column name; numeric zero is not missing.
- **P0.3 – Sparse audit:** RUN rules and input/output cardinalities in `audit/pipeline.json`; `audit/value_changes.parquet` records **only actual directly comparable changed values**. Unmodified source cells are **not** duplicated into an exhaustive field-lineage table.
- **P0.4 – Relations:** Append-only typed relation assertions; `assert`, `replace`, `retract` with explicit user review and source references; four selected event/occurrence/measurement predicates with cardinality/cycle checks, a current view, and historical RUN pins.
- **P0.5 – Profiles and curated metadata:** Locally registered JSON Schema Draft 2020-12 profiles (eight schema drafts), mandatory **approved exact schema ID/version/hash pins** for semantic Entity pipelines; separately approved append-only metadata envelopes with historical RUN snapshots.

Both the `run-mapping` CSV-profile reference path and `run-pipeline` generic DAG path exist. They currently use **different audit and export artifacts**; this is a documented PoC boundary, not a promise of interchangeable packages. Example export/EML/DwC-A components exist but do not collectively establish a generally validated publication service.

## Quick start

Requires Python **3.11+**. Install locally:

```bash
python -m pip install -e ".[dev]"
fairmorph-engine --help
fairmorph-engine init-project --project ./survey.fairmorph
fairmorph-engine import-resource --project ./survey.fairmorph --source ./survey.csv --role survey
```

A technical import **does not** require an ecological profile. Before a **semantic entity pipeline**, declare/review source fields, then explicitly install approved schemas:

```bash
fairmorph-engine install-profile-contracts --project ./survey.fairmorph --confirmed-by researcher
fairmorph-engine profile-bindings --project ./survey.fairmorph --entities SamplingEvent,MeasurementOrFact
```

Place the returned exact pins under `profile_bindings` of the declarative pipeline, then use `register-pipeline` → `confirm-projection` → `select-pipeline` → `run-pipeline` → `verify-project`. The original `stage-csv-mapping` / `approve-mapping` / `run-mapping` command family remains a separate technical reference path. See [Project-driven RUN](docs/project-driven-run.md) and [User Guide](docs/USER-GUIDE.md).

## Implementation policy before framework version 1.0

1. **Vertical PoC only, not an entire product.** Implement a small authentic end-to-end scientific path, not every production feature.
2. **Core contracts are mandatory, breadth and operational hardening are not yet fully differentiated.** Preserve immutable source identity, explicit field/semantic confirmation, deterministic declaration and source/result pins, entity/relation validity, scientific zero/missing distinction and reproducible RUN evidence. Keep incomplete capabilities visibly deferred.
3. **No backward-compatibility obligation for experimental PoC artifacts before v1.0.** Iterate **forward consistently**: change code, contracts, tests, examples and docs together. Do not silently rewrite immutable source bytes or completed valid RUN evidence.

See [Technical Framework v0.13 – PoC rules and gap analysis](docs/FRAMEWORK-v0.13-POC-SCOPE.md). For the full original framework, use the complete v0.13 source bundle accompanying the technical documentation.

## Verification and next milestones

Last verified code baseline before these documentation edits: [GitHub CI run #307](https://github.com/FAIRmorph/fairmorph-engine/actions/runs/42858754662), commit `c8480ba36bbac55245cce69fd94db58c1adafcbe`, **129 passing tests on Linux and Windows**, with Ruff lint and format checks. Subsequent edits require their own CI results.

- **P0.6 next:** Workbench user journey – source-field semantics, profile choice, preview, findings, explicit mapping review and relation/metadata revision UI.
- **P0.7:** generalized, independently validated EML, Darwin Core Archive and GeoPackage publication profiles.
- **P0.8:** real CS-PHOC plus independent second-dataset regression, key/join/provenance and resource tests.

Production backups/recovery, multiuser locking, migration infrastructure, security/signatures, complete IPC and scalable packaging are later work, **not already delivered**.

## Documentation

Start with [Documentation Index](docs/README.md), [Architecture](docs/ARCHITECTURE.md), [Contracts](docs/DATA-CONTRACTS.md), [P0.5 checkpoint](docs/P0.5-CHECKPOINT.md), and [PoC acceptance evidence](docs/POC-ACCEPTANCE-REPORT.md).

**Scientific caution:** Structural schema validity, a checksum, and an explicitly accepted mapping do not themselves establish scientific correctness or permission to publish data.
