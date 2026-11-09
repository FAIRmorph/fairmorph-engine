"""PoC EML and Darwin Core Archive adapters driven by external project artifacts."""

import csv
import json
from datetime import date
import zipfile
from pathlib import Path

from lxml import etree

from fairmorph_engine.core.eml_compiler import compile_eml_xml
from fairmorph_engine.core.export import sha256
from fairmorph_engine.core.publication import validate_publication_intent
from fairmorph_engine.core.publication_materialize import materialize_publication_tables
from fairmorph_engine.models.eml import ProjectMetadata

DWC = "http://rs.tdwg.org/dwc/terms/"
DWC_TEXT = "http://rs.tdwg.org/dwc/text/"


def export_eml(
    project: Path,
    run_id: str,
    profile_file: Path,
    metadata_file: Path,
    schema_file: Path,
    destination: Path,
) -> dict:
    """Validate EML with a caller-provided official EML 2.2.0 XSD (offline)."""
    intent = validate_publication_intent(project, run_id, profile_file, metadata_file)
    if "eml/2.2.0" not in intent["formats"]:
        raise ValueError("EML is not declared in publication intent")
    if not schema_file.is_file():
        raise ValueError("EML 2.2.0 XSD must be provided")
    raw_metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    if "publication_date" not in raw_metadata:
        raise ValueError("EML metadata requires explicit publication_date for reproducibility")
    publication_date = date.fromisoformat(raw_metadata["publication_date"]).isoformat()
    metadata = ProjectMetadata.model_validate(raw_metadata)
    xml = compile_eml_xml(metadata, publication_date=publication_date)
    schema = etree.XMLSchema(etree.parse(str(schema_file)))
    schema.assertValid(etree.fromstring(xml))
    if destination.exists():
        raise ValueError("EML destination already exists")
    destination.mkdir(parents=True)
    target = destination / "eml.xml"
    target.write_bytes(xml)
    result = {
        "format": "eml/2.2.0",
        "source_run_id": run_id,
        "run_manifest_sha256": json.loads(profile_file.read_text(encoding="utf-8"))[
            "run_manifest_sha256"
        ],
        "publication_profile_sha256": sha256(profile_file),
        "metadata_sha256": sha256(metadata_file),
        "schema_sha256": sha256(schema_file),
        "eml_sha256": sha256(target),
        "schema_validated": True,
    }
    (destination / "manifest.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return result


def export_dwca(
    project: Path,
    run_id: str,
    profile_file: Path,
    metadata_file: Path,
    projection_file: Path,
    integrity_file: Path,
    destination: Path,
) -> dict:
    """Produce a Darwin Core text archive with externally declared core and extensions."""
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    if "dwca/1" not in profile["formats"]:
        raise ValueError("DwC-A is not declared in publication intent")
    if destination.exists():
        raise ValueError("DwC-A destination already exists")
    tables_dir = destination / "tables"
    tables_manifest = materialize_publication_tables(
        project, run_id, profile_file, metadata_file, projection_file, integrity_file, tables_dir
    )
    dwca = profile["dwca"]
    rules = json.loads(integrity_file.read_text(encoding="utf-8"))
    core_type = dwca["core"]
    core_name = f"{core_type}.csv"
    core_field = f"{core_type.lower()}ID"
    declared = [(core_type, dwca["core_fields"])]
    declared.extend(
        (item["row_type"], item["fields"]) for item in dwca.get("extensions", [])
    )
    root = etree.Element(f"{{{DWC_TEXT}}}archive", nsmap={None: DWC_TEXT})
    for index, (row_type, fields) in enumerate(declared):
        row_type_tag = "core" if index == 0 else "extension"
        element = etree.SubElement(
            root,
            f"{{{DWC_TEXT}}}{row_type_tag}",
            encoding="UTF-8",
            fieldsTerminatedBy=",",
            linesTerminatedBy="\\n",
            fieldsEnclosedBy='"',
            ignoreHeaderLines="1",
            rowType=f"http://rs.tdwg.org/dwc/terms/{row_type}",
        )
        files = etree.SubElement(element, f"{{{DWC_TEXT}}}files")
        etree.SubElement(files, f"{{{DWC_TEXT}}}location").text = f"{row_type}.csv"
        if index == 0:
            core_index = next(
            i for i, field in enumerate(fields) if field["term"] == DWC + core_field
        )
        etree.SubElement(element, f"{{{DWC_TEXT}}}id", index=str(core_index))
        else:
            relationships = [
                rule for rule in rules["relationships"]
                if rule["child_row_type"] == row_type
                and rule["parent_row_type"] == core_type
            ]
            if len(relationships) != 1:
                raise ValueError("Each extension needs one declared relationship to the core")
            foreign = relationships[0]["child_column"]
            projected = {item["source_field"]: i for i, item in enumerate(fields)}
            if foreign not in projected:
                raise ValueError("Extension core foreign key must be mapped to an output column")
            etree.SubElement(element, f"{{{DWC_TEXT}}}coreid", index=str(projected[foreign]))
        for i, field in enumerate(fields):
            etree.SubElement(element, f"{{{DWC_TEXT}}}field", index=str(i), term=field["term"])
    metadata_xml = destination / "meta.xml"
    metadata_xml.write_bytes(
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    )
    archive = destination / "dwca.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for row_type, _ in declared:
            file = tables_dir / f"{row_type}.csv"
            info = zipfile.ZipInfo(f"{row_type}.csv", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, file.read_bytes())
        info = zipfile.ZipInfo("meta.xml", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        package.writestr(info, metadata_xml.read_bytes())
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError("DwC-A ZIP integrity check failed")
        if set(package.namelist()) != {"meta.xml", *(f"{row_type}.csv" for row_type, _ in declared)}:
            raise ValueError("DwC-A archive structure differs from declared tables")
        etree.fromstring(package.read("meta.xml"))
        for row_type, fields in declared:
            rows = list(csv.reader(package.read(f"{row_type}.csv").decode("utf-8").splitlines()))
            if not rows or len(rows[0]) != len(fields):
                raise ValueError("DwC-A table width differs from metadata")
    result = {
        "format": "dwca/1",
        "source_run_id": run_id,
        "tables_manifest_sha256": sha256(tables_dir / "manifest.json"),
        "meta_xml_sha256": sha256(metadata_xml),
        "archive_sha256": sha256(archive),
        "tables": tables_manifest["artifacts"],
        "archive_structure_verified": True,
    }
    (destination / "manifest.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return result
