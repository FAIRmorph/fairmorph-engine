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
