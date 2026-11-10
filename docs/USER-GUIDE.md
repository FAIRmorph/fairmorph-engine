# FAIRmorph Engine — User Guide

**Audience:** Data curators, scientific reviewers and operators running the generic CSV-to-Parquet workflow. **Scope:** Framework v0.12 Draft branch (Python package version `0.1.0`). This guide uses **synthetic, dataset-independent** inputs. The code and JSON Schemas in the branch are authoritative.

## 1. Requirements and installation

Install Python **3.11+**. From the repository root:

```bash
python -m pip install -e ".[dev]"
fairmorph-engine --help
fairmorph-engine handshake
```

The engine runs locally and does not need a remote API. Use separate writable directories for input files and generated project state. Paths below are relative to your current working directory. Windows users can run the same commands in PowerShell with suitable paths.

## 2. Prepare a source CSV

Create a UTF-8 file named `survey.csv`:

```csv
site_id,oak_count,pine_count
S01,2,0
S02,0,3
S03,,1
```

The header must contain **unique** column names. `site_id` is the identifier, and the two count columns are explicitly selected for transformation. An empty `oak_count` cell in the last row is **omitted**; zero values are **preserved**. These are technical processing rules, not automatically inferred scientific facts.

For this sample, the expected long-format observation count is **5** (six potential cells minus one empty cell), the number of explicit zeros is **2**, and the sum of counts is **6**. These expectations are valid **only for this sample** and must not be hardcoded into the engine.

Avoid editing the CSV after import. If the bytes change, import the new version and create a new mapping profile with its new source SHA-256.

## 3. Initialize a project and import data

```bash
fairmorph-engine init-project --project ./survey-project --name "Synthetic Survey"
fairmorph-engine import-resource --project ./survey-project --source ./survey.csv --role observations
```

The import result contains a `resource_id` and `sha256`. Record both. The source is stored under `objects/sha256/<first-two-hash-chars>/<full-sha256>` and is registered with the state `imported_unmapped`. Importing does **not** approve any interpretation.

`--role` must be a safe identifier consisting of letters, digits, underscore, dot or hyphen; it cannot be `.` or `..`.

## 4. Configure the CSV mapping profile

Create `survey-mapping.json`. Replace `REPLACE_WITH_64_CHARACTER_IMPORT_SHA256` with the **exact** SHA-256 returned by the import; the placeholder is not valid input.

```json
{
  "mapping_id": "synthetic-survey-counts",
  "version": "1.0.0",
  "operation": "wide-to-long-counts/1",
  "source_sha256": "REPLACE_WITH_64_CHARACTER_IMPORT_SHA256",
  "identifier": "site_id",
  "empty_cell_policy": "omit",
  "zero_cell_policy": "preserve",
  "fields": [
    {
      "source_column": "oak_count",
      "target_field": "oak_observations",
      "description": "Number of oak observations recorded at the site.",
      "definition_source": "user_confirmed",
      "counting_unit": "observations",
      "zero_meaning": "true_zero",
      "missing_values": [{"token": "", "meaning": "No count was supplied"}]
    },
    {
      "source_column": "pine_count",
      "target_field": "pine_observations",
      "description": "Number of pine observations recorded at the site.",
      "definition_source": "user_confirmed",
      "counting_unit": "observations",
      "zero_meaning": "true_zero",
      "missing_values": [{"token": "", "meaning": "No count was supplied"}]
    }
  ],
  "acceptance": {
    "output_rows": 5,
    "explicit_zeros": 2,
    "value_sum": 6
  }
}
```

### 4.1 Top-level input parameters

| Property | Required | Allowed values / meaning |
| --- | --- | --- |
| `mapping_id` | Yes | Stable identifier using `A-Z a-z 0-9 _ . -` |
| `version` | Yes | Three-part semantic version such as `1.0.0` |
| `operation` | Yes | `wide-to-long-counts/1` or `wide-to-long-values/1` |
| `source_sha256` | Yes | Lowercase 64-character hexadecimal digest of the imported source |
| `identifier` | Yes | Existing CSV column containing the source record identifier |
| `empty_cell_policy` | Yes | Currently only `omit` |
| `zero_cell_policy` | Yes | Currently only `preserve` |
| `fields` | Yes | Nonempty array of explicitly described source fields |
| `acceptance` | No | Expected `output_rows`, `explicit_zeros`, `value_sum` (nonnegative integers); values must match observed output |
| `auxiliary_resource_ids` | No | IDs of separately imported auxiliary resources; pinned but not automatically joined |
| `relationships` | No | Declarative links validated during preflight; **no implicit join** |

The schema forbids unknown top-level properties (`additionalProperties: false`). For typed values, `acceptance.output_rows` is the applicable supported metric; count-specific `explicit_zeros` and `value_sum` are not available in the typed execution path.

### 4.2 Field configuration

| Property | Required | Meaning |
| --- | --- | --- |
| `source_column` | Yes | Exact existing CSV header; must differ from the identifier |
| `target_field` | Yes | Target name in the normalized observations |
| `description` | Yes | Substantive description, at least 12 characters |
| `definition_source` | Yes | `source_documentation` or `user_confirmed` |
| `zero_meaning` | Yes | `true_zero`, `absence`, `not_applicable`, `unknown`, `other`; counts permit only the first two |
| `missing_values` | Yes | Array of `{"token": "...", "meaning": "..."}` objects |
| `counting_unit` | For counts | Explicit nonempty unit of counted entities |
| `value_type` | For typed values | `integer`, `decimal` or `text` |
| `attributes` | No | Object with string values for additional field metadata |

The mapping profile is validated against `src/fairmorph_engine/contracts/csv-mapping-profile.schema.json`. The underlying field registry stores approved revisions separately. Do not equate an unreviewed description with scientific approval.

### 4.3 Typed values

For a source with text or decimal measurements, use `"operation": "wide-to-long-values/1"` and specify `value_type` on **every** field. For example:

```json
{
  "source_column": "temperature_c",
  "target_field": "temperature",
  "description": "Measured temperature of the sampled location.",
  "definition_source": "source_documentation",
  "zero_meaning": "true_zero",
  "missing_values": [{"token": "NA", "meaning": "Measurement unavailable"}],
  "value_type": "decimal"
}
```

This is a **field fragment**, not a standalone mapping. It belongs in the `fields` array of a full typed profile. The engine does not infer units, precision, or domain meaning from the column name.

## 5. Optional auxiliary resources and relationships

Import each additional CSV separately and collect its `resource_id`. Then add it to `auxiliary_resource_ids` and optionally declare a relationship:

```json
{
  "relationship_id": "survey-to-sites",
  "left_resource_id": "REPLACE_WITH_MAIN_RESOURCE_ID",
  "left_column": "site_id",
  "right_resource_id": "REPLACE_WITH_SITE_RESOURCE_ID",
  "right_column": "site_id",
  "cardinality": "many-to-one",
  "require_match": true,
  "missing_key_policy": "reject"
}
```

This is a **relationship object fragment** to place in the `relationships` array. Supported cardinalities: `one-to-one`, `one-to-many`, `many-to-one`, `many-to-many`. `require_match` defaults to `true`, and `missing_key_policy` defaults to `reject` (alternative: `ignore`). Preflight validates resource identities, CSV columns, uniqueness, missing keys and required matches. **Relationships are validation declarations, not instructions to join datasets during RUN execution.**

## 6. Stage, review and approve

```bash
fairmorph-engine stage-csv-mapping \
  --project ./survey-project \
  --resource-id RESOURCE_ID \
  --profile ./survey-mapping.json
```

The stage result contains `mapping_sha256`, `mapping_id`, `version`, `status: "draft"` and field revision IDs. The command checks the source hash and header, validates relationships and registers versioned field definitions.

Review the field descriptions, counting units, missing-value semantics, zero semantics and acceptance expectations. Then approve explicitly:

```bash
fairmorph-engine approve-mapping \
  --project ./survey-project \
  --mapping-sha256 MAPPING_SHA256 \
  --confirmed-by "data-curator"
```

Use the exact mapping SHA-256 from staging. Approval is an explicit, recorded action; it is not inferred from a valid JSON document.

## 7. Execute the transformation

```bash
fairmorph-engine run-mapping \
  --project ./survey-project \
  --mapping-sha256 MAPPING_SHA256
```

The command validates the approved registry snapshot and source bytes, transforms the selected CSV fields and creates a completed RUN only after successful processing and artifact checks. It emits progress and result events in NDJSON. Capture the returned `run_id`.

The executor creates:

```text
survey-project/
  project.json
  catalog/catalog.sqlite
  objects/sha256/<prefix>/<sha256>
  imports/<import_id>/manifest.json
  runs/<run_id>/
    manifest.json
    inputs.snapshot.json
    configuration.snapshot.json
    outputs/observations.parquet
    audit/lineage.parquet
    reports/quality.json
```

**Output data structure:** `observations.parquet` contains `record_id`, `source_identifier`, `source_line`, `source_column`, `target_field`, `value`, and `value_type` for typed mappings. `lineage.parquet` records source provenance. The RUN manifest contains artifact paths and SHA-256 digests; the two snapshots pin source/registry state and mapping configuration.

The acceptance criteria in the example must match the observed metrics or execution fails. Failed attempts may leave `runs/.pending-*` directories with diagnostic information.

## 8. Verify the project and export

Verify before and after exporting:

```bash
fairmorph-engine verify-project --project ./survey-project
fairmorph-engine export-package --project ./survey-project --run-id RUN_ID
fairmorph-engine verify-project --project ./survey-project
```

`verify-project` checks indexed sources, imports, packages, RUN artifacts and exports. It does not change project data. A generic export produces `datapackage.json`, `observations.csv`, `lineage.csv`, `quality.json` and an export manifest. **This is not a Darwin Core Archive.**

### Interpreting CLI results

Each CLI event is one JSON object per line. For example, the event structure is:

```json
{"event":"result","status":"success","data":{"project_id":"...","project_path":"..."}}
```

The `data` fields vary by command. Read the returned IDs; do not treat the example ellipses as literal output. For handled failures, expect a `result` event with `status: "error"` and a nonzero exit code. Some unhandled exceptions can still produce a Python traceback.

## 9. Contracts and schema configuration

**Where contracts live:**

| Location | Content |
| --- | --- |
| `src/fairmorph_engine/contracts/csv-mapping-profile.schema.json` | Input profile shape and supported operations |
| `src/fairmorph_engine/contracts/SourceFieldDefinition.schema.json` | Detailed field semantics and review metadata |
| `src/fairmorph_engine/contracts/import.schema.json` | Import manifest contract |
| `src/fairmorph_engine/contracts/inputs.snapshot-v2.schema.json` | RUN input snapshot contract |
| `src/fairmorph_engine/contracts/run-v2.schema.json` | RUN/2 manifest contract |
| `src/fairmorph_engine/contracts/virtual-package.schema.json` | Virtual package contract |
| `src/fairmorph_engine/contracts/publication-*.schema.json` | Publication profile, projection and integrity contracts |
| `contracts/` | Additional project/PoC contracts |
| `vendor/schemas/eml/2.2.0/` | Local official EML XSDs |
| `vendor/schemas/dwca/` | Local Darwin Core Archive metadata XSD |

**Do not edit built-in contracts to make an invalid profile pass.** Supply values that conform to the applicable schema. For project-specific schema extensions, use the versioned Python schema registry (`register_schema`/`get_schema`) with exact HTTPS `schema_id`, SemVer `schema_version`, content hash and explicit reviewer status. The registry rejects remote `$ref`; registering a schema does not automatically change the CSV executor's accepted profile schema.

The `SourceFieldDefinition` contract includes identity, field locator, semantic/review statuses, definition provenance, description, optional unit/counting metadata, missing-value definitions, zero meaning, evidence and reviewer information. The staged CSV profile is a **simpler external authoring format** that the engine converts into registry revisions; these are not interchangeable JSON files.

## 10. Optional publication formats

The generic Data Package workflow is the normal CLI export. EML 2.2.0 and Darwin Core Archive require **additional externally authored** publication profile, metadata, projection plan and integrity rules, validated against their own schemas. The publication adapters are Python functions, not separate built-in CLI commands:

```python
from pathlib import Path
from fairmorph_engine.core.publication import validate_publication_intent
from fairmorph_engine.core.publication_projection import validate_publication_projection
from fairmorph_engine.core.publication_bindings import validate_publication_binding_columns
from fairmorph_engine.core.publication_integrity import validate_publication_integrity

project = Path("./survey-project")
run_id = "REPLACE_WITH_RUN_ID"
profile = Path("./publication-profile.json")
metadata = Path("./publication-metadata.json")
projection = Path("./publication-projection.json")
integrity = Path("./publication-integrity.json")

validate_publication_intent(project, run_id, profile, metadata)
validate_publication_projection(project, run_id, projection)
validate_publication_binding_columns(project, run_id, profile, metadata, projection)
validate_publication_integrity(project, run_id, profile, metadata, projection, integrity)
```

The example is an **API invocation template**, not a runnable publication configuration until the four JSON files are supplied and valid. After validation, `materialize_publication_tables`, `export_eml` and `export_dwca` may be used. EML requires an explicit publication date and local EML XSD; DwC-A requires declared core/extension bindings and integrity rules. Consult [Data Contracts](DATA-CONTRACTS.md) and [API Reference](API-REFERENCE.md).

## 11. Crash recovery and safe operations

If execution is interrupted during publication, a complete RUN directory may exist without matching entries in `project.json` and/or SQLite. Stop **all** project writers, back up the project, then run:

```bash
fairmorph-engine reconcile-runs --project ./survey-project
fairmorph-engine verify-project --project ./survey-project
```

Reconciliation validates completed RUN directories and restores missing index references. It does not automatically promote `.pending-*` directories or silently accept corrupted RUNs. Do not run it concurrently with another writer. This PoC does not claim complete power-loss durability or cross-process locking. See [RUN Recovery](RUN-RECOVERY.md).

## 12. Troubleshooting and validation checklist

| Symptom | Action |
| --- | --- |
| Source hash mismatch | Reimport changed bytes and create a new pinned profile |
| Unknown or duplicate CSV header | Correct the CSV and restage |
| Mapping remains `draft` | Review fields and run `approve-mapping` |
| Invalid count semantics | Supply `counting_unit`, `true_zero` or `absence`, and explicit missing tokens |
| Typed parser error | Check each `value_type` and source cell; define missing tokens |
| Relationship preflight fails | Check imported resource IDs, key columns, cardinality and missing-key policy |
| Acceptance metrics differ | Check input data and expectations; do not force expected values to match blindly |
| Artifact checksum fails | Treat the RUN as corrupted; investigate instead of editing manifests |
| RUN directory exists but is not indexed | Stop writers, back up and explicitly reconcile |
| Publication preflight fails | Check the separate profile, metadata, projection, integrity rules and XSD |

For acceptance, run `ruff check src tests`, `ruff format --check src tests`, and `pytest --cov=fairmorph_engine --cov-report=xml`. The fault-injection suite and generic end-to-end tests must pass on both Ubuntu and Windows before formal PoC recovery acceptance. The CS-PHOC reference is optional and manually triggered; it is not an engine configuration default.

**Further reading:** [Architecture](ARCHITECTURE.md) · [API Reference](API-REFERENCE.md) · [Data Contracts](DATA-CONTRACTS.md) · [Operations](OPERATIONS.md).
