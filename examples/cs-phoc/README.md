# CS-PHOC real-data reference publication test (manual)

This directory contains **example-specific configuration**, not built-in scientific semantics in FAIRmorph Engine.

## Start in GitHub Actions (recommended)

1. Open [CS-PHOC external reference regression](https://github.com/FAIRmorph/fairmorph-engine/actions/workflows/cs-phoc-reference.yml).
2. Select **Run workflow**, branch **`refactor/framework-v012-foundation`**, then **Run workflow**.
3. Wait for both `ubuntu-latest` and `windows-latest` jobs.
4. Open the completed workflow run and download **`cs-phoc-reference-ubuntu-latest`** or **`cs-phoc-reference-windows-latest`** under **Artifacts**.
5. Inspect `publication/eml.xml`, `publication/meta.xml`, `publication/event.txt`, `publication/occurrence.txt`, `publication/cs-phoc-dwca.zip` and `test-report.json`.

**Important:** A newly added workflow step is not considered passing until the manual workflow is actually run. The standard PR CI does **not** execute this separate reference workflow.

## Start locally

Requirements: Python 3.11+, repository checkout, installed development dependencies, writable output directory.

```bash
git checkout refactor/framework-v012-foundation
python -m pip install -e ".[dev]"
python examples/cs-phoc/run_reference_publication.py --output ./cs-phoc-reference-output
```

The output directory **must not exist** before invocation. To rerun, use a new name, e.g. `--output ./cs-phoc-reference-output-02`. The same command works in PowerShell.

The runner performs a real generic CLI lifecycle: project initialization, imports of the two CSV files, explicit mapping staging and reviewer approval, RUN/2 execution, immutable RUN verification, Data Package export and project verification. It then independently checks every mapped source cell and produces the **reference** EML/DwC-A export.

### Configuration files

| File | Role |
| --- | --- |
| `mapping-profile.json` | Pinned CS-PHOC count fields, zero/missing policies, acceptance totals and source SHA |
| `publication-metadata.json` | Publisher/DOI/license provenance and explicit non-endorsement note |
| `reference-publication.json` | Reference export row counts, output formats, Event core/Occurrence extension and provenance guardrails |
| `run_reference_publication.py` | Manual test driver, checks and archive generation |
| `legacy/dwca.py` | **Historical, publisher-compatible reference scientific mapping** used only by this example driver |

The configuration `reference-publication.json` is an **example-level reference configuration**, not an input that can be passed directly to `core.publication_adapters.export_dwca`.

### Expected outputs and acceptance

| Check | Expected |
| --- | ---: |
| Generic RUN observations | 16,940 |
| Explicit zeros | 11,599 |
| Count sum | 79,232 |
| Reference Darwin Core Event rows | 536 |
| Reference Darwin Core Occurrence rows | 16,940 |
| ZIP members | `event.txt`, `occurrence.txt`, `meta.xml`, `eml.xml` |

The runner also verifies the approved counts SHA-256, each source-cell value against the generic RUN, project integrity, ZIP CRC and XML well-formedness. Its `test-report.json` pins the RUN manifest, input hashes and generated file hashes.

**Validation boundary:** The generated EML and DwC-A are a **reference implementation export**, **not an execution of the generic publication adapters**. The legacy scientific mapping is deliberately confined to the CS-PHOC example; it is not imported by the Engine core. The driver does **not** claim official EML XSD validation or official DwC-A XSD validation, nor byte equivalence with the original publisher's archive. The resulting EML is a FAIRmorph-derived metadata document, **not the publisher's original IPT EML**, and nothing is uploaded or published.

### Why the generic publication adapter cannot yet generate this archive

`core.publication_adapters.export_dwca` requires a verified RUN/2 with separately pinned, declared **Event and Occurrence Parquet tables**, a publication profile containing the exact RUN manifest and metadata SHA-256, a projection plan naming those artifacts and an integrity plan with validated identifiers and foreign keys. The current generic count RUN contains `outputs/observations.parquet` and lineage, but **does not contain a published Event table nor the author-specific Occurrence columns**. The publication contracts intentionally prohibit inventing them.

The reference runner therefore provides a **real, manually executable output test now** without pretending that the generic adapter's Event/Occurrence projection is implemented. To qualify a **generic-adapter EML/DwC-A acceptance**, a subsequent change must add an explicit, reviewed projection/materialization stage producing both tables as checksum-pinned RUN artifacts, external publication-profile/projection/integrity JSON, official XSD validation and regression checks against the publisher's reference fingerprints. That work is **still open**.

See [PoC Acceptance Report](../../docs/POC-ACCEPTANCE-REPORT.md) and [User Guide](../../docs/USER-GUIDE.md).
