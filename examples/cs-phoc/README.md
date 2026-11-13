# CS-PHOC: Manual Reference Publication Example

This directory contains a **dataset-specific example**, not generic biological semantics or a production publication workflow in FAIRmorph Engine. The original CS-PHOC research belongs to its authors; source and derivative publications must not be confused.

For the principal **independent real-data validation**, including exact original source revisions, 16,940 source-cell comparisons, all three locally generated test outputs and caveats, use [fairmorph-validations](https://github.com/FAIRmorph/fairmorph-validations/blob/main/docs/CS-PHOC-REPRODUCTION-AND-RESULTS.md). That validation does **not** use this Engine example to claim generic multi-format publication support.

## Run the optional Engine example

Requires Python **3.11+**, the Engine dependencies installed, and a writable **new output directory**. From the Engine repository root:

```bash
python -m pip install -e ".[dev]"
python examples/cs-phoc/run_reference_publication.py --output ./cs-phoc-reference-output
```

The destination **must not already exist**; use a new path for each repeat. The command imports the two bundled CSV reference files, stages and confirms an explicit example count-mapping profile, executes a verified reference RUN, exports a generic Data Package, compares all mapped recorded count cells against the source, and runs an **example-scoped** publisher-style Event/Occurrence conversion.

This example **does not execute `core.publication_adapters.export_dwca()`**. It uses a separate legacy reference converter restricted to this example. The generated EML is FAIRmorph-derived, not the original publisher's EML; the example does **not** claim official EML/DwC-A XSD validation, external submission or author endorsement.

## What it generates

```text
cs-phoc-reference-output/
  project/                       # New local Engine project, imports and RUN
  approved-mapping.json          # Example-specific approved profile snapshot
  publication/
    event.txt                    # Site-specific Darwin Core Event rows
    occurrence.txt               # Age/sex category Occurrence records
    meta.xml                     # Darwin Core Archive metadata
    eml.xml                      # FAIRmorph-generated derivative metadata
    cs-phoc-dwca.zip             # ZIP packaging of those files
  test-report.json               # Source hashes, RUN identity and checks
```

| Check | Expected from this pinned reference example |
| --- | ---: |
| Source survey windows | 322 |
| Source count records | 2,144 |
| Generic RUN observation records | 16,940 |
| Reference site-specific Events | 536 |
| Reference Occurrences | 16,940 |
| Recorded explicit zeros | 11,599 |
| Sum of category count values | 79,232 |

The `test-report.json` carries the actual RUN manifest digest, source file digests, generated file hashes and specific validation limitations. **Count records are not unique individual animals; the sum is not a seal population estimate.** Empty source categories are omitted, not zero-filled.

## Files and boundaries

| File | Purpose |
| --- | --- |
| `mapping-profile.json` | Explicit count-field and zero/missing policy used by the example |
| `reference-publication.json` | Source digests, expected row totals and example output intentions |
| `publication-metadata.json` | Research-source attribution and derivative metadata details |
| `run_reference_publication.py` | Manual, locally reproducible example driver |
| `legacy/dwca.py` | Historical publisher-compatible data projection; intentionally outside Engine core |

The **generic** `core.publication_adapters.export_dwca` path instead requires a verified RUN with separately declared Event/Occurrence output artifacts and explicit publication profile, projection, integrity and metadata documents. The current example's count RUN does not automatically supply those tables. Technical metadata validity is not scientific review or publication authorization.

**For routine Engine use**, start with the [user guide](../../docs/USER-GUIDE.md), not this dataset-specific example.
