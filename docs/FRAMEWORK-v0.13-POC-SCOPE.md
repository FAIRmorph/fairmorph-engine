# Scope and development policy (v0.13)

**Status:** Technical framework and implementation policy for the pre-1.0 FAIRmorph Engine proof of concept. The Python package's version (`0.1.0`) and framework document version (`v0.13`) are distinct. The v0.13 framework extends the v0.12 architecture; **it does not assert complete implementation of that architecture**.

## Binding principles before framework 1.0

1. **Build a verifiable vertical proof of concept, not an entire product.** The scope is an inspectable, reproducible path from imported source data through explicit decisions and a verified RUN. Comprehensive UI workflows, user roles, installation bundles, scalability, signatures, migration support and production-grade operational durability are not implied.
2. **Preserve the scientific and technical boundaries.** Original source bytes are immutable; physical source identity is distinct from scientific interpretation. Scientific field definitions and domain mappings require explicit review before semantic use. Null and numerical zero remain distinct. Actual entity/schema/relationship revisions and RUN snapshots are version-pinned and verifiable. Do not invent fields, ecological interpretations or publication approvals from a successful import or pipeline run.
3. **Experimental formats may evolve before 1.0.** Changes to PoC APIs, configuration schemas and project layout do not require legacy compatibility, but they must be made consistently across code, schemas, tests, examples and documentation. Do not silently overwrite completed source objects, approved revisions or historical RUN evidence. Any future production compatibility policy must be established explicitly.

These principles govern implementation expectations, **not an automated certification of an entire scientific dataset**.

## Implemented Engine capabilities and known gaps

| Area | Implemented in the current PoC | Not established |
| --- | --- | --- |
| Source import and project catalog | Local content-addressed source storage, resource identity, SQLite catalog and verified RUN/2 | Production backup, concurrent writers and power-loss durability |
| Field semantics and mappings | Versioned SourceFieldDefinitions, explicit review events, reviewed mappings and current revision identity | Complete scientific validation and all Workbench interviews |
| Entity materialization | Selected SamplingEvent, Occurrence and MeasurementOrFact pipelines under explicit approved bindings | Execution of all possible ecological Entity types |
| Audit | Declarative DAG/row-count evidence; sparse directly comparable changed values | Universal stored row-by-row lineage for every DAG operation |
| Relations | Four scoped typed assertion predicates with append-only assert/replace/retract and historical RUN snapshots | Complete domain relation vocabulary and rich temporal/spatial review |
| Schema profiles and metadata | Local schema registry, approved exact profile bindings, revisioned metadata evidence | Complete domain profiles, spatial specialist validation and comprehensive metadata UX |
| Publication | Verified Data Package path and separate EML/DwC-A adapters with profile, projection and integrity preflight | Generalized one-command publication, publisher-certified products, native PANGAEA/GeoJSON exports |

### Tested evidence and its proper interpretation

The Engine's automated suite exercises generic behavior with synthetic inputs. See [operations and CI](OPERATIONS.md) for commands and the current test pipeline. A test-pass count from an older commit must **not** be represented as the complete current test suite.

Separately, [FAIRmorph validations](https://github.com/FAIRmorph/fairmorph-validations) reproduces a **pinned** Engine revision on genuine CS-PHOC research CSVs. Its [independent reviewer guide](https://github.com/FAIRmorph/fairmorph-validations/blob/main/docs/CS-PHOC-REPRODUCTION-AND-RESULTS.md) reports results and limits. In that test, the generic Engine executes a verified tabular RUN; **dataset-specific code in the validations repository**, not the Engine's generic publication adapter, creates the three test outputs. The Workbench is not exercised in this evidence.

## Framework compatibility and review implications

Engine registry approvals are **explicit, revision-bound actions**; an unreviewed draft or project-user discussion is not an approved scientific record. A `verified` project status proves the defined integrity checks passed, not that a biologist signed off the interpretation. A schema-valid DwC-A or EML document is not automatically publication-ready.

FAIRmorph has **no AI runtime requirement**. Source-field descriptions may come from user-confirmed or documented sources. Any AI-assisted description supplied for a specific validation experiment must be labelled truthfully as derivative provenance; it does not introduce an AI feature into the Engine.

## Further implementation areas

The priority after a successful vertical test is to expose the existing Engine-owned decisions coherently through the separate Workbench, then strengthen generic publication projection and adapter integration, and finally broaden scientific datasets and production operations as separate validated milestones.

For the actual commands, use the [user guide](USER-GUIDE.md); for contracts, use [data contracts](DATA-CONTRACTS.md); for architectural details, use [architecture](ARCHITECTURE.md).
