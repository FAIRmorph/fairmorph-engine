# Data Contracts, Mapping Semantics and Publication Formats

## 1. Contract model

FAIRmorph separates **physical input representation** (CSV/JSON/Parquet), **scientific semantics** (field definitions), **transformation decisions** (mapping), **execution evidence** (RUN) and **publication decisions** (profiles, metadata, projections). Each layer is validated separately. Schema validity does not imply scientific correctness or review approval.

## 2. Versioned JSON Schemas

Executable contracts are located in `src/fairmorph_engine/contracts/`; additional PoC/project contracts live in `contracts/`.

| Contract | Purpose |
| --- | --- |
| `SourceFieldDefinition.schema.json` | Field semantics and revision content |
| `csv-mapping-profile.schema.json` | External CSV mapping, policies and relationships |
| `import.schema.json` | Immutable source import evidence |
| `virtual-package.schema.json` | Virtual package resource references |
| `inputs.snapshot-v2.schema.json` | Source and registry pins captured in a RUN |
| `run-v2.schema.json` | RUN/2 manifest, status and artifact declarations |
| `publication-profile.schema.json` | Publication intent and output formats |
| `publication-projection.schema.json` | Publication table and column projection |
| `publication-integrity.schema.json` | Publication identifiers and integrity rules |

Legacy PoC contracts, including `run.schema.json`, `export.schema.json` and `project.schema.json`, are used by `core.export.validate_contract`. **The actual schema is authoritative for required fields, enumerations and additional-properties rules.**

## 3. External CSV mapping profiles

A mapping profile declares `mapping_id`, `version`, `operation`, `source_sha256`, `identifier`, `fields` and explicit policies. Each field specifies its source column, target name, meaningful description, definition provenance, zero semantics and missing-value tokens; count mappings additionally require `counting_unit`, and typed mappings require `value_type`.

Supported operations:

- `wide-to-long-counts/1`: integer counts, `empty_cell_policy: "omit"` and `zero_cell_policy: "preserve"`; count zero meaning must be `true_zero` or `absence`.
- `wide-to-long-values/1`: typed values with `value_type` equal to `integer`, `decimal` or `text` and declared missing tokens.

The process is **validate and stage draft → review field revisions → approve mapping → execute RUN**. Optional `auxiliary_resource_ids` and `relationships` pin and validate linked resources, but **do not execute implicit joins**.

See the [User Guide](USER-GUIDE.md) for exact profile fields, constraints and a working-shaped synthetic example.

## 4. RUN/2 artifacts

`runs/<run_id>/manifest.json` records `schema_version = fairmorph.poc.run/2`, `run_id`, `status = completed`, execution metadata, `configuration_sha256`, `input_snapshot_sha256` and artifact paths/sizes/SHA-256 hashes.

`inputs.snapshot.json` captures approved source and registry pins; `configuration.snapshot.json` captures the mapping configuration. `outputs/observations.parquet` stores normalized rows (including `record_id`, `source_identifier`, `source_line`, `source_column`, `target_field`, `value` and, for typed mappings, `value_type`). `audit/lineage.parquet` preserves provenance. `reports/quality.json` reports observed metrics.

RUN/2 verification checks source and registry references in addition to artifact bytes. Checksums alone cannot establish scientific validity.

## 5. Generic Data Package

`export_data_package` first verifies the RUN, then creates `package/datapackage.json`, `observations.csv`, `lineage.csv` and `quality.json` in a versioned export directory. An `export-manifest.json` pins the source RUN and exported artifacts. **This generic Data Package is not a Darwin Core Archive.**

## 6. Optional publication pipeline

Four externally supplied documents are kept separate:

1. **Publication profile:** requested formats (`eml/2.2.0`, `dwca/1`) and explicit Darwin Core bindings.
2. **Publication metadata:** descriptive metadata; EML requires an explicit `publication_date`.
3. **Projection plan:** RUN-pinned Parquet artifacts, row types, selected columns and optional expected types.
4. **Integrity rules:** identifiers, relationships and required key conditions.

The workflow is **intent validation → projection → bindings → integrity → materialization → adapter**. Materialization writes deterministically ordered CSV tables and a manifest. The EML adapter compiles XML and validates it against an official local EML 2.2.0 XSD. The DwC-A adapter creates a ZIP with `meta.xml` and declared core/extension tables; validation checks schema and archive references. Vendored schemas are located under `vendor/schemas/eml/2.2.0/` and `vendor/schemas/dwca/`.

Adapters neither infer scientific taxonomy nor publish to an external service.

## 7. Versioning and compatibility

Schema versions, mapping versions and transformation versions are independent of the Python package version. Export verification distinguishes RUN/1 and RUN/2; publication projections require RUN/2. The local schema registry supports new profile kinds without an automatic SQLite core migration. General project migration and guaranteed backward compatibility of Draft APIs are not yet provided.
