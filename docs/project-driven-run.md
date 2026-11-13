# Generic project-driven RUN/2 pipelines

This guide covers the Engine's **declarative DAG workflow**, which is distinct from the simpler reviewed CSV mapping workflow in the [user guide](USER-GUIDE.md). Data processing executes locally inside a project with imported, SHA-256-pinned original inputs.

## 1. How a project-driven run works

```text
Original source file(s)
       |
       v
import-resource -> immutable source objects and resource IDs
       |
       v
pipeline JSON -> register-pipeline -> content-addressed pipeline SHA-256
       |
       +-- optional semantic entity mappings require:
       |      reviewed SourceFieldDefinitions
       |      approved exact schema profile bindings
       |      explicit confirm-projection decision
       |
       v
select-pipeline -> run-pipeline -> immutable RUN/2
                                      |
                                      v
                                verify-project
```

The active selected configuration belongs to the **project**, not an arbitrary runtime `--config` value. The import and a **technical-only** DAG do not require biodiversity profiles or a scientific interpretation. Only explicitly declared supported operators execute.

## 2. Prepare and run a technical DAG

First install the Engine and import your source file as described in [INSTALL.md](../INSTALL.md). The import prints an actual resource ID. In the pipeline JSON, set `resources.<role>.resource_id` to that value; do **not** use placeholders from example templates in executable declarations.

A representative declaration shape is:

```json
{
  "schema_version": "fairmorph.pipeline/1",
  "resources": {
    "counts": {
      "resource_id": "REPLACE_WITH_REAL_IMPORTED_RESOURCE_ID",
      "format": "csv"
    }
  },
  "steps": [
    {
      "id": "unpivot_counts",
      "operator": "table.unpivot/1",
      "inputs": ["counts"],
      "output": "long_counts",
      "parameters": {
        "columns": ["oak_count", "pine_count"],
        "identifiers": ["site_id"],
        "variable": "count_type",
        "value": "count_value"
      }
    },
    {
      "id": "keep_recorded",
      "operator": "table.filter/1",
      "inputs": ["long_counts"],
      "output": "recorded_counts",
      "parameters": {
        "predicate": {
          "column": "count_value",
          "op": "is_not_null",
          "value": null
        }
      }
    }
  ],
  "outputs": ["recorded_counts"]
}
```

Save as `pipeline.json` and replace the resource identifier. For the three-row synthetic CSV in the user guide, the expected output is **five nonblank long rows**, including **two numerical zero values**; null filtering does not treat zero as missing. The exact schema and operator behavior are controlled by the Engine's versioned contracts.

```bash
fairmorph-engine register-pipeline --project ./survey.fairmorph --definition ./pipeline.json
fairmorph-engine select-pipeline --project ./survey.fairmorph --pipeline-sha256 PIPELINE_SHA256
fairmorph-engine run-pipeline --project ./survey.fairmorph
fairmorph-engine verify-project --project ./survey.fairmorph
```

Replace `PIPELINE_SHA256` with the hash returned by `register-pipeline`. The RUN command returns a **generated run ID**; use that for reading artifacts. The technical DAG itself does not automatically create domain entities, assert relations, or approve scientific semantics.

### RUN evidence

For each completed generic RUN/2, the Engine records:

- `runs/<run-id>/manifest.json`: immutable output declarations, SHA-256 digests and integrity evidence.
- `runs/<run-id>/inputs.snapshot.json` and `configuration.snapshot.json`: pinned input/configuration and applicable reviewed decisions.
- `runs/<run-id>/outputs/*.parquet`: named output tables from the pipeline.
- `runs/<run-id>/audit/pipeline.json`: selected input/output cardinalities, operator rules and execution evidence.
- `audit/value_changes.parquet` **only if directly comparable values were actually modified** by a supported derivation. It is not a mandatory per-cell history for unchanged data.

The old reviewed CSV mapping path instead writes `outputs/observations.parquet` and a distinct `audit/lineage.parquet` reference-style audit. **Do not assume both workflows create identical artifacts.**

## 3. Add scientific Entity projections only with explicit decisions

A generic pipeline can optionally declare `entities` such as `SamplingEvent`, `Occurrence` and `MeasurementOrFact`. This requires a more restrictive process.

1. Create versioned **SourceFieldDefinition** documents using the Engine's schema, one per relevant physical source field. Each declaration must reflect a source-backed meaning, missing-value policy and, where relevant, a count unit. Register via the Engine Registry's `define_field()` Python API.
2. Review each specific immutable definition revision through `review_field(project, revision_id, reviewer, "approved")`. The reviewer is the **actual responsible confirming user**; the PoC does not enforce a separate second signer. `semantic_status: "defined"` and a substantive description are required. A draft does **not** satisfy the condition.
3. Install and confirm supported schema profile contracts in the project, then request the exact approved pins:

   ```bash
   fairmorph-engine install-profile-contracts --project ./survey.fairmorph --confirmed-by researcher
   fairmorph-engine profile-bindings --project ./survey.fairmorph --entities SamplingEvent,MeasurementOrFact
   ```

4. Include returned exact `schema_id`, `schema_version`, `schema_sha256` and source-definition `source_field_id` / `definition_revision_id` / `definition_sha256` in a new pipeline's `profile_bindings` and `entities` declarations. Reference [data contracts](DATA-CONTRACTS.md) and [API](API-REFERENCE.md) for supported fields and constraints.
5. Register that **new** pipeline, explicitly confirm its scientific projection and execute it:

   ```bash
   fairmorph-engine register-pipeline --project ./survey.fairmorph --definition ./entity-pipeline.json
   fairmorph-engine confirm-projection --project ./survey.fairmorph --pipeline-sha256 PIPELINE_SHA256 --confirmed-by researcher
   fairmorph-engine select-pipeline --project ./survey.fairmorph --pipeline-sha256 PIPELINE_SHA256
   fairmorph-engine run-pipeline --project ./survey.fairmorph
   fairmorph-engine verify-project --project ./survey.fairmorph
   ```

A source identifier and an Entity identifier are different concepts. For example, a survey window is not automatically identical to a location-specific published Event, and a numeric count does not automatically represent an individual biological Occurrence. Such target mappings must be supplied and reviewed.

### Optional relations and curated metadata

The PoC supports selected typed, append-only relations (`parent_event`, `event_occurrence`, `event_measurement`, `occurrence_measurement`) with a confirming user and source reference:

```bash
fairmorph-engine assert-relation --project ./survey.fairmorph \
  --pipeline-sha256 PIPELINE_SHA256 --predicate parent_event \
  --subject-id e2 --object-id e1 --confirmed-by researcher \
  --source-reference documented-survey-note

fairmorph-engine show-relations --project ./survey.fairmorph --pipeline-sha256 PIPELINE_SHA256
```

The example IDs are placeholders: they must correspond to actual Entity IDs in a confirmed pipeline. To change a relation, use `replace-relation` or `retract-relation`, not manual deletion. Historical RUN snapshots preserve past assertion states.

Curated metadata is similarly versioned using `record-metadata` with explicit JSON attributes and field provenance; `show-metadata-snapshot` inspects current selections. The separate dataset-title revision workflow uses `stage-dataset-metadata`, `approve-dataset-metadata` and `show-dataset-metadata`. Staging and approval are intentionally separate; the UI cannot infer an approval from an edited field.

## 4. Interpret and troubleshoot a RUN

A `verified` status establishes the configured integrity checks: source identity, expected artifact hashes, source references and recorded configuration. It does **not** establish that the scientific interpretation is correct or authorized for publication.

If a project was interrupted, use [RUN recovery](RUN-RECOVERY.md); do not delete immutable source objects or completed RUNs. For an independently checked real-data example—including an explicit explanation of which work was generic Engine code versus dataset-specific test export code—see [CS-PHOC independent validation](https://github.com/FAIRmorph/fairmorph-validations/blob/main/docs/CS-PHOC-REPRODUCTION-AND-RESULTS.md).

The FAIRmorph Workbench is a separate application and is **not** a prerequisite for these CLI operations.
