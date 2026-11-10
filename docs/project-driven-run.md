# Project-driven RUN entry point (v0.12 P0.1 foundation)

The FAIRmorph project descriptor, not a caller-supplied `--config` path,
selects the executable approved mapping revision.

```sh
fairmorph-engine select-mapping --project ./survey.fairmorph --mapping-sha256 <approved-sha256>
fairmorph-engine run-pipeline --project ./survey.fairmorph
fairmorph-engine verify-project --project ./survey.fairmorph
```

The mapping must already have been reviewed and approved through the registry
workflow. Selection is explicit, SHA-256-pinned and stored as
`project.json.active_mapping_sha256`. No mapping is inferred from the number
of catalog entries or their creation order. Omitting `--project` uses the
current directory.

The public entry point reuses the existing immutable RUN/2 mapping executor,
including input and configuration snapshots, audit Parquet, manifest checksums
and RUN publication. It does **not** load arbitrary Python code or accept a
second external runtime configuration.

**Important scope boundary:** This is the first project-to-RUN integration
slice, not full vertical v0.12 acceptance. The generic multi-resource
`fairmorph.pipeline/1` operator DAG is not yet wired to the RUN/2 publisher;
Event/Occurrence RUN materialization, EML/DwC-A and real CS-PHOC and
independent synthetic end-to-end verification remain separate open work.
The CLI name `run-pipeline` currently executes the project-selected approved
mapping operation, not the complete generic DAG.

Data Package descriptors are deliberately unchanged: the framework requires
`datapackage.json` to remain standards-compliant and independent of
FAIRmorph-specific runtime configuration. Virtual packages are not portable
Data Packages until explicitly materialized.
