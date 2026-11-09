# Architecture, Components and Concepts

## 1. System boundary

The engine comprises a Typer CLI (`src/fairmorph_engine/cli.py`), Python core modules (`core/`), tabular transformations (`processing/`), versioned JSON Schema contracts (`contracts/`) and separate reference examples (`examples/`). Processing is local; the inspected core does not expose an HTTP or gRPC API.

```text
CSV / external mapping profiles / publication metadata
                       |
                 CLI (NDJSON)
                       |
             Project + SHA-256 object store
                       |
     SQLite: resources, field revisions, reviews, mappings
                       |
             Approval -> generic RUN/2 executor
                       |
       runs/<RUN_ID>/ (Parquet, lineage, snapshots, manifest)
                       |
       Verification -> Data Package / optional publication adapters
                       |
         Explicit interrupted-RUN reconciliation
```

## 2. Component inventory

| Module | Responsibility |
| --- | --- |
| `cli.py` | CLI commands, structured NDJSON events, error exit codes |
| `core/project.py` | Project initialization, SQLite base catalog, import, SHA objects, virtual packages |
| `core/registry.py` | Append-only field revisions, review decisions, mapping versions and snapshots |
| `core/schema_registry.py` | Local versioned schema registry; rejects remote `$ref` |
| `core/profile.py` | External CSV profile validation, preflight, staging and grouped approval |
| `processing/tabular.py` | Generic wide-to-long count and typed-value transformations |
| `core/run_executor.py` | Approval and pin verification, Polars/Parquet, quality metrics, RUN/2 publication |
| `core/export.py` | RUN verification, Frictionless-style Data Package and project verification |
| `core/run_recovery.py` | Explicit index reconciliation from verified completed RUN directories |
| `core/publication.py` | Publication intent and metadata validation |
| `core/publication_projection.py` | Declared publication tables/columns versus pinned Parquet artifacts |
| `core/publication_bindings.py` | Darwin Core bindings versus projection columns |
| `core/publication_integrity.py` | Publication-level identifier and relationship checks |
| `core/publication_materialize.py` | Materialization of declared publication CSV tables |
| `core/publication_adapters.py` | EML and Darwin Core Archive creation/validation |
| `core/eml_compiler.py` | EML XML compilation from project metadata |

## 3. On-disk project structure

```text
<project>/
  project.json                  # readable project index
  catalog/catalog.sqlite       # identities, reviews and mapping states
  objects/sha256/ab/<sha256>    # original immutable source bytes
  imports/<import_id>/manifest.json
  packages/<package_id>/virtual-descriptor.json
  configurations/
  registry/schemas/            # versioned local schemas, when registered
  runs/
    .pending-<run_id>/         # incomplete or failed execution
    <run_id>/
      manifest.json
      inputs.snapshot.json
      configuration.snapshot.json
      outputs/observations.parquet
      audit/lineage.parquet
      reports/quality.json
  exports/<export_id>/
    export-manifest.json
    package/datapackage.json
    package/observations.csv
    package/lineage.csv
    package/quality.json
```

The project index records `project_id`, `name`, `schema_version`, `catalog_schema_version`, `input_objects`, `package_ids` and `run_ids`. SQLite base tables include `project_meta`, `source_objects`, `source_resources`, `packages`, `package_resources` and `runs`. Registry operations add `source_fields`, `field_definition_revisions`, `field_definition_reviews`, `current_field_definitions`, `mapping_versions`, `mapping_reviews` and `mapping_field_bindings`; the schema registry adds `schema_versions`.

## 4. Identity, immutability and approval

**Source identity:** Every imported source is identified by its SHA-256 digest. Identical bytes can be deduplicated. The `imported_unmapped` state explicitly means that no scientific interpretation has been approved.

**Field semantics:** A `source_field_id` identifies a source field; immutable `field_definition_revisions` capture its semantic definitions. `field_definition_reviews` record explicit decisions. Descriptions, definition provenance, counting units and missing/zero semantics must be supplied rather than inferred.

**Mapping versions:** `mapping_id` and `version` express mapping identity; `mapping_sha256` pins its exact content. `draft` and `approved` are distinct states. Execution resolves approved, internally consistent snapshots; later mapping changes do not rewrite an existing RUN.

**Schema registry:** `schema_id` is an HTTPS URI, `schema_version` is SemVer, and `schema_sha256` pins content. Schemas are validated locally; remote `$ref` is rejected. Statuses `draft`, `approved` and `deprecated` are registry states, not automatic migrations.

## 5. Transformations and RUN/2

`wide-to-long-counts/1` and `wide-to-long-values/1` convert declared CSV columns into observation rows. Counts require explicit empty-cell and zero policies. Typed values require `integer`, `decimal` or `text` types and missing-token declarations. The engine does not infer scientific thresholds or taxonomies.

A RUN derives `record_id` from the source hash, source row/column, transformation version and mapping hash. `lineage.parquet` retains source provenance. `inputs.snapshot.json` pins source and registry state; `configuration.snapshot.json` captures the mapping configuration. The manifest checksums generated artifacts. Quality metrics such as `output_rows`, `explicit_zeros` and `value_sum` describe observed output; any expected values must be declared by the project.

Publication starts in `runs/.pending-*`, then renames the directory to `runs/<run_id>` and updates `project.json` and SQLite. These stores do not share a transaction: a crash can leave a completed directory absent from one or both indexes. Explicit [RUN recovery](RUN-RECOVERY.md) addresses these cases.

## 6. Trust and security boundaries

Checksums detect byte modifications but do not replace digital signatures or access control. Verification rejects modified artifacts and unsafe paths. Scientific correctness depends on externally reviewed definitions and mappings. Recovery requires exclusive writer access. EML/DwC-A validation uses local XSDs from `vendor/schemas/` or explicitly supplied paths. A structurally valid publication artifact does not imply scientific or organizational publication approval.

## 7. External reference

`examples/cs-phoc/` is an **optional** reference implementation. Its regression workflow is manual (`workflow_dispatch`); ordinary engine CI uses generic synthetic datasets.
