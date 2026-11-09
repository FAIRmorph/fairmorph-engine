# Datenverträge, Mapping-Semantik und Publikationsformate

## 1. Vertragsprinzip

FAIRmorph trennt **technische Datenform** (CSV, JSON, Parquet), **fachliche Semantik** (Felddefinitionen), **Transformationsentscheidung** (Mapping), **Ausführungsbeleg** (RUN) und **Publikationsentscheidung** (Profil/Metadaten/Projektion). Jeder Schritt hat eigene Prüfbedingungen. Ein syntaktisch gültiges Profil ist nicht automatisch wissenschaftlich richtig oder genehmigt.

## 2. Versionierte JSON-Schemas

Die Engine führt ausführbare Verträge unter `src/fairmorph_engine/contracts/`; zusätzliche Projekt-/PoC-Verträge liegen in `contracts/`. Relevante Dateien:

| Schema | Verwendung |
| --- | --- |
| `SourceFieldDefinition.schema.json` | Explizite Feldsemantik und Revisionsinhalt |
| `csv-mapping-profile.schema.json` | Externe CSV-Mapping-Definition einschließlich Policies und Beziehungen |
| `import.schema.json` | Nachweis eines unveränderten Quellenimports |
| `virtual-package.schema.json` | Ressourcenreferenzen eines virtuellen Pakets |
| `inputs.snapshot-v2.schema.json` | Im RUN eingefrorene Quellen- und Registry-Pins |
| `run-v2.schema.json` | RUN/2-Manifest mit Status und Artefakten |
| `publication-profile.schema.json` | Publikationsabsicht und Formate |
| `publication-projection.schema.json` | Tabellen-/Spaltenplan für Publikation |
| `publication-integrity.schema.json` | Integritätsregeln der Publikation |

Ältere PoC-Verträge wie `run.schema.json`, `export.schema.json` und `project.schema.json` werden von `core.export.validate_contract` verwendet. **Für exakte Pflichtfelder, Enum-Werte und zusätzliche Eigenschaften ist immer das konkrete Schema maßgeblich**, nicht ein verkürztes Beispiel in dieser Dokumentation.

## 3. Externes CSV-Mapping

Ein Profil benennt `mapping_id`, `version`, `operation`, `source_sha256`, `identifier`, `fields` und Policies. Pro Feld sind Quellspalte, Zielname, Beschreibung, Definitionsquelle und gegebenenfalls Zähleinheit, Zero-Semantik und Missing-Tokens anzugeben. Beziehungen können zusätzliche Ressourcen, Schlüsselspalten, Kardinalität und Missing-Key-Verhalten deklarieren.

Die zwei unterstützten generischen Operationen sind:

- `wide-to-long-counts/1`: Integer-Zählwerte mit expliziten `empty_cell_policy`- und `zero_cell_policy`-Entscheidungen; Nullwerte dürfen nicht unbemerkt zu Missing-Werten werden.
- `wide-to-long-values/1`: Werte mit deklariertem `value_type` (`integer`, `decimal`, `text`) und `missing_tokens`.

**Freigabeprozess:** Profil validieren und als Draft stagen → Feldrevisionen prüfen → Mapping explizit genehmigen → erst danach RUN ausführen. Beziehungen werden im Preflight geprüft; eine deklarierte Beziehung ist nicht automatisch eine universelle Join-Operation im RUN-Executor.

## 4. RUN/2-Artefakte

`runs/<run_id>/manifest.json` enthält unter anderem `schema_version = fairmorph.poc.run/2`, `run_id`, `status = completed`, Zeit-/Engine-/Transformationsinformationen, `configuration_sha256`, `input_snapshot_sha256` und eine Liste von `artifacts` mit Pfad, Bytezahl und SHA-256.

`inputs.snapshot.json` friert Quellobjekt-Pins und den genehmigten Mapping-Snapshot ein. `configuration.snapshot.json` speichert die verwendete Konfiguration. `outputs/observations.parquet` enthält normalisierte Beobachtungen (z. B. `record_id`, `source_identifier`, `source_line`, `source_column`, `target_field`, `value`, optional `value_type`). `audit/lineage.parquet` hält Quellbezüge fest. `reports/quality.json` enthält Ausführungsmetriken.

RUN/2-Verifikation prüft sowohl die Bytes als auch die Registry- und Quellreferenzen. Eine Hash-Übereinstimmung allein beweist keine fachliche Korrektheit.

## 5. Data-Package-Export

`export_data_package` prüft zuerst den RUN, erzeugt danach ein Exportverzeichnis mit `package/datapackage.json`, `observations.csv`, `lineage.csv` und `quality.json`. Das `export-manifest.json` pinnt den Quell-RUN und alle Exportartefakte. Dieses generische CSV-Datenpaket ist **kein Darwin Core Archive**.

## 6. Publikationspipeline

Die optionale Publikationsschicht trennt vier Dokumente:

1. **Publication Profile:** Welche Formate (`eml/2.2.0`, `dwca/1`) sollen entstehen, mit welchen externen Feldbindungen?
2. **Publication Metadata:** Inhaltliche Metadaten; EML verlangt ein explizites `publication_date` für reproduzierbare Ausgaben.
3. **Projection Plan:** Welche im RUN gepinnten Parquet-Artefakte, Zeilentypen, Spalten und gegebenenfalls Datentypen sollen verwendet werden?
4. **Integrity Rules:** Welche Identifikatoren, Beziehungen und Schlüsselbedingungen müssen erfüllt sein?

Der Ablauf ist **Intent-Validierung → Projektion → Bindings → Integrität → Materialisierung → Adapter**. `materialize_publication_tables` schreibt deterministisch sortierte CSV-Tabellen und ein eigenes Manifest. Der EML-Adapter erzeugt XML und prüft es gegen ein lokales offizielles EML-2.2.0-XSD. Der DwC-A-Adapter erzeugt ein ZIP mit `meta.xml` und den deklarierten Core-/Extension-Tabellen; die Validierung prüft Struktur und Referenzen. Vendored Schemas befinden sich unter `vendor/schemas/eml/2.2.0/` und `vendor/schemas/dwca/`.

Die Adapter machen **keine** automatische taxonomische Interpretation, keine implizite DwC-Feldzuordnung und keine externe Veröffentlichung.

## 7. Kompatibilität und Migration

Schema- und Transformationsversionen sind getrennt von der Paketversion. RUN/1 und RUN/2 werden bei der Exportverifikation unterschieden; Projektionen verlangen ausdrücklich RUN/2. Das lokale Schema-Register ermöglicht neue Profiltypen ohne automatische SQLite-Kernmigration. Eine allgemeine Projektmigration oder garantierte Rückwärtskompatibilität aller Draft-APIs ist nicht implementiert.
