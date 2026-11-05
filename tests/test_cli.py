import pytest
from lxml import etree
from pydantic import ValidationError

from fairmorph_engine.core.eml_compiler import EML_NS, compile_eml_xml
from fairmorph_engine.models.eml import (
    Agent,
    GeographicBoundingBox,
    LicenseEnum,
    ProjectMetadata,
)


@pytest.fixture
def sample_metadata() -> ProjectMetadata:
    return ProjectMetadata(
        project_id="urn:uuid:6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        dataset_version="1.0.0",
        title="Benthic Coral Coverage Moorea",
        abstract="Long-term benthic survey across the barrier reef crest.",
        language="eng",
        license=LicenseEnum.CC_BY_4_0,
        creators=[
            Agent(
                given_name="Jane",
                surname="Doe",
                organization="CRIOBE",
                email="jane.doe@criobe.pf",
                orcid="0000-0002-1825-0097",
            )
        ],
        contacts=[
            Agent(
                given_name="Jane",
                surname="Doe",
                email="jane.doe@criobe.pf",
            )
        ],
        geographic_coverage=GeographicBoundingBox(
            description="Moorea North Shore",
            west_bounding_coordinate=-149.85,
            east_bounding_coordinate=-149.80,
            north_bounding_coordinate=-17.48,
            south_bounding_coordinate=-17.52,
        ),
    )


def test_orcid_normalization(sample_metadata: ProjectMetadata):
    assert sample_metadata.creators[0].orcid == "https://orcid.org/0000-0002-1825-0097"


def test_invalid_orcid():
    with pytest.raises(ValidationError):
        Agent(given_name="Bad", surname="Orcid", orcid="invalid-orcid-id")


def test_invalid_latitudes():
    with pytest.raises(ValidationError):
        GeographicBoundingBox(
            description="Invalid BBox",
            west_bounding_coordinate=-149.85,
            east_bounding_coordinate=-149.80,
            north_bounding_coordinate=-17.52,
            south_bounding_coordinate=-17.48,  # south > north
        )


def test_eml_compilation(sample_metadata: ProjectMetadata):
    xml_bytes = compile_eml_xml(sample_metadata)
    assert xml_bytes.startswith(b"<?xml")

    root = etree.fromstring(xml_bytes)
    assert root.tag == f"{{{EML_NS}}}eml"
    assert root.attrib["packageId"] == "urn:uuid:6ba7b810-9dad-11d1-80b4-00c04fd430c8/v1.0.0"

    title_el = root.find(".//dataset/title")
    assert title_el is not None
    assert title_el.text == "Benthic Coral Coverage Moorea"

    creator_id = root.find(".//dataset/creator/userId")
    assert creator_id is not None
    assert creator_id.text == "https://orcid.org/0000-0002-1825-0097"
