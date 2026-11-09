# Betrieb, Tests, Fehlerbehandlung und PoC-Abnahme

## 1. Installation und lokale Prüfung

```bash
python -m pip install -e ".[dev]"
ruff check src tests
ruff format --check src tests
pytest --cov=fairmorph_engine --cov-report=xml
```

Die Engine benötigt Python 3.11 oder neuer. Der Testumfang der Standard-CI ergibt sich aus `pyproject.toml`: `testpaths = ["tests"]`. Die reguläre GitHub-Workflow-Matrix prüft Ubuntu und Windows. Projektbezogene Referenztests unter `examples/cs-phoc/tests/` gehören nicht automatisch zu diesem Standardumfang.

## 2. Typischer Betriebsablauf

1. `init-project`: Projektstruktur ohne fachliche Interpretation erzeugen.
2. `import-resource`: Originalbytes in SHA-Objektspeicher übernehmen; Rückgabe `resource_id` sichern.
3. `stage-csv-mapping`: externes Profil mit Quelle, Felddefinitionen, Policies und Beziehungen prüfen.
4. `approve-mapping`: Review-Identität und `mapping_sha256` festhalten.
5. `run-mapping`: RUN/2 mit Parquet, Lineage und Qualitätsreport erzeugen; `run_id` sichern.
6. `verify-project`: unveränderte Projekt-/RUN-/Exportkonsistenz prüfen.
7. `export-package`: aus verifiziertem RUN generisches Datenpaket erstellen.
8. Optional: externe Publikationsprofile prüfen und EML/DwC-A über Python-Adapter erzeugen.

Die CLI gibt NDJSON aus. Automatisierungen sollten auf `event = result` und `status = success` prüfen und nicht allein auf stdout-Text oder Verzeichnisexistenz vertrauen.

## 3. RUN-Publikation und Wiederherstellung

Der Executor erstellt zunächst `runs/.pending-<run_id>/`. Nach erfolgreicher Verarbeitung wird das Verzeichnis nach `runs/<run_id>/` umbenannt und anschließend in `project.json` und SQLite registriert. Ein Prozessabbruch kann einen vollständigen, aber noch nicht überall indizierten RUN hinterlassen.

**Recovery-Verfahren:** Schreibende Prozesse stoppen, Sicherung des Projektverzeichnisses anfertigen, `reconcile-runs --project PATH` ausführen, danach `verify-project --project PATH`. Die Recovery verifiziert vollständige RUN-Verzeichnisse und ergänzt fehlende Indexeinträge; sie löscht keine fehlenden Referenzen und fördert keine `.pending-*`-Verzeichnisse zu abgeschlossenen RUNs. Fehlgeschlagene Staging-Versuche bleiben für die Analyse erhalten.

**Grenzen:** Keine Cross-Process-Sperre, kein garantierter fsync-/Power-Loss-Schutz und keine atomare Mehrspeicher-Transaktion. Der Vorgang darf nicht gleichzeitig mit einem Writer laufen. Details und Testmatrix: [RUN-RECOVERY.md](RUN-RECOVERY.md).

## 4. Tests und Qualitätssicherung

| Testfamilie | Zweck |
| --- | --- |
| `test_framework_foundation.py` | Projekt, Import, grundlegende Infrastruktur |
| `test_profile_registry.py`, `test_registry_mapping.py` | Definitionen, Reviews, Mappingzustände |
| `test_relationship_integrity.py`, `test_relationship_preflight_malformed.py` | CSV-Beziehungen, Kardinalität, fehlerhafte Zeilen |
| `test_tabular_primitive.py`, `test_typed_tabular_poc.py` | Counts und typisierte Transformation |
| `test_generic_run_executor.py` | Freigaben, RUN/2, Verifikation, Fehlerbehandlung |
| `test_run_publication_fault_injection.py` | Gezielte Ausfälle an Publikations-/Recovery-Grenzen |
| `test_independent_survey_e2e.py`, `test_cli_external_profile_e2e.py` | Generischer E2E-Durchlauf mit synthetischen Daten |
| `test_publication_*.py`, `test_official_eml_schema.py` | Publikationsabsicht, Projektion, Integrität, EML/DwC-A |
| `test_schema_registry.py` | Lokale, unveränderliche Schema-Versionen |

**Abnahmekriterien für Crash-Recovery:** Fehler vor RUN-Veröffentlichung hinterlassen keine abgeschlossenen Einträge; Fehler bei Indexaktualisierung rollen gewöhnliche I/O-Fehler zurück; ein nach RUN-Veröffentlichung simulierter Prozessabbruch lässt sich rekonstruieren; beschädigte RUNs werden abgewiesen; Recovery ist idempotent; die gesamte Testmatrix besteht auf Ubuntu und Windows.

**Statusregel:** Das Vorhandensein eines Tests ist kein Nachweis seines Erfolgs. Ein PoC gilt erst dann als abgenommen, wenn die CI für einen eindeutig benannten Commit erfolgreich ist und ein E2E-Abnahmeprotokoll Soll-/Ist-Werte, Fehlerfälle und Einschränkungen dokumentiert. Diese Dokumentation behauptet **keinen** bereits erreichten finalen Abnahmestatus.

## 5. Fehleranalyse

- **Mapping nicht genehmigt:** Review und Mapping-SHA kontrollieren; keine automatische Freigabe.
- **Originalobjekt modifiziert:** Hash gegen Importmanifest prüfen; nicht durch manuelle Änderung der SHA-Pins „reparieren“.
- **Ungültige CSV-Zeile oder Beziehung:** CSV und deklarierte Schlüssel/Kardinalität korrigieren; Profil erneut prüfen.
- **RUN-Artefakt beschädigt:** RUN nicht exportieren oder als abgeschlossen akzeptieren; Prüfsummenfehler untersuchen.
- **Indexabweichung nach Unterbrechung:** Writer stoppen, Sicherung anfertigen, explizite Recovery ausführen.
- **`.pending-*` vorhanden:** Nicht automatisch löschen; Fehlerdiagnostik und gegebenenfalls manuelle Bereinigung nach Untersuchung.
- **EML/DwC-A-Validierung schlägt fehl:** Externe Metadaten, Projektion, Integritätsregeln und lokale XSDs prüfen.

## 6. Bewusst nicht als produktionsreif ausgewiesen

Cross-Process-Locking, vollständig transaktionale SQLite-/Dateisystem-Publikation, Stromausfall-Durability, systematisches Backup/Restore, öffentliche stabile Python-/Remote-API, automatische Projektmigration und fachliche Validierung beliebiger Wissenschaftsdomänen sind keine bereits erfüllten Produktionsgarantien. Die optionale CS-PHOC-Referenz dient ausschließlich einer zusätzlichen, explizit gestarteten Regression.

## 7. Nachvollziehbare Abnahme

Ein finales Abnahmeprotokoll sollte mindestens Git-Commit, Betriebssystem-/Python-Version, Ruff- und Pytest-Ergebnis, generischen E2E-Durchlauf, Mapping-/RUN-/Export-Prüfsummen, Fault-Injection-Matrix, bekannte Einschränkungen und eine explizite Freigabeentscheidung enthalten. Ohne diese Nachweise bleibt die PoC-Abnahme offen.
