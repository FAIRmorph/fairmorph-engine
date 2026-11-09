# CLI- und Python-API-Referenz

**Stand:** Draft-Branch `refactor/framework-v012-foundation`. Python-Funktionen sind derzeit Implementierungs-APIs, **kein zugesagtes stabiles SemVer-SDK**. Signaturen und Rückgaben können sich bis zur Abnahme ändern. Als Quelle gelten `src/fairmorph_engine/` und die zugehörigen Tests.

## 1. CLI-Vertrag

Installiertes Kommando: `fairmorph-engine`. Die CLI basiert auf Typer. Erfolgs-/Fehlerereignisse werden als **newline-delimited JSON** auf stdout geschrieben. Ein `result`-Event enthält je nach Kommando `status`, `data` oder `message`. Bei behandelten Fehlern wird Exitcode 1 ausgegeben; nicht alle Python-Ausnahmen sind zwingend in strukturierte Fehlerereignisse übersetzt.

| Befehl | Parameter | Zweck |
| --- | --- | --- |
| `init-project` | `--project PATH`, optional `--name TEXT` | Projektstruktur und Katalog anlegen |
| `import-resource` | `--project PATH --source FILE --role ROLE` | Bytes unverändert importieren, `resource_id` zurückgeben |
| `stage-csv-mapping` | `--project PATH --resource-id ID --profile FILE` | Profil prüfen und Mapping/Felder als Draft registrieren |
| `approve-mapping` | `--project PATH --mapping-sha256 HASH --reviewer TEXT` | Mapping und Felddefinitionen explizit freigeben |
| `run-mapping` | `--project PATH --mapping-sha256 HASH` | Genehmigtes Mapping als RUN/2 ausführen |
| `export-package` | `--project PATH --run-id ID` | Verifizierten RUN als Data Package exportieren |
| `verify-project` | `--project PATH` | Integrität und Indexkonsistenz ohne Änderung prüfen |
| `reconcile-runs` | `--project PATH` | Unterbrochene RUN-Publikation explizit reparieren |
| `handshake` | keine | CLI-/Protokollinformationen ausgeben |
| `poc` | siehe `fairmorph-engine poc --help` | Separater historischer PoC-Befehl; nicht mit generischem RUN/2 gleichsetzen |

**Hinweis:** Die Publikationsadapter sind Python-APIs. Für sie ist in `cli.py` keine eigene vollständige CLI-Kommandofamilie definiert.

## 2. Projekt und Import — `core.project`

- `initialize_project(project: Path, name: str = "FAIRmorph project") -> dict`: legt Standardverzeichnisse und SQLite-Grundschema an; gibt `project.json` zurück.
- `import_resource(project: Path, source: Path, role: str) -> dict`: prüft Quelle/Rolle, speichert SHA-Objekt und Importmanifest, registriert Ressource. Ergebnis u. a. `resource_id`, `sha256`, `object_path`, `state`.
- `register_package(project: Path, package_id: str, resources: dict[str, dict]) -> dict`: registriert eine virtuelle Paketbeschreibung mit Ressourcenreferenzen, ohne Originalbytes zu kopieren.
- `digest(path: Path) -> str`: SHA-256 einer Datei.
- `write_json(path: Path, data: dict) -> None`: JSON-Datei neu anlegen; vorhandene Datei wird nicht überschrieben.
- `connection(project: Path)`: SQLite-Verbindung mit aktivierten Foreign Keys.
- `update_index(project: Path, object_entry=None, package_id=None) -> None`: ersetzt `project.json` über temporäre Datei; nicht transaktional mit SQLite.

## 3. Registry — `core.registry`

- `canonical_bytes(document: dict) -> bytes`: stabile, sortierte JSON-Serialisierung (kein formaler RFC-8785-Vertrag).
- `digest(document: dict) -> str`: SHA-256 dieser Serialisierung.
- `define_field(project, resource_id, locator, definition, parent_revision_id=None) -> dict`: legt eine unveränderliche, schema-validierte Felddefinition an; optionale Vorgängerrevision.
- `review_field(project, revision_id, reviewer, decision) -> dict`: dokumentiert `approved` oder `rejected`; ohne Reviewer keine fachliche Freigabe.
- `register_mapping(project, mapping: dict) -> dict`: speichert eine Mapping-Version als Draft, referenziert Feldrevisionen.
- `approve_mapping(project, mapping_sha256, reviewer) -> dict`: genehmigt eine registrierte Mapping-Version unter Validierungsbedingungen.
- `mapping_snapshot(project, mapping_sha256) -> dict`: liefert die versionierten Quellen-/Feld-/Mapping-Pins für die RUN-Ausführung.

## 4. Externes Mapping — `core.profile`

- `stage_csv_mapping(project: Path, resource_id: str, profile_file: Path) -> dict`: validiert das externe CSV-Mapping-Profil gegen `csv-mapping-profile.schema.json`, Quellspalten und deklarierte Beziehungen; registriert Drafts.
- `approve_staged_mapping(project: Path, mapping_sha256: str, reviewer: str) -> dict`: genehmigt die gestagten Feldrevisionen und das Mapping innerhalb einer SQLite-Transaktion.

Beziehungen prüfen referenzierte Ressourcen, Schlüssel, deklarierte Kardinalität und Missing-Key-Policy. Die Preflight-Implementierung lehnt unter anderem CSV-Zeilen mit zu vielen oder zu wenigen Feldern ab.

## 5. Transformation — `processing.tabular`

- `unpivot_csv(source: Path, *, identifier: str, columns: list[str], empty_cell_policy: str, zero_cell_policy: str)`: erzeugt Long-Format-Beobachtungen für Zählwerte.
- `unpivot_typed_csv(source: Path, *, identifier: str, value_types: dict[str, str], missing_tokens: dict[str, list[str]] | None = None)`: erzeugt typisierte Beobachtungen gemäß externer Typ- und Missing-Deklaration.

Die Funktionen transformieren deklarierte Daten, treffen aber keine fachlichen Annahmen über Messgrößen.

## 6. RUN, Export und Recovery

- `core.run_executor.execute_mapping_run(project: Path, mapping_sha256: str, emit=...) -> dict`: prüft Freigaben und Quellen, erzeugt Parquet, Lineage, Qualitätsreport, Snapshots und RUN/2-Manifest; meldet Fortschritt und Ergebnis.
- `core.run_executor.verify_mapping_run(project: Path, run_dir: Path, manifest: dict) -> None`: prüft RUN/2-Mapping-Snapshot gegen genehmigte Registry-Revisionen.
- `core.export.verified_run(project: Path, run_id: str) -> tuple[Path, dict]`: prüft Manifest, Artefakte, SHA-256, sichere Pfade und bei RUN/2 die Mapping-Pins.
- `core.export.export_data_package(project: Path, run_id: str, emit)`: erzeugt CSV-Datenpaket und Exportmanifest aus einem verifizierten RUN.
- `core.export.verify_project(project: Path) -> dict`: prüft Projektobjekte, Import-/Paketreferenzen, RUNs, SQLite-Konsistenz und Exporte; gibt u. a. `completed_runs`, `exports`, `status` zurück.
- `core.run_recovery.reconcile_runs(project: Path) -> dict`: validiert veröffentlichte RUNs und ergänzt fehlende SQLite-/JSON-Indexeinträge; Ergebnis `recovered`, `pending`, `status`. **Nur ohne parallele Writer verwenden.**

## 7. Schema-Registry — `core.schema_registry`

- `register_schema(project, *, schema_id, schema_version, kind, schema, status="draft", reviewer=None) -> dict`: prüft JSON Schema Draft 2020-12, verweigert Remote-Referenzen, legt unveränderliche Schema-Bytes unter SHA-256 ab. `kind`: `core`, `source`, `export`, `extension`.
- `get_schema(project, *, schema_id, schema_version) -> tuple[dict, str]`: lädt ausschließlich die exakt angeforderte Version und verifiziert ihren Content-Pin.

## 8. Publikations-APIs

Diese Funktionen erwarten **explizite** externe Profile/Metadaten; sie erzeugen keine automatische Darwin-Core-Semantik.

| Modul/Funktion | Signatur bzw. Zweck |
| --- | --- |
| `publication.validate_publication_intent` | `(project, run_id, profile_file, metadata_file) -> dict`; RUN-Pin, Formate, Metadaten und Absicht validieren |
| `publication_projection.validate_publication_projection` | `(project, run_id, plan_file) -> dict`; gepinnte Parquet-Spalten/Typen prüfen |
| `publication_bindings.validate_publication_binding_columns` | `(project, run_id, profile_file, metadata_file, projection_file) -> dict`; deklarierte DwC-Quellspalten prüfen |
| `publication_integrity.validate_publication_integrity` | `(project, run_id, profile_file, metadata_file, projection_file, integrity_file) -> dict`; Schlüssel/Beziehungen und Integritätsregeln prüfen |
| `publication_materialize.materialize_publication_tables` | `(project, run_id, profile_file, metadata_file, projection_file, integrity_file, destination) -> dict`; sortierte CSV-Tabellen mit Manifest erzeugen |
| `publication_adapters.export_eml` | `(project, run_id, profile_file, metadata_file, schema_file, destination) -> dict`; EML-XML mit lokalem XSD validieren |
| `publication_adapters.export_dwca` | `(project, run_id, profile_file, metadata_file, projection_file, integrity_file, destination) -> dict`; Darwin-Core-Archive erzeugen |
| `publication_adapters.validate_dwca_archive` | `(archive, schema_file=DWCA_META_XSD) -> dict`; DwC-A-ZIP und `meta.xml` prüfen |
| `eml_compiler.compile_eml_xml` | `(meta: ProjectMetadata, publication_date: str | None = None)`; EML-XML aus validierten Projektmetadaten erzeugen |

**Wichtige Unterscheidung:** `publication_ready: false` in einem Preflight- oder Materialisierungsresultat bedeutet, dass eine erfolgreiche Strukturprüfung noch keine abschließende Publikationsfreigabe ist.

## 9. Fehler und Integration

Typische Fehler: `ValueError` (ungültige Profile, nicht genehmigte Mappings, Integritätsfehler), `OSError` (Dateisystem), SQLite-Fehler (Katalog/Transaktion), JSON-Schema-`ValidationError`, fehlende Polars-Abhängigkeit. Integrationen sollten Rückgaben und `result`-Events prüfen, RUNs nicht manuell manipulieren und Recovery nur nach Stop aller Writer ausführen.
