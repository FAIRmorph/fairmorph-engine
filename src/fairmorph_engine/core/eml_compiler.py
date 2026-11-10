from datetime import UTC, datetime

from lxml import etree

from fairmorph_engine.models.eml import ProjectMetadata

EML_NS = "https://eml.ecoinformatics.org/eml-2.2.0"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
NSMAP = {"eml": EML_NS, "xsi": XSI_NS}


def compile_eml_xml(meta: ProjectMetadata, publication_date: str | None = None) -> bytes:
    dataset_urn = f"{meta.project_id}/v{meta.dataset_version}"

    root = etree.Element(
        f"{{{EML_NS}}}eml",
        nsmap=NSMAP,
        attrib={
            "packageId": dataset_urn,
            "system": "fairmorph",
            "scope": "system",
            f"{{{XSI_NS}}}schemaLocation": f"{EML_NS} https://eml.ecoinformatics.org/eml-2.2.0/eml.xsd",
        },
    )

    dataset = etree.SubElement(root, "dataset")
    etree.SubElement(dataset, "title").text = meta.title

    for c in meta.creators:
        creator_el = etree.SubElement(dataset, "creator")
        if c.orcid:
            creator_el.set("id", c.orcid)
        ind_name = etree.SubElement(creator_el, "individualName")
        etree.SubElement(ind_name, "givenName").text = c.given_name
        etree.SubElement(ind_name, "surName").text = c.surname
        if c.organization:
            etree.SubElement(creator_el, "organizationName").text = c.organization
        if c.email:
            etree.SubElement(creator_el, "electronicMailAddress").text = c.email
        if c.orcid:
            user_id = etree.SubElement(creator_el, "userId", directory="https://orcid.org/")
            user_id.text = c.orcid

    etree.SubElement(dataset, "pubDate").text = publication_date or datetime.now(UTC).strftime(
        "%Y-%m-%d"
    )
    etree.SubElement(dataset, "language").text = meta.language

    abstract_el = etree.SubElement(dataset, "abstract")
    para = etree.SubElement(abstract_el, "para")
    para.text = meta.abstract

    rights_el = etree.SubElement(dataset, "intellectualRights")
    rights_para = etree.SubElement(rights_el, "para")
    rights_para.text = f"This work is licensed under {meta.license.name} ({meta.license.value})."

    coverage = etree.SubElement(dataset, "coverage")
    geo = etree.SubElement(coverage, "geographicCoverage")
    etree.SubElement(geo, "geographicDescription").text = meta.geographic_coverage.description
    box = etree.SubElement(geo, "boundingCoordinates")
    etree.SubElement(box, "westBoundingCoordinate").text = str(
        meta.geographic_coverage.west_bounding_coordinate
    )
    etree.SubElement(box, "eastBoundingCoordinate").text = str(
        meta.geographic_coverage.east_bounding_coordinate
    )
    etree.SubElement(box, "northBoundingCoordinate").text = str(
        meta.geographic_coverage.north_bounding_coordinate
    )
    etree.SubElement(box, "southBoundingCoordinate").text = str(
        meta.geographic_coverage.south_bounding_coordinate
    )

    for ct in meta.contacts:
        contact_el = etree.SubElement(dataset, "contact")
        ind_name = etree.SubElement(contact_el, "individualName")
        etree.SubElement(ind_name, "givenName").text = ct.given_name
        etree.SubElement(ind_name, "surName").text = ct.surname
        if ct.email:
            etree.SubElement(contact_el, "electronicMailAddress").text = ct.email

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")
