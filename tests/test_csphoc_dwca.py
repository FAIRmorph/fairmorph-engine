"""Scientific regression checks for the author-defined CS-PHOC DwC-A profile."""

import csv
import json
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from fairmorph_engine.core.dwca import (
    DWC,
    DWC_TEXT,
    EML,
    EVENT_COLUMNS,
    OCCURRENCE_COLUMNS,
    PUBLISHED_DOI,
    archive_metadata_xml,
    derived_eml,
    published_records,
    write_archive,
)

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "cs-phoc"


@pytest.fixture(scope="module")
def reference_rows():
    return published_records(FIXTURE / "cs-phoc-events.csv", FIXTURE / "cs-phoc-counts.csv")


def test_published_reference_cardinality_and_zero_semantics(reference_rows):
    events, occurrences = reference_rows
    assert len(events) == 536
    assert len(occurrences) == 16940
    assert len({row["eventID"] for row in events}) == 536
    assert len({row["occurrenceID"] for row in occurrences}) == 16940
    assert {row["eventID"] for row in occurrences} == {row["eventID"] for row in events}
    assert Counter(row["occurrenceStatus"] for row in occurrences) == {
        "absent": 11599,
        "present": 5341,
    }
    assert sum(int(row["individualCount"]) for row in occurrences) == 79232
    assert all(
        (int(row["individualCount"]) == 0) == (row["occurrenceStatus"] == "absent")
        for row in occurrences
    )
    assert set(row["lifeStage"] for row in occurrences) == {"adult", "juvenile", "pup", "unknown"}
    assert set(row["sex"] for row in occurrences) == {"female", "male", "indeterminate"}


def test_original_identifier_and_site_mapping(reference_rows):
    events, occurrences = reference_rows
    by_id = {row["eventID"]: row for row in events}
    assert by_id["185-1"]["eventDate"] == "1997-12-10"
    assert by_id["185-1"]["decimalLatitude"] == "-62.47"
    assert by_id["185-1"]["decimalLongitude"] == "-60.77"
    assert by_id["1-2"]["decimalLatitude"] == "-62.4835"
    assert by_id["1-2"]["decimalLongitude"] == "-60.808"
    occurrence = next(row for row in occurrences if row["occurrenceID"] == "1-1-344008-1-1")
    assert occurrence["scientificName"] == "Lobodon carcinophaga"
    assert occurrence["individualCount"] == "0"
    assert occurrence["occurrenceStatus"] == "absent"
    assert occurrence["basisOfRecord"] == "HumanObservation"
    assert "total_count" not in occurrence
    assert not any(row["eventID"] == "185" for row in events)


def test_archive_manifest_eml_and_references(tmp_path, reference_rows):
    events, occurrences = reference_rows
    result = write_archive(tmp_path, "20261107T010000Z-a1b2c3d4e5f6", events, occurrences)
    assert result["event_rows"] == 536
    assert result["occurrence_rows"] == 16940
    with zipfile.ZipFile(tmp_path / "cs-phoc-dwca.zip") as archive:
        assert set(archive.namelist()) == {"event.txt", "occurrence.txt", "meta.xml", "eml.xml"}
        event_lines = list(
            csv.DictReader(archive.read("event.txt").decode().splitlines(), delimiter="\t")
        )
        occurrence_lines = list(
            csv.DictReader(archive.read("occurrence.txt").decode().splitlines(), delimiter="\t")
        )
        assert len(event_lines) == 536
        assert len(occurrence_lines) == 16940
        assert list(event_lines[0]) == EVENT_COLUMNS
        assert list(occurrence_lines[0]) == OCCURRENCE_COLUMNS
        meta = ET.fromstring(archive.read("meta.xml"))
        core = meta.find(f"{{{DWC_TEXT}}}core")
        extension = meta.find(f"{{{DWC_TEXT}}}extension")
        assert core.attrib["rowType"] == DWC + "Event"
        assert extension.attrib["rowType"] == DWC + "Occurrence"
        assert core.find(f"{{{DWC_TEXT}}}id").attrib["index"] == "0"
        assert extension.find(f"{{{DWC_TEXT}}}coreid").attrib["index"] == "1"
        eml = ET.fromstring(archive.read("eml.xml"))
        assert eml.tag == f"{{{EML}}}eml"
        assert eml.attrib["packageId"].startswith("fairmorph.cs-phoc.")
        assert PUBLISHED_DOI in archive.read("eml.xml").decode()
        assert "CC0" in archive.read("eml.xml").decode()
    assert ET.fromstring(archive_metadata_xml()) is not None
    assert ET.fromstring(derived_eml("sample", "1997-01-01", "2026-01-01")) is not None


def test_reject_incomplete_archive(tmp_path, reference_rows):
    events, occurrences = reference_rows
    with pytest.raises(ValueError, match="incomplete"):
        write_archive(tmp_path, "test", events[:-1], occurrences)
    assert list(tmp_path.iterdir()) == []


def test_dwca_preflight_cli():
    import subprocess
    import sys

    response = subprocess.run(
        [sys.executable, "-m", "fairmorph_engine.cli", "dwca-preflight"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    doc = json.loads(response.stdout.splitlines()[-1])
    assert doc["status"] == "success"
    assert doc["data"]["core_rows"] == 536
    assert doc["data"]["extension_rows"] == 16940


def test_dwca_export_is_integrity_checked_and_does_not_modify_run(tmp_path, monkeypatch):
    """Exercise the publication lifecycle without pretending mock data are Parquet bytes."""
    import sys
    from types import SimpleNamespace

    from fairmorph_engine.core.csphoc import run_slice, sha256
    from fairmorph_engine.core.export import export_dwca, verified_run, verify_project

    class FakeFrame:
        def __init__(self, rows=None, schema=None):
            self.rows = rows or []

        def write_parquet(self, path):
            Path(path).write_text(json.dumps(self.rows), encoding="utf-8")

        def to_dicts(self):
            return self.rows

    fake = SimpleNamespace(
        DataFrame=FakeFrame,
        read_parquet=lambda path: FakeFrame(
            rows=json.loads(Path(path).read_text(encoding="utf-8"))
        ),
        Int64="i64",
        String="str",
    )
    monkeypatch.setitem(sys.modules, "polars", fake)
    project = tmp_path / "project.fairmorph"
    output = []

    def emit(event, **kwargs):
        return output.append({"event": event, **kwargs})

    run_slice(
        project,
        FIXTURE / "cs-phoc-events.csv",
        FIXTURE / "cs-phoc-counts.csv",
        FIXTURE / "decision.json",
        emit,
    )
    run_id = output[-1]["data"]["run_id"]
    run_dir, _ = verified_run(project, run_id)
    original_manifest_hash = sha256(run_dir / "manifest.json")
    result = export_dwca(project, run_id, emit)
    assert result["event_rows"] == 536
    assert result["occurrence_rows"] == 16940
    assert sha256(run_dir / "manifest.json") == original_manifest_hash
    assert verify_project(project)["exports"] == 1
    archive = Path(result["export_path"]) / "package" / "cs-phoc-dwca.zip"
    assert zipfile.is_zipfile(archive)
    archive.write_bytes(archive.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="modified export artifact"):
        verify_project(project)


def test_export_rejects_modified_run_payload_even_if_manifest_rehashed(tmp_path, monkeypatch):
    """An attacker cannot replace the observations parquet with a different valid table."""
    import sys
    from types import SimpleNamespace

    from fairmorph_engine.core.csphoc import run_slice, sha256
    from fairmorph_engine.core.export import export_dwca

    class FakeFrame:
        def __init__(self, rows=None, schema=None):
            self.rows = rows or []

        def write_parquet(self, path):
            Path(path).write_text(json.dumps(self.rows), encoding="utf-8")

        def to_dicts(self):
            return self.rows

    monkeypatch.setitem(
        sys.modules,
        "polars",
        SimpleNamespace(
            DataFrame=FakeFrame,
            read_parquet=lambda path: FakeFrame(
                rows=json.loads(Path(path).read_text(encoding="utf-8"))
            ),
            Int64="i64",
            String="str",
        ),
    )
    project = tmp_path / "project.fairmorph"
    output = []

    def emit(event, **kwargs):
        return output.append({"event": event, **kwargs})

    run_slice(
        project,
        FIXTURE / "cs-phoc-events.csv",
        FIXTURE / "cs-phoc-counts.csv",
        FIXTURE / "decision.json",
        emit,
    )
    run_id = output[-1]["data"]["run_id"]
    run_dir = project / "runs" / run_id
    observations = run_dir / "outputs" / "observations.parquet"
    altered = json.loads(observations.read_text(encoding="utf-8"))
    altered[0]["value"] = 999
    observations.write_text(json.dumps(altered), encoding="utf-8")
    manifest_file = run_dir / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        if artifact["path"] == "outputs/observations.parquet":
            artifact["sha256"] = sha256(observations)
            artifact["bytes"] = observations.stat().st_size
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from approved source transformation"):
        export_dwca(project, run_id, emit)
    assert not list((project / "exports").glob("*/export-manifest.json"))


def test_published_author_table_fingerprints(reference_rows, tmp_path):
    """Order-independent fingerprints derived from original author tables at pinned Git blobs.

    Source: us-amlr/cs-phoc at commit 64f0b77e631c711c681306bbb56a7636ae91a471.
    FNV fingerprints are regression sentinels, not security hashes; integrity is SHA-256.
    The author's Event TSV omits enclosing quotes for the JSON column, whereas
    FAIRmorph quotes it as a CSV/TSV-escaped cell; the parsed contents match.
    """
    events, occurrences = reference_rows
    write_archive(tmp_path, "fingerprint", events, occurrences)

    def fingerprint(lines):
        total = 0
        xor = 0
        for line in lines:
            value = 2166136261
            for char in line:
                value = ((value ^ ord(char)) * 16777619) & 0xFFFFFFFF
            total = (total + value) & 0xFFFFFFFF
            xor ^= value
        return total, xor

    for file, expected in (
        ("event.txt", (1146929489, 2076352101)),
        ("occurrence.txt", (1992734649, 2063770683)),
    ):
        with (tmp_path / file).open(encoding="utf-8") as stream:
            next(stream)
            assert fingerprint(line.rstrip("\n") for line in stream) == expected
