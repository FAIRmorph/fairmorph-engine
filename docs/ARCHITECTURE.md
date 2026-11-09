# Architektur, Komponenten und Konzepte

## 1. Systemgrenze

Die Engine besteht aus einer Typer-CLI (`src/fairmorph_engine/cli.py`), einem Python-Kern (`core/`), tabellarischen Transformationen (`processing/`), versionierten JSON-Schema-Verträgen (`contracts/`) und explizit getrennten Referenzbeispielen (`examples/`). Sie arbeitet lokal; eine HTTP- oder gRPC-API ist im untersuchten Kern nicht implementiert.

```text
CSV / externe Profile / Metadaten
            |
      CLI (NDJSON)
            |
   Projekt + SHA-256-Objektspeicher
            |
   SQLite: Ressourcen, Feldrevisionen, Reviews, Mappings
            |
   Freigabeprüfung -> generischer RUN/2-Executor
            |
   runs/<RUN_ID>/ (Parquet, Lineage, Snapshots, Manifest)
            |
   Verifikation -> Data Package / optionale Publikationsadapter
            |
   explizite Recovery für unterbrochene RUN-Publikation
```

## 2. Modulübersicht

| Modul | Verantwortung |
| --- | --- |
| `cli.py` | CLI-Kommandos, strukturierte NDJSON-Ausgabe, Fehler-Exitcodes |
| `core/project.py` | Projektanlage, SQLite-Grundtabellen, Import, SHA-Objekte, virtuelle Pakete |
| `core/registry.py` | Append-only Felddefinitionen, Review-Entscheidungen, Mapping-Versionen, Snapshots |
| `core/schema_registry.py` | Lokales, versioniertes Schema-Register ohne Remote-`$ref` |
| `core/profile.py` | Externes CSV-Mapping einlesen, Preflight, Draft und gebündelte Freigabe |
| `processing/tabular.py` | Generisches Wide-to-Long für Counts und typisierte Werte |
| `core/run_executor.py` | Freigabe- und Pin-Prüfung, Polars/Parquet, Qualität, RUN/2-Publikation |
| `core/export.py` | RUN-Integritätsprüfung, Frictionless-artiges Data Package, Projektprüfung |
| `core/run_recovery.py` | Explizite Wiederherstellung von RUN-Indizes aus validierten Verzeichnissen |
| `core/publication.py` | Externe Publikationsabsicht und Metadaten validieren |
| `core/publication_projection.py` | Geplante Tabellen/Spalten gegen gepinnte Parquet-Artefakte prüfen |
| `core/publication_bindings.py` | DwC-Feldbindungen gegen Projektionsspalten prüfen |
| `core/publication_integrity.py` | Publikationsweite Integritätsbedingungen prüfen |
| `core/publication_materialize.py` | Deklarierte Publikationstabellen als CSV materialisieren |
| `core/publication_adapters.py` | EML- und Darwin-Core-Archive-Erzeugung/-Validierung |
| `core/eml_compiler.py` | Projektmetadaten in EML-XML übersetzen |

## 3. Projektverzeichnis

```text
<projekt>/
  project.json                  # lesbarer Projektindex
  catalog/catalog.sqlite       # relationale Identitäten, Reviews, Mappingzustände
  objects/sha256/ab/<sha256>    # unveränderte Originalbytes
  imports/<import_id>/manifest.json
  packages/<package_id>/virtual-descriptor.json
  configurations/              # projektbezogene Konfigurationen
  registry/schemas/            # bei Bedarf versionierte Schemas
  runs/
    .pending-<run_id>/         # noch nicht veröffentlichter Versuch
    <run_id>/
      manifest.json
      inputs.snapshot.json
      configuration.snapshot.json
      outputs/observations.parquet
      audit/lineage.parquet
      reports/quality.json
  exports/<export_id>/
    export-manifest.json
    package/datapackage.json
    package/observations.csv
    package/lineage.csv
    package/quality.json
```

`project.json` enthält `project_id`, `name`, `schema_version`, `catalog_schema_version`, `input_objects`, `package_ids` und `run_ids`. Die SQLite-Tabellen umfassen `project_meta`, `source_objects`, `source_resources`, `packages`, `package_resources`, `runs` sowie bei Registry-Nutzung `source_fields`, `field_definition_revisions`, `field_definition_reviews`, `current_field_definitions`, `mapping_versions`, `mapping_reviews` und `mapping_field_bindings`. Das Schema-Register ergänzt `schema_versions`.

## 4. Identität, Unveränderlichkeit und Freigabe

**Objektidentität:** Originaldateien erhalten einen SHA-256-Digest. Identische Bytes können im Objektspeicher dedupliziert werden. Der Importzustand `imported_unmapped` weist ausdrücklich darauf hin, dass noch keine wissenschaftliche Zuordnung erfolgt ist.

**Feldsemantik:** Ein `source_field_id` identifiziert ein Quellfeld; seine `field_definition_revisions` sind versionierte Definitionen. Die `field_definition_reviews` dokumentieren die explizite Entscheidung. Definitionen enthalten u. a. Beschreibung, Definitionsquelle, Zähleinheit und Missing-/Null-Semantik. Eine technische Spaltenbezeichnung ist keine fachliche Definition.

**Mapping:** `mapping_id` und `version` bezeichnen die fachliche Mapping-Version, `mapping_sha256` pinnt den Inhalt. `draft` und `approved` sind verschiedene Zustände. Die Ausführung akzeptiert nur genehmigte, in sich konsistente Snapshots; ein späteres Mapping-Update verändert bestehende RUNs nicht.

**Schema-Registry:** `schema_id` ist eine HTTPS-URI, `schema_version` eine SemVer-Version, `schema_sha256` pinnt den Inhalt. Schemas werden lokal validiert; Remote-`$ref`-Auflösung ist untersagt. `draft`, `approved` und `deprecated` sind registrierte Zustände, nicht automatische Migrationsmechanismen.

## 5. Transformation und RUN/2

Die Operationen `wide-to-long-counts/1` und `wide-to-long-values/1` transformieren deklarierte CSV-Spalten in Beobachtungszeilen. Counts benötigen explizite Regeln für leere Zellen und Nullen. Typisierte Werte verlangen eine deklarierte Typzuordnung (`integer`, `decimal`, `text`) und Missing-Tokens. Der Engine-Kern leitet keine wissenschaftlichen Schwellenwerte oder Taxonomien ab.

Ein RUN erzeugt `record_id` aus Quellhash, Zeile, Spalte, Transformation und Mapping-Pin. Die `lineage.parquet` bewahrt den Bezug zur Quelle. `inputs.snapshot.json` hält Ressourcen- und Registry-Pins fest; `configuration.snapshot.json` speichert die verwendete Mapping-Konfiguration. `manifest.json` enthält Prüfsummen der Artefakte. Qualitätsmetriken wie `output_rows`, `explicit_zeros` und `value_sum` sind Beobachtungen; projektbezogene Sollwerte müssen explizit im Mapping stehen.

Die Publikation läuft über ein `.pending-*`-Verzeichnis und anschließendes Umbenennen in `runs/<run_id>`. Danach werden `project.json` und SQLite aktualisiert. Da diese Speicher keine gemeinsame Transaktion haben, kann ein Prozessabbruch zu einem bereits vorhandenen RUN mit unvollständigen Indizes führen. [Recovery](RUN-RECOVERY.md) gleicht diese Zustände ausdrücklich ab.

## 6. Sicherheits- und Vertrauensgrenzen

Prüfsummen entdecken nachträgliche Byteänderungen; sie ersetzen keine Signaturen oder Zugriffskontrolle. RUN- und Exportverifikation lehnen unsichere Pfade und modifizierte Artefakte ab. Die Datenverarbeitung setzt fachlich korrekte, extern genehmigte Profile voraus. Recovery benötigt exklusiven Schreibzugriff. Offline-XSDs werden aus `vendor/schemas/` bzw. expliziten lokalen Pfaden verwendet. Ein Publikationsprofil oder validierter Export bedeutet nicht automatisch wissenschaftliche oder organisatorische Publikationsfreigabe.

## 7. Externe Referenz

`examples/cs-phoc/` ist ein **optionales** Projektbeispiel mit eigener Mapping- und Publikationslogik. Der Referenzworkflow wird ausschließlich manuell (`workflow_dispatch`) gestartet. Die reguläre Engine-CI testet die generische Implementierung mit synthetischen Daten.
