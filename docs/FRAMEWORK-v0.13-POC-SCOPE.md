# FAIRmorph – verbindliche PoC-Leitlinien des technischen Rahmenwerks v0.13

**Status:** Architektur-/Entwicklungsvertrag, November 2026. **Geltung:** Dokumentversionen unter **1.0**. Dies ist eine Fortschreibung des vollständigen technischen Rahmenwerks v0.12, **keine** Behauptung vollständiger Implementierung. Grundlage: Kapitel 01–15/ADR-001–055 und die beschlossenen ADR-056–058 der v0.13-Fassung.

## Drei verbindliche Regeln

1. **Vertikaler PoC, kein ausdifferenziertes Vollprodukt.** Solange das technische Rahmenwerk eine Version unter 1.0 trägt, wird ein nachvollziehbarer vertikaler Proof of Concept implementiert. Produktweite Workflows, Rollen, Skalierung, Installer, Signaturen und Migrations-/Betriebs-Härtung sind keine impliziten PoC-Definition-of-Done.
2. **Kernverträge verpflichtend; Breite ausdrücklich begrenzt.** Ein realer Engine-Durchstich muss die Quell-Unveränderlichkeit, getrennte technische und fachliche Identität, bestätigte Feldsemantik, explizit freigegebenes deklaratives Mapping, korrekte Null-/Nullzählungsregeln, schemafixierte Entity- und Relationsverträge sowie prüfbare RUN/2-Snapshots/Checksummen tatsächlich erfüllen. Zusätzliche Profile, Exporte, Workbench-UX, Datenmengen und Randfälle sind dokumentierte Folgearbeit, keine stillschweigende Zusicherung.
3. **Keine Rückwärtskompatibilität vor 1.0; ausschließlich vorwärts konsistente Entwicklung.** Für experimentelle PoC-Datenbanken, Projektdateien, RUN-Formate, CLI-/IPC-APIs und Schemaversionen müssen keine früheren Stände weiterlesbar sein. Breaking Changes aktualisieren Code, Contracts, Fixtures, Tests und Docs synchron und werden dokumentiert. Unveränderte Originalquellen und bereits gültig abgeschlossene RUN-Nachweise dürfen dennoch nicht überschrieben oder stillschweigend uminterpretiert werden. Ab Version 1.0 ist eine neue, ausdrückliche Kompatibilitäts-/Migrationsregel nötig.

Diese speziellere vor-1.0-Regel überlagert ältere allgemeine Roadmap-Formulierungen, die bereits Migrationsinfrastruktur für eine fertige Produktlinie voraussetzen. Sie verlangt **keine** hypothetischen historischen User-RUN-Migrationen; es existieren keine produktiven Nutzerläufe.

## Kernverträge und realisierter Umfang

| Bereich | PoC-Nachweis P0.1–P0.5 | Noch nicht ausdifferenziert |
| --- | --- | --- |
| Quellen/Katalog | SHA-256-gepinnter Import, technische Ressourcen-/Quellidentität, Polars→RUN/2-Parquet | produktive Backups und Crash-/Multiwriter-Garantien |
| Feldsemantik/Mapping | Versionierte SourceFieldDefinitions, explizite Einzel-Nutzerbestätigung und erzwungene Mapping-Pins | vollständige Workbench-Preview und wissenschaftliche Validatoren |
| Entity-Modell | SamplingEvent, optionale Occurrence und MeasurementOrFact | Sample/MediaAsset/SpatialFeature/Dive/Transect-Ausführung |
| Audit | Deklarative DAG- und Mengenprotokolle; nur tatsächliche, direkt vergleichbare Wertabweichungen als sparse Events | vollständige interaktive Quellzell-Diagnostik; keine per-cell-Persistierung im generischen DAG |
| Relationen | Vier explizite Prädikate, append-only assert/replace/retract, historischer Relationsstand im RUN | vollständiges Relationenvokabular und temporale Intervallkonflikte |
| Schemas/Metadaten | Acht lokale v0.8-Domänen-Schemadrafts, bestätigte exakte Pins für *jede* semantische Pipeline, separater bestätigter Metadata-Envelope mit historisch fixierter Revision | vollständige Profilerweiterung, räumliche Fachvalidierung, FTS/R-Tree |
| Publikation | technische Data-Package-/EML-/DwC-A-Adapter und Prüfbausteine | vollständige generische P0.7-Freigabe/GeoPackage-Medien-Strecke |

**Abnahme-Evidenz für bisherigen Engine-Code:** [CI 42858754662](https://github.com/FAIRmorph/fairmorph-engine/actions/runs/42858754662), Commit `c8480ba36bbac55245cce69fd94db58c1adafcbe`: jeweils **129 Tests Linux/Windows**, Ruff grün. Das ist technische/synthetische Testevidenz, **keine** reale CS-PHOC-/Zweitdatensatz-Abnahme. Neuere Doc-Commits haben eigene CI-Belege.

## V0.12-Abgleich: wichtige offene Verträge

- **Kapitel 07/15:** konsistente Sicherung/Recovery, Datenbankmigrationen, idempotente Wiederaufnahme, separate Typindizes/R-Tree und Polars-Key-/Join-Prüfung großer Daten sind keine vollständigen Produktgarantien.
- **Kapitel 09–11:** P0.4 nutzt vier PoC-Relationstypen. Das P0.5-Bundle nutzt für den Metadata-Envelope lokal eingebettete `$defs` statt der separaten v0.12-`provenance-entry.schema.json`; daher keine pauschale Behauptung byteidentischer v0.12-Schema-Hashes. Vor 1.0 Originaldraft und Engine-Kontrakt bewusst normalisieren.
- **Kapitel 12–14:** Workbench-Vorschau Quelle→Feldsemantik→Mapping→Ziel, maschinenlesbare Findings, Profilwahl, bewusste Freigabe und Konfliktresolution gehören zu P0.6.
- **Kapitel 13/15:** v0.12 beschreibt Zellherkunftsprüfung; der generische P0.3-RUN protokolliert aus Gründen der Sparsamkeit nur Wertänderungen. Vollständige Rekonstruktion bei komplexen Joins/Wide-to-Long muss in den jeweiligen E2E- und Preview-Tests nachgewiesen werden, ohne jeden unveränderten Wert dauerhaft zu duplizieren.
- **Kapitel 06/10:** EML/DwC-A/GeoPackage und Medienbezüge werden mit separater Exportsemantik als P0.7 abgegrenzt. **CS-PHOC** (322 Eventzeilen, 2144 Countzeilen, 16.940 Long-Zeilen, 11.599 explizite Nullen) und ein zweiter unabhängiger Datensatz sind P0.8, nicht automatisch von der bisherigen Unit-CI abgedeckt.
- **Zwei Transformationspfade:** Der ältere CSV-Profil-/CS-PHOC-Pfad besitzt andere Artefakte als der generische DAG/Entity-RUN; Ziel ist eine vorwärts konsistente Konsolidierung **ohne** rückwärtsgerichtete Kompatibilitätsschicht.

## Nächste Schritte

**P0.6:** vorhandene Workbench/IPC zunächst prüfen; minimalen UI-Durchstich für Feld- und Profilfreigabe, Relation-/Metadatensicht, Preview und Findings/Value-Changes auf bestätigtem SamplingEvent/MeasurementOrFact aufbauen. Danach **P0.7** Exportprofile und **P0.8** reale Datensatz-Regression. Produkt-Härtung bleibt außerhalb des vertikalen PoC.

Diese Datei beschreibt den **Implementierungsstand und das PoC-Delta**. Die Originalkapitel/Schemas/SQL-Entwürfe des vollständigen Rahmenwerks bleiben separat im v0.13-Quellpaket enthalten.
