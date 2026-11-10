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

## P0.2 – v0.12 semantic entity projection (vertical PoC)

This demonstrator uses the **final separation of concerns** from framework v0.12,
chapters 10, 13–15: immutable imported bytes, source-field definitions,
user-confirmed target mappings, a project-local SQLite registry and immutable
RUN/2 tabular outputs. It is **not** a complete production implementation.

### 1. Define and confirm physical source-field semantics

Before building a semantic projection, the application/Workbench registers
the relevant imported CSV or Parquet source columns through
`registry.define_field(project, resource_id, "csv:column", definition)`.
Each revision carries an immutable `revision_id`, `source_field_id`,
`source_resource_id` and content SHA-256. Relevant definitions must have
`semantic_status="defined"`, a substantive description and documented
value/missing semantics.

The responsible user explicitly confirms the revision using
`registry.review_field(project, revision_id, user_id, "approved")`.
Here `reviewer` in the underlying v0.12 registry means the **confirming user**:
no independent second person or four-eyes process is required. Technically
imported resources and unconfirmed drafts remain valid, but **cannot** be
used for the semantic projection.

### 2. Explicit binding to a supported entity profile

`entities` is an optional member of the content-addressed
`fairmorph.pipeline/1` configuration. Each selected profile declares
`source_table`, a substantive `description`, and a map of `fields`.
Every target field contains:

```json
{
  "column": "sampling_event_key",
  "description": "Stable technical event identity in this imported source.",
  "source_definitions": [
    {
      "source_resource_id": "<resource-id>",
      "source_field_id": "<source-field-id>",
      "definition_revision_id": "<definition-revision-id>",
      "definition_sha256": "<64-character-sha256>"
    }
  ]
}
```

The Engine checks field identity, revision/hash, confirmation, current definition
and column provenance against the declared DAG. No inferred scientific
semantics, guessing of column meaning, or automatic Occurrence creation occurs.

Supported **PoC projection profiles**:

| Profile | Required mapped fields | Optional examples |
|---|---|---|
| `SamplingEvent` | `entity_id`, `event_type` | `event_id`, `parent_event_ref`, time and method |
| `Occurrence` | `entity_id` | `sampling_event_ref`, taxon/evidence semantics |
| `MeasurementOrFact` | `entity_id`, `measurement_type`, `value` | `sampling_event_ref`, `occurrence_ref`, unit, `missing_reason` |

`entity_id` is a stable **technical** key. Domain identifiers such as
`event_id` and `occurrence_id` are optional, separate target fields.
Foreign-key projections use explicit technical references. This PoC validates
declared event/occurrence keys and cycle-free parent-event references in the
resulting tables; it does not yet implement the full append-only relations
assertion registry from v0.12 chapter 09.

`SamplingEvent` can be materialized **without** Occurrence, taxon,
coordinates, transect or dive. A count becomes a `MeasurementOrFact` or an
`Occurrence` only by explicit user mapping; a numerical zero is retained.
Missing measurement values require an explicit `missing_reason` in this PoC.

### 3. Confirm and execute

Once every mapped source definition has been confirmed and the exact pipeline
configuration has been registered:

```sh
fairmorph-engine register-pipeline --project ./survey.fairmorph --definition ./pipeline.json
fairmorph-engine confirm-projection --project ./survey.fairmorph --pipeline-sha256 <sha> --confirmed-by <user-id>
fairmorph-engine select-pipeline --project ./survey.fairmorph --pipeline-sha256 <sha>
fairmorph-engine run-pipeline --project ./survey.fairmorph
fairmorph-engine verify-project --project ./survey.fairmorph
```

The confirmation is stored once in the project SQLite table
`projection_confirmations`, keyed by immutable configuration SHA-256.
Its evidence snapshot includes all referenced SourceFieldDefinition documents,
confirming users, review timestamps, schema hash, exact source-column bindings
and evidence SHA-256. RUN/2 embeds this confirmation in
`inputs.snapshot.json` and checks its integrity when verifying the RUN.

`approve-mapping --confirmed-by` remains the separate CSV profile path from
P0.1; **neither command requires a second person**. A new semantic definition
or binding creates a new revision and must be confirmed before a new run.

### Boundary of P0.2

This PoC demonstrates an executable, event-centric data path and its versioned
decision evidence. It intentionally does **not** claim a production Workbench,
complete v0.12 envelope/profile JSON-Schema validation, every event profile,
full relation-assertion history, record-/cell-level provenance, generic
export adapters or DwC-A/EML conformance. See `docs/P0.2-CHECKPOINT.md`.
