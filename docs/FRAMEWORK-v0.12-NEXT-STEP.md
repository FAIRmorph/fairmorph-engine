# FAIRmorph Framework v0.12: Field Semantics and Mapping Foundation

## Scope

This step establishes the **dataset-independent semantic review and schema
registry foundation**. It extends the generic project/import foundation of
PR #10. It does **not** yet replace the CS-PHOC pipeline or claim completion
of the framework-v0.12 architecture.

## New components

- `core/registry.py`: immutable field-definition revisions validated against
  the original v0.12 `SourceFieldDefinition.schema.json`; append-only reviews;
  mapping versions and their approved field-revision bindings; reproducible
  mapping snapshots with source-definition and contract hashes.
- `core/schema_registry.py`: local immutable schema versions, canonical
  SHA-256 and disallowance of unreviewed remote JSON Schema references.
- `processing/tabular.py`: dataset-neutral audited wide-to-long primitive
  with explicit `omit`-empty and `preserve`-zero policies. Numeric conversion
  errors are never silently substituted with zeros.
- `tests/`: regression coverage for unresolved imports, semantic approval
  gates, mapping content immutability, schema tampering, separate source-field
  identities, and the real 16,940-row CS-PHOC input.

## Important boundaries

- Review decisions require an explicit reviewer. Technical import remains
  possible without semantic approval.
- `mapping_snapshot()` is currently an **API building block**. The existing
  CS-PHOC `run_slice` is not yet wired to consume this mapping snapshot.
- Existing completed RUNs and their manifests remain unchanged. The next
  integration step must upgrade the generic RUN contract without invalidating
  prior CS-PHOC RUNs.
- The source-field schema is copied verbatim from technical framework v0.12.
  Its draft status is retained; this commit does not make it production-final.
- Canonical JSON bytes are defined for this PoC, not falsely advertised as
  RFC 8785 JSON Canonicalization Scheme.
- CSV is used for source-cell parsing/lineage in this primitive. A Polars-based
  run executor and Frictionless Table Schema integration are **still pending**.
- The existing DwC-A profile remains unchanged; only a future approved
  migration may connect the export to a generic RUN output.

## Acceptance gates

1. Existing CI on Linux/Windows remains green.
2. New tests pass with the actual `core/project.py` in PR #10 (not a test shim).
3. Ruff check and format pass on all added Python modules.
4. Running the generic primitive against `examples/cs-phoc/cs-phoc-counts.csv`
   gives 16,940 long rows, 11,599 explicit zeroes, total 79,232.
5. Draft mapping cannot create a RUN snapshot; only a reviewed mapping and
   reviewed source field revisions can do so.
6. No regression of author-defined DwC-A reference fingerprints.
