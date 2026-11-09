# FAIRmorph Engine — technische Projektdokumentation

**Dokumentationsstand:** Framework-v0.12-Entwicklungszweig `refactor/framework-v012-foundation` (Draft PR #10). **Implementierte Paketversion:** `0.1.0` laut `pyproject.toml`; v0.12 bezeichnet hier den Framework-Ausbaustand, nicht eine bereits veröffentlichte Paketversion.

FAIRmorph Engine ist eine **offline-orientierte, projekt- und datensatzunabhängige Transformations- und Kuratierungsengine**. Sie übernimmt Originaldaten unverändert, verwaltet explizit geprüfte Feldsemantik und Mapping-Versionen, erzeugt nachvollziehbare RUN-Artefakte und unterstützt validierte Exporte. Sie ist weder ein wissenschaftliches Datenrepository noch ein Dienst, der aus Spaltennamen automatisch fachliche Bedeutung ableitet.

## Dokumentationslandkarte

| Dokument | Inhalt |
| --- | --- |
| [Architektur und Konzepte](ARCHITECTURE.md) | Module, Projektmodell, Datenfluss, Hash-Pins, Semantik, RUN/2, Sicherheitsgrenzen |
| [CLI und Python-APIs](API-REFERENCE.md) | Befehle, Signaturen, Parameter, Rückgaben, Integrationsverträge |
| [Datenverträge und Publikation](DATA-CONTRACTS.md) | JSON-Schemas, CSV-Mappings, Parquet, Metadaten, DwC-A und EML |
| [Betrieb, Recovery und Qualität](OPERATIONS.md) | Installation, Betrieb, Verifikation, Fehlerfälle, Tests, PoC-Abnahme |
| [RUN-Recovery](RUN-RECOVERY.md) | Recovery-Verfahren, Fehlergrenzen und Fault-Injection-Matrix |

Vorhandene vertiefende Entwicklungsdokumente: [Foundation](FRAMEWORK-v0.12-FOUNDATION.md), [Generic RUN](FRAMEWORK-v0.12-GENERIC-RUN.md), [Mapping-Profil](FRAMEWORK-v0.12-MAPPING-PROFILE.md), [CS-PHOC-Referenz](CS-PHOC-POC.md). Bei Abweichungen ist die Implementierung im genannten Branch maßgeblich.

## Schnellstart

Voraussetzungen: Python **3.11+**, Git und lokale Schreibrechte. Aus dem Repository:

```bash
python -m pip install -e ".[dev]"
fairmorph-engine --help
fairmorph-engine init-project --project ./demo.fairmorph --name "Demo"
fairmorph-engine import-resource --project ./demo.fairmorph --source ./measurements.csv --role measurements
```

Der Import meldet eine `resource_id` und einen SHA-256-Pin. Die weiteren Schritte benötigen **ein ausdrücklich bereitgestelltes Mapping-Profil** und eine fachliche Freigabe:

```bash
fairmorph-engine stage-csv-mapping --project ./demo.fairmorph --resource-id RESOURCE_ID --profile ./mapping.json
fairmorph-engine approve-mapping --project ./demo.fairmorph --mapping-sha256 MAPPING_SHA256 --reviewer reviewer
fairmorph-engine run-mapping --project ./demo.fairmorph --mapping-sha256 MAPPING_SHA256
fairmorph-engine export-package --project ./demo.fairmorph --run-id RUN_ID
fairmorph-engine verify-project --project ./demo.fairmorph
```

Platzhalter sind durch die tatsächlich ausgegebenen IDs zu ersetzen. Das Mapping-Profil muss dem versionierten JSON-Schema entsprechen. Die CLI schreibt **NDJSON-Ereignisse** nach stdout; Aufrufer sollten die `result`-Ereignisse auswerten, statt IDs aus Dateinamen zu erraten.

## Leitprinzipien

1. **Keine implizite wissenschaftliche Interpretation.** Felddefinitionen, Null-/Missing-Semantik und Publikationszuordnungen sind externe, überprüfbare Entscheidungen.
2. **Originalbytes bleiben erhalten.** Importierte Objekte werden nach SHA-256 adressiert und beim Lesen auf Integrität geprüft.
3. **Freigabe vor Ausführung.** Mapping und referenzierte Felddefinitionen benötigen explizite Review-Entscheidungen.
4. **Reproduzierbare Belege.** RUN-Manifeste referenzieren Konfiguration, Quellen und erzeugte Artefakte über Prüfsummen.
5. **Verifikation ist getrennt von Recovery.** Die Prüfung verändert keine Daten; die Wiederherstellung ist ein expliziter Wartungsvorgang.
6. **Projektunabhängigkeit.** CS-PHOC ist ausschließlich eine externe Referenz unter `examples/cs-phoc/`, kein automatischer Engine-Standard und kein regulärer CI-Zwang.

## Reifegrad

Die Funktionen sind Teil eines **PoC-/Draft-Branches**. Ein grüner CI-Lauf und ein dokumentiertes E2E-Abnahmeprotokoll sind vor einer formalen PoC-Freigabe erforderlich. SQLite und `project.json` bilden keine gemeinsame atomare Transaktion; Cross-Process-Locking, vollständige Power-Loss-Durability, Backup/Restore und ein stabiler Remote-API-Vertrag sind nicht als produktionsreif nachgewiesen. Siehe [Operations](OPERATIONS.md).
