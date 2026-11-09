"""Offline EML 2.2.0 conformance proof using the official vendored XSD bundle."""

import json
from pathlib import Path

import pytest
from lxml import etree

from fairmorph_engine.core.eml_compiler import compile_eml_xml
from fairmorph_engine.core.publication_adapters import export_eml
from fairmorph_engine.models.eml import ProjectMetadata

SCHEMA = (
    Path(__file__).resolve().parents[1] / "vendor/schemas/eml/2.2.0/eml.xsd"
)


def _metadata():
    return {
        "project_id": "urn:uuid:11111111-2222-4333-8444-555555555555",
        "dataset_version": "1.0.0",
        "title": "Synthetic observation dataset",
        "abstract": "A fully synthetic dataset for testing offline EML schema validation.",
        "language": "eng",
        "creators": [{"given_name": "Ada", "surname": "Example"}],
        "contacts": [{"given_name": "Ada", "surname": "Example"}],
        "geographic_coverage": {
            "description": "Fictional testing region",
            "west_bounding_coordinate": 10.0,
            "east_bounding_coordinate": 11.0,
            "north_bounding_coordinate": 52.0,
            "south_bounding_coordinate": 51.0,
        },
        "publication_date": "2026-01-01",
    }


def test_official_eml_schema_validates_deterministic_xml():
    schema = etree.XMLSchema(etree.parse(str(SCHEMA)))
    metadata = _metadata()
    xml_a = compile_eml_xml(
        ProjectMetadata.model_validate(metadata), publication_date=metadata["publication_date"]
    )
    xml_b = compile_eml_xml(
        ProjectMetadata.model_validate(metadata), publication_date=metadata["publication_date"]
    )
    assert xml_a == xml_b
    schema.assertValid(etree.fromstring(xml_a))


def test_official_eml_schema_rejects_invalid_document():
    schema = etree.XMLSchema(etree.parse(str(SCHEMA)))
    metadata = _metadata()
    xml = compile_eml_xml(
        ProjectMetadata.model_validate(metadata), publication_date=metadata["publication_date"]
    )
    root = etree.fromstring(xml)
    dataset = root.find("dataset")
    dataset.remove(dataset.find("title"))
    with pytest.raises(etree.DocumentInvalid):
        schema.assertValid(root)


def test_eml_adapter_validates_and_pins_official_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "fairmorph_engine.core.publication_adapters.validate_publication_intent",
        lambda *_args: {"formats": ["eml/2.2.0"]},
    )
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text(json.dumps(_metadata()), encoding="utf-8")
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps({"run_manifest_sha256": "a" * 64}), encoding="utf-8")
    first = export_eml(
        tmp_path, "synthetic-run", profile_file, metadata_file, SCHEMA, tmp_path / "first"
    )
    second = export_eml(
        tmp_path, "synthetic-run", profile_file, metadata_file, SCHEMA, tmp_path / "second"
    )
    assert first == second
    assert first["schema_validated"] is True
    assert (tmp_path / "first/eml.xml").read_bytes() == (tmp_path / "second/eml.xml").read_bytes()
