"""Acceptance tests for the approved, fixed CS-PHOC PoC."""

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from fairmorph_engine.core.csphoc import (
    COUNT_FIELDS,
    PROJECT_VERSION,
    RUN_VERSION,
    sha256,
    transform_sources,
    validate_decision,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "cs-phoc"
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def test_reference_originals_are_unchanged():
    assert sha256(EXAMPLES / "cs-phoc-events.csv") == (
        "4362ae650cb72cc74901f7719920db5c8bbcfdc2ee09842595d04bf5e587bddc"
    )
    assert sha256(EXAMPLES / "cs-phoc-counts.csv") == (
        "be4a28aa5036dea103e9e6bbc6af5fef13d80354ef2750e0960bf78e320c3545"
    )


def test_originals_match_independent_reference_counts():
    records, findings, lineage, counters, event_count = transform_sources(
        EXAMPLES / "cs-phoc-events.csv",
        EXAMPLES / "cs-phoc-counts.csv",
        sha256(EXAMPLES / "cs-phoc-counts.csv"),
    )
    assert event_count == 322
    assert counters["count_rows"] == 2144
    assert counters["empty_cells"] == 4500
    assert counters["zero_cells"] == 11599
    assert counters["positive_cells"] == 5341
    assert len(records) == 16940
    assert len(lineage) == len(records)
    assert findings == []
    assert len({row["record_id"] for row in records}) == len(records)
    assert all(row["source_column"] in COUNT_FIELDS for row in records)
    assert sum(row["value"] == 0 for row in records) == 11599


def test_repeatable_lineage_without_timestamp_or_run_id():
    events = EXAMPLES / "cs-phoc-events.csv"
    counts = EXAMPLES / "cs-phoc-counts.csv"
    digest = sha256(counts)
    a, *_ = transform_sources(events, counts, digest)
    b, *_ = transform_sources(events, counts, digest)
    assert a == b


def test_approved_static_decision_cannot_be_changed_silently():
    approved = json.loads((EXAMPLES / "decision.json").read_text(encoding="utf-8"))
    validate_decision(approved)
    edited = dict(approved, status="suggested")
    with pytest.raises(ValueError, match="user-approved"):
        validate_decision(edited)
    edited = dict(approved, source_columns=["total_count"])
    with pytest.raises(ValueError, match="ten approved"):
        validate_decision(edited)


def test_invalid_source_cells_are_findings_not_implicit_zeroes(tmp_path):
    events = tmp_path / "events.csv"
    counts = tmp_path / "counts.csv"
    events.write_text(
        "event_id,season_name,census_date_start,census_date_end,census_days,surveyed_pst,research_program\n"
        "one,2026,2026-01-01,2026-01-02,2,FALSE,test\n",
        encoding="utf-8",
    )
    header = "count_id,event_id,location,species,species_common,total_count," + ",".join(
        COUNT_FIELDS
    )
    counts.write_text(header + "\n" + "a,one,Site,Seal,Seal,0,abc,,,,,,0,,,\n", encoding="utf-8")
    result, findings, _lineage, stats, _events = transform_sources(events, counts, sha256(counts))
    assert any(item["raw_value"] == "abc" for item in findings)
    assert stats["invalid_cells"] == 1
    assert any(item["value"] == 0 and item["source_value"] == "0" for item in result)
    assert len(result) == 1


def test_missing_event_is_flagged_and_not_joined(tmp_path):
    events = tmp_path / "events.csv"
    counts = tmp_path / "counts.csv"
    events.write_text(
        "event_id,season_name,census_date_start,census_date_end,census_days,surveyed_pst,research_program\n"
        "known,2026,2026-01-01,2026-01-02,2,FALSE,test\n",
        encoding="utf-8",
    )
    header = "count_id,event_id,location,species,species_common,total_count," + ",".join(
        COUNT_FIELDS
    )
    counts.write_text(
        header + "\n" + "a,unknown,Site,Seal,Seal,0," + ",".join(["0"] * 10) + "\n",
        encoding="utf-8",
    )
    result, findings, _lineage, stats, _events = transform_sources(events, counts, sha256(counts))
    assert result == []
    assert findings[0]["issue"] == "missing_or_ambiguous_event"
    assert stats["invalid_events"] == 1


def test_poc_contract_schema_is_valid():
    for path in CONTRACTS.glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
    assert PROJECT_VERSION == "fairmorph.poc.project/1"
    assert RUN_VERSION == "fairmorph.poc.run/1"


def test_project_objects_are_content_addressed_and_deduplicated(tmp_path):
    from fairmorph_engine.core.csphoc import _import_source, _init_catalog

    project = tmp_path / "project.fairmorph"
    project.mkdir()
    _init_catalog(project)
    source = tmp_path / "source.csv"
    source.write_bytes(b"col\n1\n")
    digest, relative = _import_source(project, source)
    digest2, relative2 = _import_source(project, source)
    assert digest == hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest2 == digest and relative2 == relative
    assert len(list((project / "objects").rglob(digest))) == 1
