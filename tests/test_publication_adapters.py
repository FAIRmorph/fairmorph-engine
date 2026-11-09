"""Generic archive layout checks using synthetic project-independent tables."""

import csv
import json
import zipfile

import pytest
from lxml import etree

from fairmorph_engine.core.publication_adapters import DWC_TEXT, export_dwca, export_eml


def test_dwca_occurrence_core_and_extension(tmp_path, monkeypatch):
    profile = {
        "formats": ["dwca/1"],
        "dwca": {
            "core": "Event",
            "core_fields": [
                {"source_field": "event_key", "term": "http://rs.tdwg.org/dwc/terms/eventID"}
            ],
            "extensions": [
                {
                    "row_type": "Occurrence",
                    "fields": [
                        {
                            "source_field": "record_key",
                            "term": "http://rs.tdwg.org/dwc/terms/occurrenceID",
                        },
                        {
                            "source_field": "event_ref",
                            "term": "http://rs.tdwg.org/dwc/terms/eventID",
                        },
                    ],
                }
            ],
        },
    }
    rules = {
        "relationships": [
            {
                "child_row_type": "Occurrence",
                "child_column": "event_ref",
                "parent_row_type": "Event",
                "parent_column": "event_key",
            }
        ]
    }
    profile_file = tmp_path / "profile.json"
    rules_file = tmp_path / "rules.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    rules_file.write_text(json.dumps(rules), encoding="utf-8")

    def materialize(_project, _run_id, _profile, _metadata, _projection, _rules, dest):
        dest.mkdir(parents=True)
        for name, header, rows in (
            ("Event", ["eventID"], [["e1"]]),
            ("Occurrence", ["occurrenceID", "eventID"], [["o1", "e1"]]),
        ):
            with (dest / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(header)
                writer.writerows(rows)
        (dest / "manifest.json").write_text("{}", encoding="utf-8")
        return {"artifacts": []}

    monkeypatch.setattr(
        "fairmorph_engine.core.publication_adapters.materialize_publication_tables",
        materialize,
    )
    output = tmp_path / "export"
    result = export_dwca(
        tmp_path,
        "synthetic",
        profile_file,
        tmp_path / "metadata.json",
        tmp_path / "projection.json",
        rules_file,
        output,
    )
    assert result["archive_structure_verified"]
    with zipfile.ZipFile(output / "dwca.zip") as archive:
        assert set(archive.namelist()) == {"Event.csv", "Occurrence.csv", "meta.xml"}
        root = etree.fromstring(archive.read("meta.xml"))
        ns = {"d": DWC_TEXT}
        assert root.find("d:core", ns).get("rowType").endswith("/Event")
        assert root.find("d:extension/d:coreid", ns).get("index") == "1"


def test_eml_requires_declared_intent_and_xsd(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "fairmorph_engine.core.publication_adapters.validate_publication_intent",
        lambda *_args: {"formats": ["eml/2.2.0"]},
    )
    with pytest.raises(ValueError, match="XSD"):
        export_eml(
            tmp_path,
            "synthetic",
            tmp_path / "profile.json",
            tmp_path / "metadata.json",
            tmp_path / "missing.xsd",
            tmp_path / "export",
        )
