# CLI and Python API Reference

**Scope:** Technical framework **v0.13 vertical PoC** (P0.1–P0.5). Python implementation APIs are **not** a stable SemVer SDK, and this is not a complete v0.12 product. Before framework document version 1.0 there is **no backward-compatibility obligation** for experimental PoC contracts; changes must be **forward-consistent** across schema, code, tests and docs. Current implementation authority is `src/fairmorph_engine/` and its tests. See [v0.13 policy](FRAMEWORK-v0.13-POC-SCOPE.md).

## 1. CLI contract

Installed executable: `fairmorph-engine` (Typer). Success and error events are written as **newline-delimited JSON (NDJSON)** to stdout. A `result` event contains `status` and, depending on the command, `data` or `message`. Handled failures exit with code 1; not every possible Python exception is guaranteed to become a structured event.

| Command | Arguments | Purpose |
| --- | --- | --- |
| `init-project` | `--project PATH`, optional `--name TEXT` | Initialize project directories and SQLite |
| `import-resource` | `--project PATH --source FILE --role ROLE` | Import unchanged bytes; return `resource_id` |
| `stage-csv-mapping` | `--project PATH --resource-id ID --profile FILE` | Validate profile and register draft mapping/fields |
| `approve-mapping` | `--project PATH --mapping-sha256 HASH --confirmed-by TEXT` | Explicitly approve mapping and field revisions |
| `run-mapping` | `--project PATH --mapping-sha256 HASH` | Execute approved mapping as RUN/2 |
| `register-pipeline` | `--project PATH --definition FILE` | Register a versioned declarative DAG and optional entity mappings |
| `confirm-projection` | `--project PATH --pipeline-sha256 HASH --confirmed-by USER` | Confirm exact field-revision pins and entity projection as the responsible user |
| `assert-relation` | `--project PATH --pipeline-sha256 HASH --predicate NAME --subject-id ID --object-id ID --confirmed-by USER --source-reference TEXT` | Register a user-confirmed append-only typed relation |
| `replace-relation` | `--project PATH --pipeline-sha256 HASH --relation-id ID --object-id ID --confirmed-by USER --source-reference TEXT` | Replace the target via a new assertion |
| `retract-relation` | `--project PATH --pipeline-sha256 HASH --relation-id ID --confirmed-by USER --source-reference TEXT` | Revoke current relation without erasing history |
| `show-relations` | `--project PATH --pipeline-sha256 HASH` | Inspect current confirmed relation snapshot and profile pins |
| `install-profile-contracts` | `--project PATH --confirmed-by USER` | Explicitly approve/install eight local v0.12 domain schemas and the metadata envelope |
| `profile-bindings` | `--project PATH --entities SamplingEvent,MeasurementOrFact` | Return verified schema ID, SemVer and SHA pins to put in a pipeline |
| `record-metadata` | `--project PATH --pipeline-sha256 HASH --entity-type KIND --entity-id ID --attributes FILE --provenance FILE --source SOURCE --confirmed-by USER [--parent-revision-id ID]` | Append a reviewed domain metadata envelope revision |
| `show-metadata-snapshot` | `--project PATH --pipeline-sha256 HASH` | Inspect active pinned metadata revisions |
| `select-pipeline` | `--project PATH --pipeline-sha256 HASH` | Select a confirmed project DAG revision |
| `run-pipeline` | `--project PATH` | Run the selected mapping/DAG and publish RUN/2 |
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
- `review_field(project, revision_id, reviewer, decision) -> dict`: record `approved` or `rejected` by the confirming user; no separate reviewer is required.
- `register_mapping(project, mapping: dict) -> dict`: store a draft mapping version with revision bindings.
- `approve_mapping(project, mapping_sha256, reviewer) -> dict`: approve a valid mapping version.
- `mapping_snapshot(project, mapping_sha256) -> dict`: resolve source, field and mapping pins for execution.

## 4. External profiles — `core.profile`

- `stage_csv_mapping(project: Path, resource_id: str, profile_file: Path) -> dict`: validate the external CSV mapping profile, source columns and declared relationships; register drafts.
- `approve_staged_mapping(project: Path, mapping_sha256: str, reviewer: str) -> dict`: confirm the staged field revisions and mapping in a SQLite transaction (parameter is the confirming user).

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

## 7. P0.2 semantic entity projection

- `core.pipeline_run.register_pipeline(project, config) -> dict`: store SHA-256-pinned declarative DAG (and optional `entities`).
- `core.entity_projection.confirm_projection(project, sha, confirmed_by) -> dict`: validate the exact `SourceFieldDefinition` revisions and field provenance, then store one revision-bound user confirmation in SQLite.
- `core.entity_projection.require_confirmation(project, sha) -> dict`: retrieve and validate the pinned confirmation/evidence.
- `core.project_execution.select_project_pipeline(project, pipeline_sha256)`: select only a confirmed semantic projection when `entities` are present.
- `core.pipeline_run.execute_pipeline_run(project, sha, emit=...)`: produce RUN/2 materialized `SamplingEvent`, optional `Occurrence` and `MeasurementOrFact`, snapshots and checksums.

This is a v0.12 **vertical PoC**, not a complete production schema or publication adapter. The `--confirmed-by` argument is a user identity, not a four-eyes or external-review requirement. See `docs/project-driven-run.md` and `docs/P0.2-CHECKPOINT.md`.

## 8. P0.3 sparse change audit for generic DAG RUN/2

- `core.pipeline.execute_pipeline(config, resources, on_step=...)`: optionally report each executed operator with input/output frames to an observer; does not change the registered DAG contract.
- `core.change_audit.ChangeAudit`: collect per-step row counts and differences of directly comparable `table.derive/1` values without materializing a source-cell table.
- `core.pipeline_run.execute_pipeline_run`: always write the checksummed `audit/pipeline.json` with `step_audit`; write `audit/value_changes.parquet` **only when actual differences occur**.
- `core.pipeline_run.verify_pipeline_run`: reconstruct the pinned source/DAG outputs, step counts and optional change events; reject modified data or audit entries, including after a forged audit file hash.

For combined/constant derived values without a single comparison baseline, `fields_without_direct_value_comparison` records the exceptional field in `audit/pipeline.json`. Normal field provenance remains deterministic via source hashes, field revisions and the saved declarative rule. This is **not** a guarantee of full per-cell auditability; see `docs/P0.3-CHECKPOINT.md`.

The original profile-mapping RUN/2 path (`core.run_executor`) continues to use its own established lineage artifacts for the CS-PHOC reference demonstration. The sparse audit is the **generic DAG** P0.3 contract; harmonizing both paths is a separate planned task.

## 9. P0.4 versioned domain relations

- `core.relation_assertions.relation_profile() -> dict`: load the installed, versioned `fairmorph.ecology.core/0.12-poc.1` predicate contract and content hash.
- `assert_relation(project, pipeline_sha256, predicate, subject_entity_id, object_entity_id, confirmed_by, source_reference, *, source_kind="user_confirmed", valid_from=None, valid_to=None) -> dict`: append one user-confirmed typed relation.
- `replace_relation(project, pipeline_sha256, relation_id, new_object_entity_id, confirmed_by, source_reference, *, source_kind="user_confirmed") -> dict`: append an assertion that supersedes the current assertion; the predicate and subject remain stable.
- `retract_relation(project, pipeline_sha256, relation_id, confirmed_by, source_reference) -> dict`: append a revocation and remove the active pointer.
- `relation_snapshot(project, pipeline_sha256, *, through_sequence=None, entity_frames=None) -> dict`: return a canonical, hash-pinned active assertion set as of the selected log sequence. The default is the current state.

SQLite stores the append-only assertion log and a transactionally maintained current projection. `execute_pipeline_run` embeds the relation snapshot in `inputs.snapshot.json`; `verify_pipeline_run` reconstructs the **historical** assertion state even after subsequent corrections. Only the declared entity kinds/predicates are supported in the vertical PoC; there is no mandatory reviewer separate from the user who confirms the relation. See `docs/P0.4-CHECKPOINT.md`.

## 10. P0.5 domain-profile selection and metadata revisions

- `core.domain_profiles.profile_bundle() -> dict`: resolve the installed offline JSON Schema Draft 2020-12 contracts from the framework v0.12 schema bundle.
- `install_builtin_profiles(project, confirmed_by) -> dict`: explicitly approve/install eight v0.8 ecological domain schemas and the v0.8 metadata-envelope contract into the existing project schema registry.
- `profile_bindings_for(project, entity_types) -> dict`: return a complete, explicitly pinned `profile_bindings` configuration fragment for previously approved schema versions.
- `resolve_profiles(project, config) -> dict`: verify exact schema ID, version, SHA-256 and approval state; no automatic `latest` resolution or remote schema fetch.
- `validate_entity_profiles(resolved, entity_frames)`: validate published P0.2 entity rows against the selected domain profile, separately from technical IDs and relation references.
- `core.metadata_revisions.register_metadata_revision(project, pipeline_sha256, *, entity_type, entity_id, attributes, field_provenance, source, confirmed_by, parent_revision_id=None) -> dict`: append a single approved, validated metadata envelope for a real projected entity.
- `metadata_snapshot(project, pipeline_sha256, *, through_sequence=None, entity_frames=None) -> dict`: resolve current or historically pinned metadata revision references and schema hashes.

**P0.5 contract:** An Entity pipeline **must** have explicit approved `profile_bindings`; unprofiled old P0.2 configurations are rejected rather than upgraded. Technical imports and purely technical DAG processing need no domain profile. No preexisting user RUNs require migration. `RUN/2` freezes the selected schema versions plus an optional set of explicitly curated metadata revisions. This does not duplicate all observations as SQLite rows. See `docs/P0.5-CHECKPOINT.md`.

## 11. Local schema registry — `core.schema_registry`

- `register_schema(project, *, schema_id, schema_version, kind, schema, status="draft", reviewer=None) -> dict`: validate Draft 2020-12, reject remote references and persist immutable content under SHA-256. Kinds: `core`, `source`, `export`, `extension`.
- `get_schema(project, *, schema_id, schema_version) -> tuple[dict, str]`: load only an exact version and verify its content pin.

## 12. Publication APIs

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

## 13. Error handling

Typical errors include `ValueError` (invalid profiles, unapproved mappings, integrity failures), `OSError` (filesystem), SQLite exceptions, JSON Schema `ValidationError` and missing optional processing dependencies. Integrations should inspect `result` events, avoid manual edits to RUNs, and use recovery only after stopping writers.
