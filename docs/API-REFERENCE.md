# CLI and Python API Reference

**Scope:** Draft branch `refactor/framework-v012-foundation`. Python functions are implementation interfaces, **not yet a stable SemVer SDK**. Signatures and return structures may change before acceptance. The authoritative sources are `src/fairmorph_engine/` and the tests.

## 1. CLI contract

Installed executable: `fairmorph-engine` (Typer). Success and error events are written as **newline-delimited JSON (NDJSON)** to stdout. A `result` event contains `status` and, depending on the command, `data` or `message`. Handled failures exit with code 1; not every possible Python exception is guaranteed to become a structured event.

| Command | Arguments | Purpose |
| --- | --- | --- |
| `init-project` | `--project PATH`, optional `--name TEXT` | Initialize project directories and SQLite |
| `import-resource` | `--project PATH --source FILE --role ROLE` | Import unchanged bytes; return `resource_id` |
| `stage-csv-mapping` | `--project PATH --resource-id ID --profile FILE` | Validate profile and register draft mapping/fields |
| `approve-mapping` | `--project PATH --mapping-sha256 HASH --confirmed-by TEXT` | Explicitly approve mapping and field revisions |
| `run-mapping` | `--project PATH --mapping-sha256 HASH` | Execute approved mapping as RUN/2 |
| `export-package` | `--project PATH --run-id ID` | Export verified RUN as a Data Package |
| `verify-project` | `--project PATH` | Read-only integrity and index checks |
| `reconcile-runs` | `--project PATH` | Explicitly repair interrupted RUN publication |
| `handshake` | none | CLI/protocol capabilities |
| `poc` | `fairmorph-engine poc --help` | Separate legacy PoC command, not the generic RUN/2 workflow |

The publication adapters are Python APIs; `cli.py` does not expose a complete publication command family.

## 2. Project and import — `core.project`

- `initialize_project(project: Path, name: str = "FAIRmorph project") -> dict`: create directories and SQLite base schema; return project index.
- `import_resource(project: Path, source: Path, role: str) -> dict`: validate file/role, store SHA object, write import manifest, register source; result includes `resource_id`, `sha256`, `object_path` and `state`.
- `register_package(project: Path, package_id: str, resources: dict[str, dict]) -> dict`: register virtual package references without copying source bytes.
- `digest(path: Path) -> str`: file SHA-256.
- `write_json(path: Path, data: dict) -> None`: create a new JSON file; refuse overwrite.
- `connection(project: Path)`: SQLite connection with foreign keys enabled.
- `update_index(project: Path, object_entry=None, package_id=None) -> None`: replace `project.json` through a temporary file; not transactional with SQLite.

## 3. Versioned registry — `core.registry`

- `canonical_bytes(document: dict) -> bytes`: sorted, deterministic JSON encoding (not a formal RFC 8785 guarantee).
- `digest(document: dict) -> str`: SHA-256 of the canonical bytes.
- `define_field(project, resource_id, locator, definition, parent_revision_id=None) -> dict`: store an immutable schema-validated field revision.
- `review_field(project, revision_id, reviewer, decision) -> dict`: record `approved` or `rejected`.
- `register_mapping(project, mapping: dict) -> dict`: store a draft mapping version with revision bindings.
- `approve_mapping(project, mapping_sha256, reviewer) -> dict`: approve a valid mapping version.
- `mapping_snapshot(project, mapping_sha256) -> dict`: resolve source, field and mapping pins for execution.

## 4. External profiles — `core.profile`

- `stage_csv_mapping(project: Path, resource_id: str, profile_file: Path) -> dict`: validate the external CSV mapping profile, source columns and declared relationships; register drafts.
- `approve_staged_mapping(project: Path, mapping_sha256: str, reviewer: str) -> dict`: approve the staged field revisions and mapping in a SQLite transaction.

Relationship preflight checks resources, keys, declared cardinality and missing-key policy. Malformed CSV records (including too many or too few fields) are rejected.

## 5. Tabular transformations — `processing.tabular`

- `unpivot_csv(source: Path, *, identifier: str, columns: list[str], empty_cell_policy: str, zero_cell_policy: str)`: count-based wide-to-long conversion.
- `unpivot_typed_csv(source: Path, *, identifier: str, value_types: dict[str, str], missing_tokens: dict[str, list[str]] | None = None)`: typed wide-to-long conversion.

Both operate on explicitly declared columns; neither infers scientific semantics.

## 6. RUNs, exports and recovery

- `core.run_executor.execute_mapping_run(project: Path, mapping_sha256: str, emit=...) -> dict`: check approvals and sources; produce Parquet, lineage, quality report, snapshots and RUN/2 manifest.
- `core.run_executor.verify_mapping_run(project: Path, run_dir: Path, manifest: dict) -> None`: check RUN/2 mapping pins against approved registry revisions.
- `core.export.verified_run(project: Path, run_id: str) -> tuple[Path, dict]`: validate manifest, artifact bytes, paths and mapping pins.
- `core.export.export_data_package(project: Path, run_id: str, emit)`: export a verified RUN to a CSV Data Package and manifest.
- `core.export.verify_project(project: Path) -> dict`: validate sources, imports, packages, indexed RUNs, SQLite references and exports; includes `completed_runs`, `exports`, `status`.
- `core.run_recovery.reconcile_runs(project: Path) -> dict`: validate completed RUN directories and repair missing SQLite/JSON index entries; includes `recovered`, `pending`, `status`. **Never run concurrently with writers.**

## 7. Local schema registry — `core.schema_registry`

- `register_schema(project, *, schema_id, schema_version, kind, schema, status="draft", reviewer=None) -> dict`: validate Draft 2020-12, reject remote references and persist immutable content under SHA-256. Kinds: `core`, `source`, `export`, `extension`.
- `get_schema(project, *, schema_id, schema_version) -> tuple[dict, str]`: load only an exact version and verify its content pin.

## 8. Publication APIs

These functions consume **explicit external** profiles and metadata; they do not infer Darwin Core semantics.

| Function | Parameters and responsibility |
| --- | --- |
| `publication.validate_publication_intent` | `(project, run_id, profile_file, metadata_file) -> dict`; validate intent, metadata, format and RUN pin |
| `publication_projection.validate_publication_projection` | `(project, run_id, plan_file) -> dict`; verify pinned Parquet columns/types |
| `publication_bindings.validate_publication_binding_columns` | `(project, run_id, profile_file, metadata_file, projection_file) -> dict`; verify declared DwC source columns |
| `publication_integrity.validate_publication_integrity` | `(project, run_id, profile_file, metadata_file, projection_file, integrity_file) -> dict`; verify identifiers/relationships |
| `publication_materialize.materialize_publication_tables` | `(project, run_id, profile_file, metadata_file, projection_file, integrity_file, destination) -> dict`; write sorted CSV tables and manifest |
| `publication_adapters.export_eml` | `(project, run_id, profile_file, metadata_file, schema_file, destination) -> dict`; compile EML and validate against local XSD |
| `publication_adapters.export_dwca` | `(project, run_id, profile_file, metadata_file, projection_file, integrity_file, destination) -> dict`; create Darwin Core Archive |
| `publication_adapters.validate_dwca_archive` | `(archive, schema_file=DWCA_META_XSD) -> dict`; validate DwC-A ZIP and `meta.xml` |
| `eml_compiler.compile_eml_xml` | `(meta: ProjectMetadata, publication_date: str | None = None)`; compile EML XML |

A preflight or materialization result with `publication_ready: false` is not a final publication approval.

## 9. Error handling

Typical errors include `ValueError` (invalid profiles, unapproved mappings, integrity failures), `OSError` (filesystem), SQLite exceptions, JSON Schema `ValidationError` and missing optional processing dependencies. Integrations should inspect `result` events, avoid manual edits to RUNs, and use recovery only after stopping writers.
