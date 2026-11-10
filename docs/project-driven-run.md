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


## P0.3 – deklarative Herkunft und sparsames Änderungs-Audit

Die Quelle eines Feldes ergibt sich aus dem SHA-256-gepinnten Importobjekt,
der bestätigten SourceFieldDefinition-Revision und der expliziten
Mapping-/Transformationskonfiguration. Eine Wiederholung dieses Nachweises
**für jede unveränderte Zelle** wird nicht gespeichert.

Jeder generische DAG-RUN/2 enthält in `audit/pipeline.json` die versionierten
Regeln, Ressourcenbindungen, Ergebniskennzahlen, Eingangs-/Ausgangszeilenzahlen
pro Operator sowie `value_change_count`. Filter, Join, Distinct, Select und
Unpivot können anhand der gepinnten Eingaben und Operatoren reproduziert
werden, ohne eine zweite Tabelle aller Ursprungszellen zu speichern.

Wenn `table.derive/1` einen Wert gegenüber einer eindeutig vergleichbaren
Eingabespalte **tatsächlich verändert**, wird ausschließlich diese Abweichung
in `audit/value_changes.parquet` protokolliert: Regel, Tabellen-/Spaltenbezug,
lokaler Zeilenoffset, Datentyp sowie Vorher-/Nachher-Wert. Bei einem unveränderten
RUN fehlt diese Datei vollständig. `null` und numerische Null sind ausdrücklich
unterscheidbar. Für neue/zusammengesetzte Werte ohne einzelne Vergleichsbasis
zeigt `fields_without_direct_value_comparison` im Regelaudit an, dass allein
die deklarierte Regel den Ursprung beschreibt.

RUN/2 verankert die erzeugten Auditdateien mit SHA-256 und Dateigröße im
Manifest. `verify-project` verifiziert Ergebnisse, Mengenaudit und vorhandene
Wertänderungen erneut anhand der unveränderten Originalquellen und DAG-Regeln.
Der PoC verlangt keine unabhängige zweite bestätigende Person. Details und
Grenzen: [P0.3-Checkpoint](P0.3-CHECKPOINT.md).


## P0.4 – append-only fachliche Relationen und RUN-feste Historie

Eine bestätigte fachliche Beziehung wird separat von den Entitäts-Parquets als
versionierte SQLite-Assertion registriert, nicht als veränderliche Liste im
`SamplingEvent` oder `Occurrence`. Ein strikt versioniertes Profil
(`fairmorph.ecology.core/0.12-poc.1`) erlaubt im PoC die Prädikate
`parent_event`, `event_occurrence`, `event_measurement` und
`occurrence_measurement`. Aussagen müssen auf vorhandene technische
`entity_id`-Werte zeigen; Typen, 0..1-Kardinalitäten und zyklusfreie
Event-Hierarchien werden geprüft. Kein Transekt, GPS oder biologischer
Occurrence-Nachweis wird automatisch vorausgesetzt.

Nach einer bestätigten Entity-Projektion:

```sh
fairmorph-engine assert-relation --project ./survey.fairmorph \
  --pipeline-sha256 <sha> --predicate parent_event \
  --subject-id e2 --object-id e1 --confirmed-by researcher \
  --source-reference field-note-42

fairmorph-engine show-relations --project ./survey.fairmorph --pipeline-sha256 <sha>
fairmorph-engine run-pipeline --project ./survey.fairmorph
```

Korrekturen werden **nicht** durch UPDATE/DELETE einer Assertion umgesetzt.
`replace-relation` verknüpft eine neue Assertion mit der vorherigen
`assertion_id`, `retract-relation` widerruft eine aktuelle Beziehung, behält
aber das Ereignis im unveränderlichen Log. Alle Operationen erfordern die
Identität des bestätigenden Nutzers und eine Quellenreferenz; es besteht
**kein Vier-Augen-Zwang**.

Ein semantischer RUN/2 speichert `relations_snapshot` in
`inputs.snapshot.json`, einschließlich Relationsprofil-ID und -Hash,
`through_sequence`, aktiver Assertions und Snapshot-Hash. Die Verifikation
rekonstruiert den Zustand **zum eingefrorenen Log-Stand**. Spätere
Widerrufe/Ersetzungen verändern weder die gespeicherte Aussage noch die
Prüfbarkeit früherer RUNs.

Der PoC verwendet lediglich die bereits ausführbaren Entity-Typen
`SamplingEvent`, `Occurrence` und `MeasurementOrFact`. Medien-, Sample-,
Spatial-, Dive- und Transect-Profile sowie eine vollständige Relations-Workbench
sind spätere Arbeitspakete. Siehe [P0.4-Checkpoint](P0.4-CHECKPOINT.md).



## P0.5 – verpflichtende Schema-Pins für semantische Entity-RUNs

Technischer Import (`imported_unmapped`) und rein technische DAG-Verarbeitung
bleiben ohne fachliche Profile möglich. **Jede** Pipeline mit `entities`
benötigt dagegen explizite, vom verantwortlichen Benutzer freigegebene
`profile_bindings`. Ein unprofilierter P0.2-Entity-RUN ist nicht mehr zulässig;
es existieren keine Altläufe, für die eine Kompatibilitätsschicht nötig wäre.
Ein später erzeugter RUN friert seine Versions-/Hash-Pins dennoch für die
historische Verifikation ein.

Die mitgelieferten v0.12-Verträge (ökologische Schemas v0.8, JSON Schema
Draft 2020-12) werden bewusst installiert:

```sh
fairmorph-engine install-profile-contracts --project ./survey.fairmorph --confirmed-by researcher
fairmorph-engine profile-bindings --project ./survey.fairmorph --entities SamplingEvent,MeasurementOrFact
```

Das zweite Kommando gibt die exakt bestätigten `schema_id`,
`schema_version` und `schema_sha256` zurück. Diese werden als
`profile_bindings.envelope` und `profile_bindings.entities` in die
zu registrierende Pipeline übernommen. Die Profile `SamplingEvent`,
`Occurrence` und `MeasurementOrFact` werden bei RUN-Ausführung anhand ihrer
materialisierten Datenzeilen validiert. Die übrigen fünf Domänenprofile
sind installierbar und einzeln validierbar, aber keine Behauptung zusätzlicher
materialisierter Entitätspfade.

Optionale kuratierte Metadaten werden unabhängig von den Ergebnis-Parquets
im technischen `metadata-envelope` erfasst. Dieser dokumentiert etwa
`entity_id`, `entity_type`, Revisionsidentität, Einspielzeit,
`source`, `review_status`, `attributes` und die präzise
`field_provenance` unter JSON-Pointern (z. B.
`/attributes/event_type`). Die Freigabe ist eine eindeutige Nutzerhandlung,
ohne zwingenden zweiten Reviewer:

```sh
fairmorph-engine record-metadata --project ./survey.fairmorph \
  --pipeline-sha256 <sha> --entity-type SamplingEvent --entity-id e1 \
  --attributes attributes.json --provenance provenance.json \
  --source user_confirmed --confirmed-by researcher

fairmorph-engine show-metadata-snapshot --project ./survey.fairmorph --pipeline-sha256 <sha>
```

Nur explizit kuratierte und bestätigte Metadaten erhalten SQLite-Revisionen;
es entstehen keine Pflicht-Envelope-Zeilen für jede Datenzelle. Ein RUN
friert `profile_bindings` und die zum Lauf gültige `metadata_snapshot`
zusammen mit Feldfreigaben und P0.4-Relationen ein. Verifikation rekonstruiert
den historischen Stand aus unveränderlichen Revisionen, ohne neue
Profilversionen zur Interpretation alter RUNs heranzuziehen.
Siehe [P0.5-Checkpoint](P0.5-CHECKPOINT.md).
