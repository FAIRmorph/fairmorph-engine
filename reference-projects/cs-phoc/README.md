# CS-PHOC – FAIRmorph v0.13 Referenzprojekt-Overlay (Vorbereitung)

**Status:** Konfigurations- und Quelleninventar; **kein** registriertes/ausgeführtes FAIRmorph-Projekt, keine fachliche Freigabe und kein validierter Export. Diese Dateien liegen in einem **separaten Referenzprojekt-Verzeichnis**. Die FAIRmorph Engine, Workbench, ihre Schemas, Python-/Rust-/Svelte-Skripte und bestehende Projektverträge werden **nicht geändert**.

## 1. Quelle unverändert halten

Verbindlicher, nachprüfbarer Ausgangspunkt: [us-amlr/cs-phoc@64f0b77e](https://github.com/us-amlr/cs-phoc/tree/64f0b77e631c711c681306bbb56a7636ae91a471).

| Unveränderte Upstream-Quelle | Zweck |
| --- | --- |
| `data/manuscript/cs-phoc-events.csv` | ursprüngliche Survey-Windows (322 Zeilen) |
| `data/manuscript/cs-phoc-counts.csv` | ursprüngliche Count-Zeilen (2.144 Zeilen) |
| `data/manuscript/README.md` | fachliche Feldbeschreibung und Missing-Semantik |
| `R/cs-phoc_examples.R` | vom Forschungsprojekt dokumentierte Long-Transformation |
| `R/data_to_dwca.R` | publizierte Event-/Occurrence- und DwC-A-Interpretation |
| `README.md` | Projektidentität, DOI, DwC-A-Konventionen |

Die zwei CSV-Dateien sind **nur eine der vom Upstream bereitgestellten Veröffentlichungsrepräsentationen**; sie sind nicht mit unveränderten historischen Feldaufzeichnungen gleichzusetzen. Originale bleiben byteidentisch. Sie werden **nicht** in diesem Overlay gespiegelt. Ihre Git-Blob-SHA-1-Werte sind in `validation/source-baseline.json` für die Upstream-Identität dokumentiert. Die Engine muss beim Import die tatsächlichen **SHA-256 der Datei-Bytes** selbst ermitteln und im Projektobjektstore fixieren. Git-SHA-1 darf nicht als FAIRmorph-Objekt-SHA-256 verwendet werden.

## 2. Projektverzeichnis aufbauen – ausschließlich vorhandene Engine-CLI

Lokal ein neues Verzeichnis außerhalb dieses Git-Repositories anlegen, beispielsweise `./cs-phoc.fairmorph`:

```sh
fairmorph-engine init-project --project ./cs-phoc.fairmorph --name "CS-PHOC reference"
fairmorph-engine import-resource --project ./cs-phoc.fairmorph --source ./cs-phoc/data/manuscript/cs-phoc-events.csv --role events
fairmorph-engine import-resource --project ./cs-phoc.fairmorph --source ./cs-phoc/data/manuscript/cs-phoc-counts.csv --role counts
```

Der Pfad `./cs-phoc` bezeichnet einen **separaten Checkout des unveränderten Upstream-Repositories**. Dateipfade entsprechend der lokalen Ordnerwahl anpassen. Die `resource_id`-Werte stammen aus den Importresultaten, nicht aus Konventionen oder Dateinamen.

- Die unveränderte Vorlage `configurations/drafts/pipeline-technical.json` enthält exakt zwei zu ersetzende `resource_id`-Platzhalter. Eine **Kopie** der Vorlage im Projektverzeichnis bearbeiten und die vom Import zurückgegebenen IDs einsetzen. Nicht die inhaltsadressierten Engine-Pipeline-Dateien nachträglich editieren.
- `configurations/drafts/dataset-metadata.json` ist ein **unbestätigter** Projekt-Draft, dessen Titel der zitierten Publikation entnommen ist. Die zuständige Person muss ihn zunächst prüfen. Die aktuelle Workbench kann diesen Draft in ihrer Oberfläche bearbeiten, anschließend mit der Engine registrieren und ausdrücklich bestätigen.
- Aus der korrekt ausgefüllten technischen DAG-Vorlage kann die Engine eine neue, inhaltsadressierte Pipeline registrieren und auswählen:

```sh
fairmorph-engine register-pipeline --project ./cs-phoc.fairmorph --definition ./cs-phoc.fairmorph/configurations/drafts/pipeline-technical.json
fairmorph-engine select-pipeline --project ./cs-phoc.fairmorph --pipeline-sha256 <vom-register-pipeline-Befehl-ausgegebene-SHA-256>
fairmorph-engine run-pipeline --project ./cs-phoc.fairmorph
fairmorph-engine verify-project --project ./cs-phoc.fairmorph
```

**Wichtig:** `pipeline-technical.json` ist ausdrücklich **nur ein technischer Test der bestehenden DAG-Verträge**. Er macht keine semantische Entity-Projektion, enthält keine angenommenen SourceFieldDefinition-Hashes und legitimiert keine wissenschaftliche Interpretation. Ein erfolgreicher technischer RUN ist **nicht** die v0.13-P0.6/P0.7-Freigabe.

## 3. Vorliegende technische DAG-Vorlage

Verwendet nur bereits von der Engine unterstützte Operatoren:

1. `table.unpivot/1`: zehn ausdrücklich aufgeführte Zählspalten zu `count_type` und `count_value`; `total_count` bleibt als **quellengegebene Kontrolle**, nicht als elfte Zählklasse.
2. `table.filter/1` mit `is_not_null`: tatsächlich fehlende Zählwerte entfernen, **explizite `0`-Werte behalten**.
3. `table.join/1` auf `event_id` mit `m:1`, `require_match` und `preserve_left_rows`: zusätzlichen Event-Kontext technisch anbinden, ohne neue wissenschaftliche Entity-Beziehungen zu behaupten.

Kein hartcodierter CS-PHOC-Sonderfall in Engine-/Workbench-Code. Die zehn Quellspalten stehen **ausschließlich in der CS-PHOC-Projekt-DAG-Konfiguration**.

## 4. Prüferwartungen und Grenzen

Die in `validation/source-baseline.json` dokumentierten Werte wurden durch Sichtung der beiden upstream-gepinnten CSV-Dateien erhoben:

- 322 Survey-Windows mit 322 verschiedenen `event_id`;
- 2.144 Count-Datensätze mit 2.144 verschiedenen `count_id`;
- 16.940 ausdrücklich belegte Count-Zellen, davon 11.599 explizite Nullen;
- 4.500 leere Count-Zellen (also `2.144 × 10 − 16.940`);
- keine Counts mit unbekannter `event_id`;
- je Count-Zeile entspricht `total_count` der Summe ihrer zehn Count-Felder (fehlende Felder ausgenommen);
- Summe der Quell-`total_count`: 79.232.

Das sind **Quellbaseline-Werte** und noch keine beobachteten FAIRmorph-RUN-Metriken. Der spätere generische RUN muss entsprechende Zahlen und `value_change`-Belege reproduzieren. Ein rein tabellarischer Join kann zusätzliche Zeilen/Spalten erzeugen; erwartet ist die Erhaltung der **16.940 Long-Zeilen**.

## 5. Erst danach die v0.13-Semantik registrieren

Siehe `curation/FIELD-REVIEW.md`. Die erforderlichen ausdrücklichen Entscheidungen gehören **in neue projektlokale Konfigurationen und Engine-Registrierungsereignisse**, nicht in veränderte Engine-Contracts:

1. Für jede relevante Quellspalte eine SourceFieldDefinition aus Upstream-Belegen erarbeiten und von der verantwortlichen Person bestätigen.
2. Exakte lokale `SamplingEvent`-/`MeasurementOrFact`-Profile durch die Engine installieren und bestätigen; ggf. `Occurrence` nur mit belegter Entscheidung.
3. **Neue** Entity-DAG-Revision konfigurieren, mit tatsächlichen Resource-IDs, bestätigten SourceFieldDefinition-Revisionen und Schema-Hashes. Die technische Vorlagendatei nicht als freigegebene Entity-Pipeline ausgeben.
4. Projektions-/Relationenkonfigurationen prüfen und ausdrücklich bestätigen; die Engine friert dann den Stand im RUN/2 ein.
5. Erst danach P0.6-Preview, P0.7-Export und P0.8-E2E an diesem Projekt validieren.

**Stop-Regel:** Falls sich für ein wissenschaftlich erforderliches Mapping kein vorhandener Engine-Vertrag ohne Umdeutung konfigurieren lässt, dokumentieren wir die Lücke und entscheiden separat über das Rahmenwerk. Wir passen nicht stillschweigend Engine-Code, Workbench-Skripte, Contracts oder Originaldaten an den Testdatensatz an.

## Herkunft und Zitate

Upstream: https://github.com/us-amlr/cs-phoc ; Publikation: https://doi.org/10.1038/s41597-024-03744-9 ; Datensatz: https://doi.org/10.48361/gklk1u . Das Referenz-Overlay stellt **keine** neue Originalpublikation und keine neue wissenschaftliche Bestätigung dar.
