# CS-PHOC engine PoC · implementation contract

**Scope:** The pinned CS-PHOC source transformation and the author's published
Darwin Core Event-core/Occurrence-extension export profile. This is a
*PoC-scoped* implementation of project, import, RUN, metadata and export manifests,
not a claim that all framework v0.12 draft contracts are production-final.

## CLI

The CLI emits newline-delimited JSON on stdout. Do not parse stderr as protocol events.
All paths are local. The Workbench needs **no file picker** and can supply a fixed
application-data project path.

```sh
fairmorph-engine handshake
fairmorph-engine poc --records 1000     # legacy IPC smoke test
fairmorph-engine csphoc --project ./CS-PHOC.fairmorph --events examples/cs-phoc/cs-phoc-events.csv --counts examples/cs-phoc/cs-phoc-counts.csv --decision examples/cs-phoc/decision.json
fairmorph-engine verify-project --project ./CS-PHOC.fairmorph
fairmorph-engine export-package --project ./CS-PHOC.fairmorph --run-id <RUN_ID>
fairmorph-engine dwca-preflight          # reports the published target profile
fairmorph-engine export-dwca --project ./CS-PHOC.fairmorph --run-id <RUN_ID>
```

`csphoc` imports two **explicitly selected, SHA-256 pinned** example CSV sources and an
explicitly user-approved transformation decision. Optional `--events`, `--counts`,
and `--decision` overrides are only suitable for controlled tests: any source
whose hash differs from the approved originals is refused before project creation.

## Persisted project structure

```text
CS-PHOC.fairmorph/
  project.json
  catalog/catalog.sqlite
  objects/sha256/<first-two-hex>/<full-sha256>
  imports/<role>-<sha256>/manifest.json
  packages/cs-phoc/virtual-descriptor.json
  packages/cs-phoc/publication-metadata.json
  configurations/<sha256>/transformation.json
  configurations/<sha256>/approval.json
  runs/<run-id>/manifest.json
  runs/<run-id>/inputs.snapshot.json
  runs/<run-id>/configuration.snapshot.json
  runs/<run-id>/outputs/observations.parquet
  runs/<run-id>/audit/lineage.parquet
  runs/<run-id>/audit/findings.parquet
  runs/<run-id>/reports/quality.json
  exports/<export-id>/export-manifest.json
  exports/<export-id>/package/datapackage.json
  exports/<export-id>/package/observations.csv
  exports/<export-id>/package/lineage.csv
  exports/<export-id>/package/quality.json
  # OR, for an independent Darwin Core Archive export:
  exports/<dwca-export-id>/export-manifest.json
  exports/<dwca-export-id>/package/event.txt
  exports/<dwca-export-id>/package/occurrence.txt
  exports/<dwca-export-id>/package/meta.xml
  exports/<dwca-export-id>/package/eml.xml
  exports/<dwca-export-id>/package/mapping-profile.json
  exports/<dwca-export-id>/package/cs-phoc-dwca.zip
```

Project root and SQLite catalog are mutable *indexes*; completed RUN manifest,
RUN artifacts, imports, stored input objects, and exports are immutable. Crashed
RUNs/exports stay under `.pending-*` with a `FAILED` marker. A new execution
produces a new run ID. `verify-project` checks the SHA-256 of persisted objects,
RUN artifacts and exports, plus the project and catalog RUN indexes.

## Scientific acceptance criteria

- `events`: **322** source rows.
- `counts`: **2,144** source rows.
- Long output: **16,940** rows from ten **approved** count columns.
- Explicit `0` cells: **11,599**, preserved as zero.
- Blank count cells: **4,500**, omitted rather than mapped to zero.
- Positive count cells: **5,341**.
- `total_count` must **not** be unpivoted.
- Record IDs and source-cell lineage depend on source hash, physical source
  record position, source column and transformation version; not on run ID.
- Any invalid cell, ambiguous event reference or row-count mismatch rejects
  completion. Diagnostic staging is retained for investigation.

## Contract and packaging boundary

The PoC JSON schemas in `contracts/` are mirrored into the wheel as
`fairmorph_engine/contracts/*.schema.json`. They cover the project, import,
virtual package, immutable input snapshot, immutable RUN, quality report,
and independent export manifest. Example data, mapping decisions and publication metadata are under `examples/cs-phoc/`, **not distributed inside the installed Engine**.

The `export-package` command creates a local, separately versioned Frictionless
Data Package. The `export-dwca` command creates an independent, SHA-256-indexed
Darwin Core Archive containing an Event core (536 rows), an Occurrence extension
(16,940 rows), `meta.xml` and `eml.xml`. Both exports leave the source RUN unchanged.

**Scientific mapping follows the original publishers**, not a new FAIRmorph
interpretation. This profile reproduces the source authors' eventID (`-1`/`-2`),
occurrenceID (`count_id` + age-code + sex-code), census locations, coordinates,
WoRMS `scientificNameID`s, `basisOfRecord=HumanObservation`, age/sex labels and
`occurrenceStatus` rule: zero count = `absent`, positive count = `present`, missing
source cell = no occurrence. The published `total_count` is checked against the
sum of categories but is not itself unpivoted.

**Reference snapshot:** the original transform and `data/dwca/{event,occurrence}.txt`
at `us-amlr/cs-phoc` commit `64f0b77e631c711c681306bbb56a7636ae91a471`.
The two reference Git blob IDs, DOI, publication publisher, citation and CC0 1.0
license are pinned in the package resource `publication-metadata.json`. This
resource is persisted in every project and its checksum is included in each RUN
input snapshot. Regression tests compare author-derived row fingerprints after
normalizing the original Event TSV's JSON-field quoting convention; this is a
content-comparability check, **not** a claim of matching archive bytes.

**EML provenance:** `eml.xml` is generated from verified published facts as
FAIRmorph derivative metadata. It is **not** the publisher's original IPT EML and
must not be presented as an independently published or endorsed CS-PHOC resource.
The original dataset DOI remains an `alternateIdentifier`; the derivative uses
its own export-specific metadata package ID. Export never contacts IPT/GBIF,
publishes a dataset, or mints a DOI.

The package is restricted to the fixed CS-PHOC PoC. It does not implement all
future general-purpose v0.12 entities, registries, metadata review workflows,
media processing or GeoPackage outputs.

## Validation

Run `python -m pytest tests` and `ruff check src tests && ruff format --check src tests`.
A real Parquet/Polars integration test is skipped if `polars` is unavailable.
The complete acceptance gate requires a CI runner with the declared Engine
dependencies and successful package assembly. The mocked lifecycle tests do **not**
validate Parquet bytes. Verify all generated ZIP members, dataset cardinalities,
Event/Occurrence associations, and export SHA-256 digests.
