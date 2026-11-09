"""Reproduce the published CS-PHOC Event-core / Occurrence-extension profile.

Reference implementation: https://github.com/us-amlr/cs-phoc/blob/main/R/data_to_dwca.R
The original publisher's scholarly semantic interpretation takes precedence over
FAIRmorph's generic measurement model. No network calls are made.
"""

import csv
import json
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from csphoc import COUNT_FIELDS, EXPECTED_COUNTS, EXPECTED_EVENTS, read_rows

DWC = "http://rs.tdwg.org/dwc/terms/"
DWC_TEXT = "http://rs.tdwg.org/dwc/text/"
EML = "https://eml.ecoinformatics.org/eml-2.2.0"

PUBLISHED_DOI = "https://doi.org/10.48361/gklk1u"
PAPER_DOI = "https://doi.org/10.1038/s41597-024-03744-9"
PUBLISHER = "SCAR - AntOBIS"
PUBLISHER_ID = "https://www.gbif.org/publisher/104e9c96-791b-4f14-978c-f581cb214912"
LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"
GEOGRAPHY = "Antarctica | South Shetland Islands | Cape Shirreff, Livingston Island"
GAZETTEER = "https://data.aad.gov.au/aadc/gaz/scar/display_name.cfm?gaz_id=131551"

EVENT_COLUMNS = [
    "eventID",
    "surveyed_pst",
    "decimalLongitude",
    "decimalLatitude",
    "locality",
    "locationRemarks",
    "eventDate",
    "eventRemarks",
    "sampleSizeValue",
    "sampleSizeUnit",
    "dynamicProperties",
    "coordinateUncertaintyInMeters",
    "higherGeography",
    "higherGeographyID",
    "continent",
    "countryCode",
    "geodeticDatum",
    "samplingProtocol",
]
OCCURRENCE_COLUMNS = [
    "occurrenceID",
    "eventID",
    "location",
    "scientificName",
    "vernacularName",
    "scientificNameID",
    "taxonRank",
    "kingdom",
    "basisOfRecord",
    "identificationReferences",
    "lifeStage",
    "sex",
    "individualCount",
    "occurrenceStatus",
    "dateIdentified",
]

# Published by the authors in data/dwca/occurrence.txt (snapshot 2026-11-07).
# Never derive the WoRMS identifiers from the unrelated source count_id suffix.
PUBLISHED_TAXA = {
    "Lobodon carcinophaga": "urn:lsid:marinespecies.org:taxname:231416",
    "Mirounga leonina": "urn:lsid:marinespecies.org:taxname:231413",
    "Hydrurga leptonyx": "urn:lsid:marinespecies.org:taxname:231417",
    "Leptonychotes weddellii": "urn:lsid:marinespecies.org:taxname:195932",
}

AGE_CODE = {"adult": 1, "juvenile": 2, "pup": 3, "unknown": 4}
SEX_CODE = {"female": 1, "male": 2, "unknown": 3, "unspecified": 3}
SITE = {
    "Core census locations": (
        "1",
        "-60.77",
        "-62.47",
        "Cape Shirreff, Livingston Island",
        "CS-PHOC core census locations, on Cape Shirreff",
    ),
    "Punta San Telmo": (
        "2",
        "-60.808",
        "-62.4835",
        "Punta San Telmo, Cape Shirreff, Livingston Island",
        "CS-PHOC location Punta San Telmo, on Cape Shirreff",
    ),
}
CREATORS = [
    ("Samuel M.", "Woodman"),
    ("Renato", "Borras-Chavez"),
    ("Michael E.", "Goebel"),
    ("Daniel", "Torres"),
    ("Anelio", "Aguayo"),
    ("Douglas J.", "Krause"),
]


def published_records(events_source: Path, counts_source: Path) -> tuple[list[dict], list[dict]]:
    """Derive published-style rows from pinned sources, validating references and counts."""
    events = []
    event_by_id = {}
    for _, source in read_rows(events_source, EXPECTED_EVENTS):
        event_id = source["event_id"]
        if event_id in event_by_id:
            raise ValueError(f"Duplicate event_id: {event_id}")
        if source["surveyed_pst"] not in {"TRUE", "FALSE"}:
            raise ValueError(f"Unrecognised surveyed_pst: {event_id}")
        event_by_id[event_id] = source
        site_names = ["Core census locations"]
        if source["surveyed_pst"] == "TRUE":
            site_names.append("Punta San Telmo")
        for site in site_names:
            suffix, longitude, latitude, locality, remarks = SITE[site]
            days = int(source["census_days"])
            if days < 1 or source["census_date_start"] > source["census_date_end"]:
                raise ValueError(f"Invalid census interval: {event_id}")
            events.append(
                {
                    "eventID": f"{event_id}-{suffix}",
                    "surveyed_pst": source["surveyed_pst"],
                    "decimalLongitude": longitude,
                    "decimalLatitude": latitude,
                    "locality": locality,
                    "locationRemarks": remarks,
                    "eventDate": source["census_date_start"],
                    "eventRemarks": (
                        ""
                        if days == 1
                        else "The census event spanned multiple days. "
                        "The reported date is the start of the census event window"
                    ),
                    "sampleSizeValue": str(days),
                    "sampleSizeUnit": "day" if days == 1 else "days",
                    "dynamicProperties": json.dumps(
                        {"research_program": source["research_program"]}
                    ),
                    "coordinateUncertaintyInMeters": "2650",
                    "higherGeography": GEOGRAPHY,
                    "higherGeographyID": GAZETTEER,
                    "continent": "Antarctica",
                    "countryCode": "AQ",
                    "geodeticDatum": "EPSG:4326",
                    "samplingProtocol": PAPER_DOI,
                }
            )

    event_dates = {row["eventID"]: row["eventDate"] for row in events}
    occurrences = []
    seen_ids = set()
    for line, source in read_rows(counts_source, EXPECTED_COUNTS):
        original_event_id = source["event_id"]
        if original_event_id not in event_by_id:
            raise ValueError(f"Unknown source event at line {line}")
        if source["location"] not in SITE:
            raise ValueError(f"Unknown census location at line {line}")
        suffix = SITE[source["location"]][0]
        event_id = f"{original_event_id}-{suffix}"
        if event_id not in event_dates:
            raise ValueError(f"Site not surveyed for event {event_id}")
        if not source["count_id"].startswith(f"{event_id}-"):
            raise ValueError(f"Count identifier does not reference event {event_id}")
        if source["species"] not in PUBLISHED_TAXA:
            raise ValueError(f"Species not in approved published taxonomy: {source['species']}")
        values = []
        for column, (stage, sex) in COUNT_FIELDS.items():
            raw = source[column]
            if not raw:
                continue
            if not raw.isascii() or not raw.isdecimal() or (len(raw) > 1 and raw[0] == "0"):
                raise ValueError(f"Invalid count in {column} at line {line}")
            value = int(raw)
            values.append(value)
            occurrence_id = f"{source['count_id']}-{AGE_CODE[stage]}-{SEX_CODE[sex]}"
            if occurrence_id in seen_ids:
                raise ValueError(f"Duplicate occurrenceID: {occurrence_id}")
            seen_ids.add(occurrence_id)
            occurrences.append(
                {
                    "occurrenceID": occurrence_id,
                    "eventID": event_id,
                    "location": source["location"],
                    "scientificName": source["species"],
                    "vernacularName": source["species_common"],
                    "scientificNameID": PUBLISHED_TAXA[source["species"]],
                    "taxonRank": "Species",
                    "kingdom": "Animalia",
                    "basisOfRecord": "HumanObservation",
                    "individualCount": str(value),
                    "occurrenceStatus": "absent" if value == 0 else "present",
                    "lifeStage": stage,
                    "sex": "indeterminate" if sex in {"unknown", "unspecified"} else sex,
                    "dateIdentified": event_dates[event_id],
                    "identificationReferences": "https://doi.org/10.1016/C2012-0-06919-0",
                }
            )
        if sum(values) != int(source["total_count"]):
            raise ValueError(f"Count total differs from category sum at line {line}")
    if len(event_by_id) != 322 or len(events) != 536 or len(occurrences) != 16940:
        raise ValueError("CS-PHOC reference row counts do not match published profile")
    if len(set(event_dates)) != len(events):
        raise ValueError("Duplicate eventID")
    return events, occurrences


def _append(parent, tag, value=None, **attributes):
    el = ET.SubElement(parent, tag, attributes)
    if value is not None:
        el.text = str(value)
    return el


def derived_eml(export_id: str, start: str, end: str) -> bytes:
    """FAIRmorph-owned derivative metadata; never impersonate the publisher's EML."""
    ET.register_namespace("eml", EML)
    root = ET.Element(
        f"{{{EML}}}eml", {"packageId": f"fairmorph.cs-phoc.{export_id}", "system": "fairmorph"}
    )
    dataset = _append(root, "dataset")
    _append(dataset, "alternateIdentifier", PUBLISHED_DOI)
    _append(dataset, "alternateIdentifier", PUBLISHER_ID)
    _append(
        dataset,
        "title",
        "CS-PHOC: weekly census counts of Southern Ocean phocids at Cape Shirreff, Livingston Island",
    )
    for given, surname in CREATORS:
        creator = _append(dataset, "creator")
        name = _append(creator, "individualName")
        _append(name, "givenName", given)
        _append(name, "surName", surname)
    publisher = _append(dataset, "publisher")
    _append(publisher, "organizationName", PUBLISHER)
    _append(dataset, "pubDate", datetime.now(UTC).date().isoformat())
    _append(dataset, "language", "eng")
    abstract = _append(dataset, "abstract")
    _append(
        abstract,
        "para",
        "A locally derived FAIRmorph archive reproducing the CS-PHOC published event and demographic count structure. Original data and scientific interpretation are attributed to Woodman et al. and SCAR - AntOBIS. This derivative has not been published or endorsed by the original publisher.",
    )
    rights = _append(dataset, "intellectualRights")
    _append(rights, "para", f"Source dataset released under CC0 1.0: {LICENSE}")
    coverage = _append(dataset, "coverage")
    temporal = _append(coverage, "temporalCoverage")
    date_range = _append(temporal, "rangeOfDates")
    beginning = _append(date_range, "beginDate")
    _append(beginning, "calendarDate", start)
    ending = _append(date_range, "endDate")
    _append(ending, "calendarDate", end)
    geographic = _append(coverage, "geographicCoverage")
    _append(
        geographic,
        "geographicDescription",
        "Cape Shirreff, Livingston Island, South Shetland Islands, Antarctica",
    )
    bounding = _append(geographic, "boundingCoordinates")
    for name, value in (
        ("westBoundingCoordinate", "-60.808"),
        ("eastBoundingCoordinate", "-60.77"),
        ("northBoundingCoordinate", "-62.47"),
        ("southBoundingCoordinate", "-62.4835"),
    ):
        _append(bounding, name, value)
    methods = _append(dataset, "methods")
    sampling = _append(methods, "methodStep")
    description = _append(sampling, "description")
    _append(
        description,
        "para",
        f"Reference survey methodology: Woodman et al. (2024), {PAPER_DOI}. FAIRmorph converts the published source counts to individual Darwin Core Occurrence category records; explicit zeros represent absent category counts and missing cells are omitted.",
    )
    contact = _append(dataset, "contact")
    _append(contact, "organizationName", PUBLISHER)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _meta_section(root, kind: str, file: str, columns: list[str]):
    element = ET.SubElement(
        root,
        f"{{{DWC_TEXT}}}{kind}",
        {
            "encoding": "UTF-8",
            "fieldsTerminatedBy": "\\t",
            "linesTerminatedBy": "\\n",
            "fieldsEnclosedBy": '"',
            "ignoreHeaderLines": "1",
            "rowType": DWC + ("Event" if kind == "core" else "Occurrence"),
        },
    )
    files = ET.SubElement(element, f"{{{DWC_TEXT}}}files")
    _append(files, f"{{{DWC_TEXT}}}location", file)
    id_tag = "id" if kind == "core" else "coreid"
    ET.SubElement(element, f"{{{DWC_TEXT}}}{id_tag}", {"index": str(columns.index("eventID"))})
    for index, column in enumerate(columns):
        # These are original CS-PHOC auxiliary columns, not Darwin Core terms.
        # Preserve their tabular values without inventing a non-existent term URI.
        if column in {"surveyed_pst", "location"}:
            continue
        ET.SubElement(element, f"{{{DWC_TEXT}}}field", {"index": str(index), "term": DWC + column})


def archive_metadata_xml() -> bytes:
    ET.register_namespace("", DWC_TEXT)
    root = ET.Element(f"{{{DWC_TEXT}}}archive", {"metadata": "eml.xml"})
    _meta_section(root, "core", "event.txt", EVENT_COLUMNS)
    _meta_section(root, "extension", "occurrence.txt", OCCURRENCE_COLUMNS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_table(path: Path, columns: list[str], records: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_archive(
    package_dir: Path, export_id: str, events: list[dict], occurrences: list[dict]
) -> dict:
    """Generate interoperable text archive, metadata and a portable ZIP."""
    if len(events) != 536 or len(occurrences) != 16940:
        raise ValueError("Cannot publish an incomplete CS-PHOC Darwin Core Archive")
    event_set = {row["eventID"] for row in events}
    if any(row["eventID"] not in event_set for row in occurrences):
        raise ValueError("Occurrence references unknown Event")
    if Counter(row["occurrenceStatus"] for row in occurrences) != {
        "absent": 11599,
        "present": 5341,
    }:
        raise ValueError("Unexpected occurrence-status totals")
    _write_table(package_dir / "event.txt", EVENT_COLUMNS, events)
    _write_table(package_dir / "occurrence.txt", OCCURRENCE_COLUMNS, occurrences)
    (package_dir / "meta.xml").write_bytes(archive_metadata_xml())
    dates = sorted(row["eventDate"] for row in events)
    (package_dir / "eml.xml").write_bytes(derived_eml(export_id, dates[0], dates[-1]))
    archive = package_dir / "cs-phoc-dwca.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipper:
        for name in ("event.txt", "occurrence.txt", "meta.xml", "eml.xml"):
            zipper.write(package_dir / name, arcname=name)
    return {
        "event_rows": len(events),
        "occurrence_rows": len(occurrences),
        "absent_records": 11599,
        "present_records": 5341,
        "archive_path": archive.name,
        "source_doi": PUBLISHED_DOI,
        "metadata_provenance": "FAIRmorph-derived; not publisher's original EML",
    }
