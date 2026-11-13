# Architecture

**Status:** Engine vertical proof of concept, Python package `0.1.0`. Core technical capabilities are tested with synthetic data; the separately pinned CS-PHOC case provides additional, bounded real-data validation. This is not a complete product. [Binding pre-1.0 rules](SCOPE-AND-DEVELOPMENT.md).

## 1. System boundary and trust model

The headless Python Engine provides a Typer CLI (NDJSON result/progress events), project/source registry, declarative Polars processing, versioned field/schema decisions, materialized Parquet RUNs and discrete publication adapter prototypes. No persistent production Workbench IPC protocol, remotely accessible service or automatic scientific interpretation is claimed.

```text
Unchanged CSV / Parquet input files
              |
         Import + SHA-256 object store       (no semantic profile required)
              |
       Project catalog and versioned decisions (SQLite)
              |  SourceFieldDefinition + explicit user review
              |  local domain profile ID / version / hash
              |  append-only relation assertions & curated metadata
              |
       Version-pinned allowlisted Polars DAG
              |
        Project-selected RUN/2 (immutable published artifacts)
         |            |               |
   Named Parquet  Rule/count audit   Input/config/decision snapshots
   outputs        + sparse changes   + checksummed manifest
              |
      Verification/reconstruction
              |
      Independent target-specific export prototypes
```

A separate **CSV external-profile path** (`stage-csv-mapping` / `approve-mapping` / `run-mapping`) remains for reference/CS-PHOC workflows. It emits `outputs/observations.parquet` and `audit/lineage.parquet`; its export adapter expects these specific artifacts. The generic DAG path emits named tables (and approved entity projections), `audit/pipeline.json`, and optional `audit/value_changes.parquet`; it does **not** automatically produce the CSV-profile lineage artifact. These paths must be reconciled **forward** in future work.

## 2. Responsibilities

| Component | Responsibility |
| --- | --- |
| `core.project`, `core.project_execution` | Initialize/select a project; SHA-256 import identities; select a reviewed mapping or pinned pipeline |
| `core.registry`, `core.entity_projection` | Append-only SourceFieldDefinition revisions, user confirmations, explicit SamplingEvent and optional Occurrence/MeasurementOrFact projection |
| `core.schema_registry`, `core.domain_profiles` | Immutable, locally approved schema ID + SemVer + SHA pins; v0.12 eight domain schema drafts and envelope; validate three live entity types |
| `core.metadata_revisions` | Explicitly curated, user-approved metadata-envelope revisions and historical snapshots, separate from observation Parquet |
| `core.relation_assertions` | Four event/occurrence/measurement relations, append-only assert/replace/retract, current view, historical RUN snapshot; type/cardinality/cycle checks |
| `core.pipeline`, `core.change_audit`, `core.pipeline_run` | Allowlisted declarative operators, per-step row summaries, changed-value audit, immutable published RUN/2 and replay verification |
| `core.run_executor`, `core.profile`, `processing.tabular` | Separate CSV profile mapping execution and traditional reference lineage path |
| `core.export`, `core.run_recovery` | Artifact/checksum verification, reference Data Package export, explicit indexed-RUN reconciliation |
| `core.publication_*`, `core.eml_compiler` | Independently controlled EML / Darwin Core adapter primitives; not complete generalized publication lifecycle |
| Workbench / website | Separate frontend and product surfaces; the CS-PHOC automated test does **not** exercise the Workbench |

## 3. Project and RUN filesystem

```text
<project>/
  project.json
  catalog/catalog.sqlite                 # registry, reviews, relations, curated metadata
  objects/sha256/ab/<sha256>              # immutable original object
  imports/<import_id>/manifest.json
  packages/<package_id>/virtual-descriptor.json
  configurations/pipelines/<sha256>.json
  registry/schemas/<sha256>.json          # exact local schema bytes
  runs/<run_id>/
    manifest.json
    inputs.snapshot.json                 # source/field/relation/profile/metadata pins
    configuration.snapshot.json
    outputs/<named>.parquet              # generic DAG outputs
    outputs/samplingevent.parquet        # when explicitly projected
    outputs/occurrence.parquet           # optional
    outputs/measurementorfact.parquet    # optional
    audit/pipeline.json
    audit/value_changes.parquet          # ONLY if comparable values changed
    reports/quality.json
  exports/<export_id>/                    # separate versioned adapter outputs
```

A **CSV-profile RUN** differs: it uses `outputs/observations.parquet`, `audit/lineage.parquet` and its own snapshots, as documented in [User Guide](USER-GUIDE.md). Do not conflate those artifacts with generic DAG/Entity provenance.

## 4. Scientific and schema invariants

- **No inferred semantics.** Technical `entity_id` differs from scientific `event_id` / `occurrence_id`. SamplingEvent requires no coordinates, taxon, GPS, transect or Occurrence.
- **Source bytes do not mutate.** An imported object has a SHA-256 content address; resource/import identity and semantic field identity are separate.
- **Explicit confirmation.** SourceFieldDefinition revisions, target entity mappings, relation assertions and metadata revisions require explicit responsible-user action; a second independent reviewer is not mandatory.
- **Strict semantic profile selection.** Every semantic Entity pipeline **must** pin an explicitly approved envelope and exact domain schema ID/version/hash for each selected entity. No legacy unprofiled Entity pipeline path is supported. Purely technical source imports and non-entity DAG runs need no domain profile.
- **No confusion between zero and missing.** A real numeric `0` remains a data value; `null` requires explicit applicable missing semantics in a projected measurement.
- **Independent versioning.** Domain profiles, relation profile, input objects, field definition revisions and configuration/RUN are separately addressable; completed RUN/2 pins the exact reproducible state.

## 5. Audit, integrity and operations

The generic DAG retains deterministic, declarative transformations and hashes the inputs/config/output artifacts. `audit/pipeline.json` records each step and input/output cardinalities. Only **actual value differences with a defined comparison baseline** go to `audit/value_changes.parquet` (zero-to-zero or unchanged fields produce no row). Joins/unpivot/derived compound fields remain reconstructible from pinned inputs and versioned DAG, but **no guarantee of a saved physical source-cell entry for every value** is made.

RUN creation uses staging and publication, and `verify-project` replays the generic DAG and validates its output, sparse audit, profile/relation/metadata snapshots and manifests. SQLite and `project.json` do not share a single atomic commit; `reconcile-runs` is an explicit index recovery mechanism, **not** a substitute for tested full-power-loss recovery or backup/restore. SHA-256 detects modified bytes; it is not an authenticated signature or publication approval.

## 6. Validated coverage and remaining work

The current Engine implements the core project/import, generic RUN, reviewed semantic mapping, selected domain relation, schema-pin and metadata mechanisms in a bounded technical proof of concept. The ordinary Engine CI exercises generic technical behavior with synthetic inputs. The independent [CS-PHOC validation repository](https://github.com/FAIRmorph/fairmorph-validations/blob/main/docs/CS-PHOC-REPRODUCTION-AND-RESULTS.md) checks real research input against a **pinned** Engine version, including a generic RUN/2, but its DwC-A/TSV/GeoJSON test exporters are **dataset-specific code outside the Engine**.

Open implementation and assurance work includes broader Workbench field/profile interviews, generic publication projection and integration, additional independent datasets, more domain profiles, spatial-specialist validation, backups/recovery, multiwriter safety, distribution, and a stable migration/security model. A fully reviewed and approved scientific publication has not been demonstrated by the CS-PHOC test.

Before a stable public release, experimental contracts and APIs can evolve together with tests and documentation. Immutable source objects and completed RUN records must not be silently rewritten.

See [project scope](SCOPE-AND-DEVELOPMENT.md), [operations](OPERATIONS.md), [user guide](USER-GUIDE.md) and [API reference](API-REFERENCE.md).
