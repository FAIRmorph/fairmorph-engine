# Framework v0.12 – external CSV mapping profile and explicit review

**Scope:** This increment connects the previously introduced generic project,
import, field-definition registry and RUN executor through public CLI operations.
It does **not** replace the old `csphoc` command or implement a generic DwC-A
adapter. PR #10 remains a Draft until that migration and the single-contract
consolidation are complete.

## Design decisions

1. The Engine source code contains no CS-PHOC field names, reference digests,
   taxonomic decisions, age classes, sex classes or fixed row counts.
2. An external, versioned JSON profile declares the source object SHA-256,
   source columns, explicit zero/missing policies, scientific labels and optional
   testable acceptance metrics. The full profile file hash is retained inside
   the mapping revision.
3. `stage-csv-mapping` validates the source against its imported immutable
   object and creates **draft** field-definition revisions plus one draft mapping.
   It never infers scientific meaning or automatically approves a profile.
4. `approve-mapping` requires an explicit reviewer identity, verifies that
   all field definitions are current and complete, and writes the ten field
   reviews and one mapping review in a **single SQLite transaction**.
5. `run-mapping` executes only approved mapping revisions and verifies optional,
   explicitly reviewed `output_rows`, `explicit_zeros` and `value_sum` acceptance
   values **before** publishing any completed RUN.
6. The original CSV bytes remain in `objects/sha256/`, never edited as part of
   mapping or transformation. New RUN artifacts and lineage remain separate.

## Example commands (run from repository root)

```shell
fairmorph-engine init-project --project ./CS-PHOC.fairmorph
fairmorph-engine import-resource --project ./CS-PHOC.fairmorph \
  --source examples/cs-phoc/cs-phoc-counts.csv --role counts
# Copy `resource_id` from the NDJSON result:
fairmorph-engine stage-csv-mapping --project ./CS-PHOC.fairmorph \
  --resource-id <RESOURCE_ID> --profile examples/cs-phoc/mapping-profile.json
# Scientific reviewer confirms the exact mapping and recorded source semantics:
fairmorph-engine approve-mapping --project ./CS-PHOC.fairmorph \
  --mapping-sha256 <MAPPING_SHA256> --reviewer <REVIEWER_ID>
fairmorph-engine run-mapping --project ./CS-PHOC.fairmorph \
  --mapping-sha256 <MAPPING_SHA256>
```

The sample mapping is data, not an Engine default. In particular, the `CS-PHOC`
profile is not automatically approved merely because it is included under
`examples/`. Its reference numbers must be independently verified by tests.

## Scientific acceptance

The external profile pins:

- Original counts CSV SHA-256: `be4a28aa5036dea103e9e6bbc6af5fef13d80354ef2750e0960bf78e320c3545`
- 10 explicitly described count fields
- 16,940 output rows (4,500 omitted blank cells)
- 11,599 explicitly preserved zeros
- 79,232 aggregate observed individuals

Age/sex categories are declarative `attributes` on the corresponding mapping
bindings. They are versioned and hash-pinned; a later DwC-A adapter must **read
these bindings** and must not re-create a private copy of the mapping semantics.

## Constraints and known incomplete work

- The `csphoc` command and its current specialised RUN/1 path are **not yet
  redirected** to this generic executor. No old RUN migration is required, but
  the temporary RUN/1 and RUN/2 contracts must still be consolidated together.
- Only the `counts` resource is pinned by this RUN. The `events` resource,
  publication-metadata revision and relevant join semantics must be included
  in the final CS-PHOC RUN snapshot before producing an Event/Occurrence DwC-A.
- Real Parquet integration and the full existing suite must be verified in
  Linux/Windows CI on the **actual PR #10 checkout**. This review package was
  tested in a reconstructed local harness because a direct GitHub checkout was
  not available in this environment.
- Source parsing is CSV-only; a Frictionless/Table Schema validation adapter
  and import recovery/reconciliation remain future work.
- Profile review does not assert that a provided profile is scientifically
  correct. Explicit reviewer responsibility is preserved.


## Configurable inter-resource integrity

A mapping profile may declare `auxiliary_resource_ids` and `relationships`. Each
relationship names two imported resources, their CSV key columns, and an explicit
cardinality (`one-to-one`, `one-to-many`, `many-to-one`, or `many-to-many`).

Two optional policies are evaluated from the external JSON profile:

- `require_match`: `true` (default) rejects left-side keys not found on the
  right; `false` allows unmatched left-side keys.
- `missing_key_policy`: `"reject"` (default) rejects empty/missing keys on
  either side; `"ignore"` excludes such keys from matching and uniqueness
  checks.

These are technical validation rules, not inferred scientific meanings. Key
comparison is exact text comparison without coercion. Relationship declarations
and their policies are reviewer-approved and SHA-256-pinned in the RUN input
snapshot. No implicit join is performed. Existing profiles without these optional
properties retain the prior strict behavior.

## Project-defined counting units

The currently supported `wide-to-long-counts/1` operation processes
non-negative integer quantities. The scientific counting unit is supplied by
each externally reviewed field definition (`counting_unit`) and may describe
individuals, sampling events, or other counted entities. The Engine checks that
a unit is explicitly defined, but does not prescribe `individual` or infer
units from target field names. Changing a unit requires a new versioned mapping
and reviewer approval.

This does **not** yet provide a generic decimal-measurement or categorical
observation transformer; those require separately versioned safe operations.

## Typed observations (experimental)

The additional reviewed operation `wide-to-long-values/1` supports
`value_type` declarations on each mapped field: `integer`, `decimal`,
or `text`. It does not require `counting_unit`. Decimal values use exact
decimal parsing (no binary floating-point conversion); non-finite values are
rejected. The output stores the canonical textual value and its explicit
`value_type`, allowing mixed measurement and categorical columns in a
single Parquet table. Empty cells are omitted; nonempty text is preserved.
No scientific categories, units, ranges or sign restrictions are inferred.

For typed mappings, the currently supported acceptance criterion is
`output_rows`. The legacy count operation and its numeric quality metrics
remain unchanged. The typed operation is an additive versioned contract,
not a silent reinterpretation of previously approved count mappings.

### PoC scope: explicit missing tokens

For `wide-to-long-values/1`, each field's reviewed `missing_values`
tokens are pinned in the mapping and omitted during transformation, just like
empty cells. The Engine compares literal tokens; it does not guess aliases,
normalize categories, or interpret the token's scientific meaning. This is a
minimal vertical-slice demonstration, not a production missing-data model.
The legacy count operation is unchanged.

## PoC acceptance: real reference-data vertical slice

`examples/cs-phoc/tests/test_reference_workflow.py` runs the **generic** CLI workflow
against the repository's CS-PHOC count and event CSV files. The test imports
both immutable resources, extends the external reference profile with an
explicit `many-to-one` event relationship, stages and approves the exact
mapping, executes RUN/2, checks the configured 16,940 observation rows,
exports a generic Frictionless Data Package, and verifies the project.

The test's reviewer identity is a simulated acceptance-test actor, **not**
an independent scientific sign-off. The reference profile's scientific
correctness and any production publication mapping remain outside the
technical test's claims. This is a PoC vertical slice, not a production
DwC-A implementation or migration of the legacy CS-PHOC command.

### v0.12 test ownership boundary

- `tests/`: Engine-owned synthetic unit/integration tests; no reference-project
  data or scientific acceptance numbers.
- `examples/cs-phoc/tests/`: Project-owned reference-data acceptance test,
  independently runnable with
  `python -m pytest examples/cs-phoc/tests/test_reference_workflow.py`.
- The Engine repository has no project-specific CI workflow. Project-owned
  acceptance checks run separately against concrete project RUN artifacts.

The reference project is an interchangeable consumer of the Engine. Its test
must not become a dependency of the Engine's generic test suite.

### Project RUN acceptance boundary

The Engine CI must remain runnable when `examples/` is absent. A project
acceptance test is not a second Engine workflow: it reads the project's
actual, immutable RUN inputs and outputs and validates them against
project-owned, reviewer-approved expectations. This includes the input
snapshot and, when produced by a supported adapter, EML and DwC-A artifacts.
The generic Frictionless Data Package export is **not** an EML or DwC-A
export, and successful package verification must not be presented as proof
of either publication format. Project-specific expected scientific values
and metadata belong outside `src/` and `tests/`.

### Export architecture gap before v0.12 acceptance

The current `export-dwca` implementation is a **legacy CS-PHOC-specific**
publication path. It contains fixed source hashes, reference counts and
publication semantics and must not be represented as the generic RUN/2
publication adapter. The generic `export-package` command currently exports
observations, lineage and quality as a Frictionless Data Package; it does not
produce EML or DwC-A.

Before claiming dataset-independent EML/DwC-A support, define an external,
versioned, reviewed publication profile and a generic adapter that consumes
the RUN/2 snapshot and its pinned metadata. Project-specific acceptance
tests must inspect the resulting EML and DwC-A artifacts from a concrete
project RUN. No CS-PHOC identifiers, expected counts or publication decisions
may be embedded in the generic adapter or Engine CI.

### Publication intent contract (design increment, not an exporter)

`contracts/publication-profile.schema.json` defines a dataset-independent
external publication **intent** with exact RUN-manifest and metadata SHA-256
references, requested EML/DwC-A format versions and explicit Darwin Core row-type identifiers. `tests/test_publication_profile_contract.py` exercises
the contract with synthetic identifiers; no `examples/` data is required.

This initial contract is deliberately not wired into `run-mapping`,
`export-package` or `export-dwca`. It does not authorize an export,
implement reviewer approval, pin a full metadata revision in RUN/2, or define
the complete column-to-Darwin-Core and EML metadata mappings. Those are
required before a generic publication adapter can be implemented or claimed
to produce valid scientific publications. The existing specialized DwC-A
command remains legacy and must not be used as evidence of generic support.

### Publication preflight (RUN/2, no publication side effects)

`core.publication.validate_publication_intent(project, run_id, profile_file,
metadata_file)` validates the external publication contract and verifies
the immutable generic RUN via `verified_run`. It compares the exact
RUN-manifest and metadata-file SHA-256 values with the external intent.
The function returns `publication_ready: false` by design: the metadata
has not yet been versioned into the RUN/2 snapshot or scientifically
reviewed, and no EML/DwC-A adapter is invoked. It is not a CLI publication
command or an approval mechanism. The tests use synthetic data only.

### Explicit Darwin Core bindings

When `dwca/1` is requested, the external publication profile now requires
`dwca.core`, `dwca.core_id_field` and `dwca.core_fields`; optional
`dwca.extensions` declare their own row type, identifier and bindings.
Each binding declares
a source-field name and an explicit Darwin Core term URI. The generic
preflight rejects duplicate source fields, duplicate target terms and
identifier mappings inconsistent with the declared Event or Occurrence
row type. Neither core type nor any extension is chosen by the Engine. This is structural validation only: it does
not establish that the named fields exist in a future Event/Occurrence
projection, nor does it constitute a scientific approval or DwC-A export.

### Publication preflight result boundary

The publication preflight returns `field_bindings_verified: false` and
`publication_ready: false`, even when the external profile and the RUN and
metadata SHA-256 pins validate. The current generic RUN/2 observations are
long-form mapping results, not necessarily Event or Occurrence publication
tables. Consequently, no source-field existence, table projection,
inter-table relationship, EML schema or DwC-A archive conformance is
asserted. Such checks require explicit, externally configured projections
and validation of their concrete artifacts; no project-specific
projection defaults may be added to Engine core.

### External publication projection plan (contract only)

`publication-projection.schema.json` defines an optional, external,
dataset-neutral plan referencing the SHA-256 of a RUN/2 manifest and
explicit output Parquet artifact paths, row types and expected columns.
It does not infer Event or Occurrence records from the Engine's
long-form observations. The contract is not yet wired to the publication
preflight: no artifact existence, column availability, projection
execution, relationship integrity or publication readiness is asserted.
A subsequent generic validator must compare the declared plan with
the verified RUN artifacts before a publication adapter can use it.
