# Framework v0.12: dataset-independent foundation

The engine is an application, not a scientific data repository. Runtime project
directories are created by `init-project`. Original sources enter through
`import-resource` without assigning scientific semantics, with SHA-256
object deduplication and the `imported_unmapped` state in SQLite.

`examples/cs-phoc/` is an external reference example. Its sources, approved
mapping and publication metadata are not installed as engine fixtures. The
CS-PHOC CLI explicitly receives source and decision paths. A RUN freezes the
publication metadata revision, and the export verifies the frozen revision.

The changes establish a project/import/package foundation, **not full
framework v0.12 compliance**. A generalized versioned schema registry,
declarative mapping executor, full metadata revision and review machinery,
backup/restore and persistent request-response protocol are still missing.
CS-PHOC-specific mapping logic must eventually become a separate profile
adapter. The original author-defined DwC-A regression remains authoritative.
