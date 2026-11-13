# FAIRmorph Engine User Guide

This guide demonstrates a **complete, locally executable CSV-to-verified-RUN workflow** using the Engine's reviewed mapping CLI. It uses synthetic data so the expected results are transparent and reproducible. No external biodiversity interpretation or Workbench UI is needed.

**Before you start:** Install Python 3.11+ and the Engine using [INSTALL.md](../INSTALL.md), then run `fairmorph-engine --help`. Run all commands below from the same working directory. For the distinct generic DAG/entity pipeline, see [Generic project pipelines](project-driven-run.md).

## 1. Prepare and import a small CSV

Save this file as `survey.csv`:

```csv
site_id,oak_count,pine_count
S01,2,0
S02,0,3
S03,,1
```

Its source-grounded expectations are:

| Property | Expected |
| --- | ---: |
| Original CSV rows | 3 |
| Potential numeric count cells | 6 |
| Nonblank count cells | 5 |
| Explicit zeros | 2 |
| Blank cells | 1 |
| Sum of nonblank values | 6 |

A blank is **not** the number zero. Scientific meaning and units are decisions supplied explicitly by the operator, not inferred by the Engine.

The expected *logical* long-form result is easy to inspect before running any software:

| Source record | Source column | Value |
| --- | --- | ---: |
| `S01` | `oak_count` | 2 |
| `S01` | `pine_count` | 0 |
| `S02` | `oak_count` | 0 |
| `S02` | `pine_count` | 3 |
| `S03` | `pine_count` | 1 |

There is **no `S03 / oak_count` output row**, because that source cell is blank. These five rows describe the scientific-independent value projection; the Engine's actual Parquet also contains provenance fields and generated record identifiers.

```bash
fairmorph-engine init-project --project ./survey.fairmorph --name "Example Survey"
fairmorph-engine import-resource --project ./survey.fairmorph --source ./survey.csv --role survey
```

The import creates a project, stores unchanged source bytes under `objects/sha256/`, and emits a JSON-line result with `resource_id` and `sha256`. **Copy the returned real SHA-256.** A source import has no scientific approval and produces no transformed output.

## 2. Declare a mapping with explicit semantics

Create `survey-mapping.json` and replace `REPLACE_WITH_64_CHARACTER_IMPORT_SHA256` with the actual input digest returned above:

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
      "description": "Count of oak observations for the given site.",
      "definition_source": "user_confirmed",
      "counting_unit": "observations",
      "zero_meaning": "true_zero",
      "missing_values": [{"token": "", "meaning": "No count was supplied"}]
    },
    {
      "source_column": "pine_count",
      "target_field": "pine_observations",
      "description": "Count of pine observations for the given site.",
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

This profile is a **demonstration fixture**, not a source of genuine biological field definitions. For actual research data, the reviewer must confirm units, counting method, missing/zero interpretation and provenance from reliable sources. The mapping shape is governed by `src/fairmorph_engine/contracts/csv-mapping-profile.schema.json`.

## 3. Stage, explicitly approve, and run

Use the `resource_id` and `mapping_sha256` returned by your own local commands:

```bash
fairmorph-engine stage-csv-mapping \
  --project ./survey.fairmorph \
  --resource-id RESOURCE_ID \
  --profile ./survey-mapping.json

fairmorph-engine approve-mapping \
  --project ./survey.fairmorph \
  --mapping-sha256 MAPPING_SHA256 \
  --confirmed-by example-curator

fairmorph-engine run-mapping \
  --project ./survey.fairmorph \
  --mapping-sha256 MAPPING_SHA256
```

**The approval command is an explicit action.** Staging a valid JSON profile alone does not mean the underlying science has been approved. On real data, `--confirmed-by` must identify the actual responsible reviewer; do not use the demonstration identifier as a substitute for review.

The run prints JSON-line progress and a final result containing a **new `run_id`**. For this synthetic input, five rows with two zeros and sum six should be recorded. The accepted CSV-to-long transformation keeps source identifiers and column provenance; it does not create taxonomic occurrences automatically.

## 4. Verify and inspect output

```bash
fairmorph-engine verify-project --project ./survey.fairmorph
fairmorph-engine export-package --project ./survey.fairmorph --run-id RUN_ID
fairmorph-engine verify-project --project ./survey.fairmorph
```

Replace `RUN_ID` with the actual run identifier. A successful verification returns `status: "verified"` inside the Engine's result data. The CLI emits **newline-delimited JSON**, normally with events shaped like:

```json
{"event": "result", "status": "success", "data": {"run_id": "GENERATED_RUN_ID"}}
```

The exact `data` shape varies by command; the example above illustrates the event envelope, not a promise about all fields.

The project contains, among other files:

```text
survey.fairmorph/
  project.json
  catalog/catalog.sqlite
  objects/sha256/<prefix>/<full-sha256>
  imports/...
  runs/<run-id>/
    manifest.json
    inputs.snapshot.json
    configuration.snapshot.json
    outputs/observations.parquet
    audit/lineage.parquet
    reports/quality.json
  exports/...
```

The completed RUN and its manifest hash the source and output artifacts. The generic `export-package` creates a **Frictionless-style Data Package** (CSV plus `datapackage.json`, lineage/quality evidence and an export manifest). It is **not** a Darwin Core Archive, EML submission or PANGAEA deposition.

## 5. Which workflow should I use?

| Goal | Entry point | What it demonstrates |
| --- | --- | --- |
| Import only | `init-project`, `import-resource` | Unchanged source identity and catalog |
| Reviewed wide-to-long CSV example | `stage-csv-mapping`, `approve-mapping`, `run-mapping` | Simple reviewed profile, per-record source lineage, Data Package export |
| Generic reproducible transformations | `register-pipeline`, `select-pipeline`, `run-pipeline` | Declarative DAG operations, RUN/2, row-count and sparse change audit |
| Scientific entities | Generic pipeline plus `SourceFieldDefinition` approvals, installed profile bindings and `confirm-projection` | Selected semantic Entity output with exact approved schema/revision pins |
| Publication-oriented materialization | Explicit publication profile, metadata, projection and integrity documents | Separate EML/DwC-A APIs; not a universal one-command exporter |

The **CSV mapping and generic DAG paths are separate** and may produce different output/audit layouts. For the generic path, follow [project-driven RUN](project-driven-run.md), [contracts](DATA-CONTRACTS.md) and the [API reference](API-REFERENCE.md).

## 6. Common failures and operational limits

- **Invalid source hash / changed input:** Import the new bytes as a *new* source revision and update the profile. Do not rewrite a stored original.
- **Mapping/field validation error:** Check original CSV headers, supported profile fields, review status and explicit `missing_values` / `zero_meaning` semantics.
- **Unapproved or stale mapping:** Confirm the actual current definition/revision, then use its returned hash. Registration is not approval.
- **Existing project directory:** `init-project` rejects overwriting. Use a new project location for a fresh demonstration.
- **Failed or interrupted RUN:** Do not delete partially written project state manually. Follow [RUN recovery](RUN-RECOVERY.md) and inspect `verify-project` / `reconcile-runs`.
- **Scientific interpretation:** A technically correct output is not a scientifically endorsed dataset or a permission to publish it.

## 7. Independent real-data evidence

For the pinned CS-PHOC research census reference, see the external [FAIRmorph validations reproduction and results guide](https://github.com/FAIRmorph/fairmorph-validations/blob/main/docs/CS-PHOC-REPRODUCTION-AND-RESULTS.md). That repository validates real source bytes, the generic Engine RUN and **dataset-specific test exports** with an independent file audit. It does **not** demonstrate a fully operational Workbench, generic PANGAEA/GeoJSON publication, or formal scientific approval of the imported field descriptions.
