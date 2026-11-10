# CS-PHOC – fachliche Kurationsgrundlage, **noch keine Engine-Freigabe**

## Quelle

- Wissenschaftliche Projektquelle: [US AMLR / CS-PHOC](https://github.com/us-amlr/cs-phoc/tree/64f0b77e631c711c681306bbb56a7636ae91a471)
- Primäre CSV-Beschreibung: [data/manuscript/README.md](https://github.com/us-amlr/cs-phoc/blob/64f0b77e631c711c681306bbb56a7636ae91a471/data/manuscript/README.md)
- Publikationslogik: [R/data_to_dwca.R](https://github.com/us-amlr/cs-phoc/blob/64f0b77e631c711c681306bbb56a7636ae91a471/R/data_to_dwca.R)

Alle Aussagen in dieser Datei stammen aus den oben genannten Quellen oder sind ausdrücklich als **zu bestätigende Interpretation** gekennzeichnet. Diese Kurationsnotiz ist kein ersetzender `SourceFieldDefinition`-Contract; die Engine-Registry muss **für jedes Feld** eine neue geprüfte Revision erhalten.

## Identität und Tabellen

| CSV | Feld | Belegte Bedeutung | Registrierungsstatus |
|---|---|---|---|
| events | `event_id` | eindeutige Identität einer Survey-Window-Zeile; Verknüpfung zu counts | noch nicht registriert |
| events | `season_name` | Feldsaisonbezeichnung | noch nicht registriert |
| events | `census_date_start` | Beginn des Erhebungsfensters (tatsächlicher Header) | noch nicht registriert |
| events | `census_date_end` | Ende des Erhebungsfensters (tatsächlicher Header) | noch nicht registriert |
| events | `census_days` | Dauer in Tagen laut Quellbeschreibung | noch nicht registriert |
| events | `surveyed_pst` | ob Punta San Telmo untersucht wurde | noch nicht registriert |
| events | `research_program` | `INACH` bzw. `USAMLR` | noch nicht registriert |
| counts | `count_id` | eindeutiger Count-Datensatzschlüssel, **nicht** automatisch DwC `occurrenceID` | noch nicht registriert |
| counts | `event_id` | zugehöriges Survey Window | noch nicht registriert |
| counts | `location` | Erhebungsort | noch nicht registriert |
| counts | `species` | wissenschaftlicher Artname wie im Ausgangsdatensatz | noch nicht registriert |
| counts | `species_common` | gebräuchlicher Artname wie dokumentiert | noch nicht registriert |
| counts | `total_count` | bereits im Original vorhandene Summe der anderen Count-Spalten | noch nicht registriert |

**Dokumentationsabweichung:** Die Upstream-Dateibeschreibung spricht für die Datumsfelder auch von `census_start_date` und `census_end_date`; die tatsächlichen CSV-Header lauten **`census_date_start`** und **`census_date_end`**. Kein automatischer Alias und keine Änderung des Originals. Vor Bestätigung ist diese Abweichung gegen die Quellautoren-/Manuskriptdokumentation zu klären.

## Explizite Count-Felder

Die Upstream-Dokumentation beschreibt folgende zehn Felder. Für **alle** gilt: Leerer CSV-Wert = *kein Zählwert erhoben bzw. aufgezeichnet*, nicht die Zahl 0. Explizites `0` ist eine echte erhobene Nullzählung und **muss** erhalten bleiben.

| Count-Feld | Fachlich im Upstream-README dokumentierte Bedeutung |
|---|---|
| `ad_female_count` | erwachsene weibliche Tiere |
| `ad_male_count` | erwachsene männliche Tiere |
| `ad_unk_count` | erwachsene Tiere mit unbekanntem Geschlecht |
| `juv_female_count` | juvenile weibliche Tiere |
| `juv_male_count` | juvenile männliche Tiere |
| `juv_unk_count` | juvenile Tiere mit unbekanntem Geschlecht |
| `pup_count` | Jungtiere unter einem Jahr, unabhängig vom Geschlecht |
| `unk_female_count` | Tiere unbekannter Altersklasse, weiblich |
| `unk_male_count` | Tiere unbekannter Altersklasse, männlich |
| `unk_unk_count` | Tiere unbekannter Altersklasse und unbekannten Geschlechts |

**Vor einer formellen Bestätigung prüfen:** fachliche Zähleinheit („Tiere“/Individuen), konkreten Bezug von `0` zu beobachteter Abwesenheit im jeweiligen Zählkontext, Kodierung fehlender Angaben sowie den Unterschied zwischen Anzahl/Observation/Occurrence. Die Engine darf diese Entscheidungen nicht aus Feldnamen ergänzen. Für `total_count` darf **keine** zweite unabhängige Messung erfunden werden; es ist im Quellmaterial eine bereits berechnete Summe.

## Noch ausdrücklich unbestätigte Zielprojektionen

- `SamplingEvent`: Quell-`event_id` ist ein Survey Window. Im veröffentlichten DwC-A wird zusätzlich nach Ortsgruppe in `eventID` mit `-1`/`-2` aufgespalten. **Nicht** stillschweigend die beiden Identitäten gleichsetzen.
- `MeasurementOrFact`: Eine belegte Count-Zelle pro `count_id × count_type` ist eine **mögliche** fachliche Projektion, die erst nach SourceFieldDefinition-Review und Profil-/Entity-Freigabe eingerichtet wird. `0` ist beizubehalten und blank auszuschließen.
- `Occurrence`: Der veröffentlichte DwC-A besitzt `occurrenceID` mit Alters-/Geschlechts-Codes; eine spätere Zielprojektion muss diese getrennte Identitätsregel explizit versionieren.
- Beziehungen: Ausgangstabelle `counts.event_id → events.event_id`; technische Prüfung gegen eindeutige Event-Keys. Das ist nicht automatisch eine fachlich freigegebene `MeasurementOrFact.sampling_event_ref`-Relation.
- Profile: ausschließlich die von der Engine registrierten, exakt SHA-256-gepinnten Schemaversionen nach individueller Bestätigung verwenden.

## Fehlende Entscheidungen / Review-Aufträge

1. An welchen Entity-Typ werden die CS-PHOC-Zählwerte sinnvoll gebunden: `Occurrence` mit `individualCount`, `MeasurementOrFact` als Count-Messung oder beide, jeweils ohne Duplikation der wissenschaftlichen Bedeutung?
2. Wann soll aus einer CSV-Event-Zeile ein oder zwei DwC-A-SamplingEvents werden? Die Upstream-R-Skripte liefern die Publikationsentscheidung, nicht der Rohimport.
3. Was ist der zitierfähige und durch den Verantwortlichen bestätigte Ursprung einer jeden Felddefinition, inklusive `census_days`-Berechnung?
4. Wie werden Alters- und Geschlechtscodes bei `pup_count` und `unk_*_count` explizit in eine später separate Publikationskonfiguration übertragen?
5. Welcher Wert und welche Revision bilden die bestätigten Projekt-/Publikationsmetadaten (EML)? Der mitgelieferte Titel ist lediglich ein unbestätigter Draft.

**Keine Person, Freigabe oder Schema-Pin wird in diesen Vorlagen erfunden.**
