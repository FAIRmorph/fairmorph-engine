# Project-driven RUN/2 execution (v0.12 P0.1)

The project, not an external runtime `--config`, selects its active execution
revision. Data Package descriptors remain standards-compliant and data-only.

## Generic declarative DAG

Register a declarative JSON definition **once**:

```sh
fairmorph-engine register-pipeline --project ./survey.fairmorph --definition ./pipeline.json
fairmorph-engine select-pipeline --project ./survey.fairmorph --pipeline-sha256 <returned-sha256>
fairmorph-engine run-pipeline --project ./survey.fairmorph
fairmorph-engine verify-project --project ./survey.fairmorph
```

The registered configuration is stored at
`configurations/pipelines/<sha256>.json`, with its SHA-256 pinned by
`project.json.active_pipeline_sha256`. No pipeline is inferred from catalog
ordering. The definition uses the existing `fairmorph.pipeline/1` operator
DAG schema plus explicit input resource bindings and output names:

```json
{
  "schema_version": "fairmorph.pipeline/1",
  "resources": {
    "survey": {"resource_id": "<imported-resource-id>", "format": "csv"}
  },
  "steps": [
    {"id": "select", "operator": "table.select/1", "inputs": ["survey"],
     "output": "result", "parameters": {"columns": ["event", "count"]}}
  ],
  "outputs": ["result"]
}
```

Only imported, checksum-verified CSV and Parquet objects are accepted. The
allowlisted DAG runs without user Python. Published RUN/2 artifacts include
named Parquet outputs, configuration and input snapshots, a DAG execution
audit, quality metrics and SHA-256 checksums. `verify-project` rechecks
these against the project catalog and the pinned configuration.

## Legacy reviewed mapping path

```sh
fairmorph-engine select-mapping --project ./survey.fairmorph --mapping-sha256 <approved-sha256>
fairmorph-engine run-pipeline --project ./survey.fairmorph
```

Selecting one mode clears the other active selection. Mapping execution
continues to use the existing RUN/2 mapping publisher.

## Scope

P0.1 covers a single project-driven entry point, generic DAG execution and
verifiable RUN/2 publication. DAG audit metadata records source bindings,
operators and output tables, **not yet record-level Event/Occurrence lineage**.
Generic Event/Occurrence materialization, publication validation and the two
vertical E2E datasets remain separate acceptance steps. The generic RUN
outputs are not yet supported by the legacy `export-package` adapter, which
expects mapping-specific `observations.parquet` and `lineage.parquet`.

## P0.2: Reviewed semantic entity projections

A Workbench can write the `entities` member into the same content-addressed
pipeline definition. It must explicitly describe the source table, user
meaning and every source-to-target field mapping for **Observation, Event and
Occurrence**. For example:

```json
"entities": {
  "Observation": {
    "source_table": "observations",
    "description": "User-confirmed observation row and event semantics.",
    "fields": {"observationID": "observation_key", "eventID": "event_key"}
  },
  "Event": {
    "source_table": "events",
    "description": "User-confirmed sampling event semantics.",
    "fields": {"eventID": "event_key"}
  },
  "Occurrence": {
    "source_table": "occurrences",
    "description": "User-confirmed occurrence and event semantics.",
    "fields": {"occurrenceID": "occurrence_key", "eventID": "event_key"}
  }
}
```

After registration, the responsible user must explicitly confirm the
content-addressed projection **before** selecting it. No second person or
four-eyes review is required:

```sh
fairmorph-engine approve-projection --project ./survey.fairmorph --pipeline-sha256 <sha> --reviewer <reviewer>
fairmorph-engine select-pipeline --project ./survey.fairmorph --pipeline-sha256 <sha>
fairmorph-engine run-pipeline --project ./survey.fairmorph
```

The approval record is retained under `configurations/approvals/`. The RUN/2
input snapshot records the reviewer, timestamp and pinned configuration SHA.
The Engine never infers taxonomy, occurrence status or aggregation semantics.
It enforces unique, non-null entity identifiers and checks declared Event and
Observation foreign keys. Duplicate Event rows must be resolved explicitly
by the declarative DAG (for example with `table.distinct/1`); the Engine does
not silently deduplicate them. Zero values remain unchanged, and missing
values remain null when present in the mapped source.

This projection contract is a v0.12 PoC integration, **not** a substitute for
the complete SourceFieldDefinition revision/review workflow. A future
Workbench must bind its approved field revisions to the semantic projection
before production acceptance. Record-level lineage remains P0.3.
