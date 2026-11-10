"""Real external CS-PHOC profile, no scientific constants inside the Engine."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from fairmorph_engine.core.profile import approve_staged_mapping, stage_csv_mapping
from fairmorph_engine.core.project import import_resource, initialize_project
from fairmorph_engine.core.registry import mapping_snapshot
from fairmorph_engine.processing.tabular import unpivot_csv

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "cs-phoc"


def _prepare(tmp_path):
    project = tmp_path / "example.fairmorph"
    initialize_project(project)
    imported = import_resource(project, EXAMPLE / "cs-phoc-counts.csv", "counts")
    draft = stage_csv_mapping(project, imported["resource_id"], EXAMPLE / "mapping-profile.json")
    return project, imported, draft


def test_csphoc_profile_is_external_and_pinned():
    profile = json.loads((EXAMPLE / "mapping-profile.json").read_text(encoding="utf-8"))
    source = (EXAMPLE / "cs-phoc-counts.csv").read_bytes()
    assert hashlib.sha256(source).hexdigest() == profile["source_sha256"]
    assert len(profile["fields"]) == 10
    assert [x["source_column"] for x in profile["fields"]] == [
        "ad_female_count",
        "ad_male_count",
        "ad_unk_count",
        "juv_female_count",
        "juv_male_count",
        "juv_unk_count",
        "pup_count",
        "unk_female_count",
        "unk_male_count",
        "unk_unk_count",
    ]
    rows = list(
        unpivot_csv(
            EXAMPLE / "cs-phoc-counts.csv",
            identifier=profile["identifier"],
            columns=[item["source_column"] for item in profile["fields"]],
            empty_cell_policy=profile["empty_cell_policy"],
            zero_cell_policy=profile["zero_cell_policy"],
        )
    )
    assert len(rows) == 16940
    assert sum(row["value"] == 0 for row in rows) == 11599
    assert sum(row["value"] for row in rows) == 79232


def test_staging_never_approves_implicitly(tmp_path):
    project, imported, draft = _prepare(tmp_path)
    assert draft["status"] == "draft"
    assert draft["source_sha256"] == imported["sha256"]
    assert len(draft["field_definition_revision_ids"]) == 10
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM field_definition_reviews").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM mapping_reviews").fetchone()[0] == 0
    with pytest.raises(ValueError, match="approved mapping"):
        mapping_snapshot(project, draft["mapping_sha256"])


def test_explicit_review_pins_mapping_and_original_resource(tmp_path):
    project, imported, draft = _prepare(tmp_path)
    approved = approve_staged_mapping(project, draft["mapping_sha256"], "reviewing-scientist")
    assert approved["status"] == "approved"
    frozen = mapping_snapshot(project, draft["mapping_sha256"])
    assert approved["mapping_snapshot"] == frozen
    assert len(frozen["field_definition_revisions"]) == 10
    assert frozen["source_resources"] == [
        {"resource_id": imported["resource_id"], "object_sha256": imported["sha256"]}
    ]
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM field_definition_reviews").fetchone()[0] == 10
        assert db.execute("SELECT COUNT(*) FROM mapping_reviews").fetchone()[0] == 1
    with pytest.raises(ValueError, match="reviewed"):
        approve_staged_mapping(project, draft["mapping_sha256"], "reviewing-scientist")


def test_declared_checksum_mismatch_rejected_before_semantics(tmp_path):
    project = tmp_path / "example.fairmorph"
    initialize_project(project)
    other = tmp_path / "other.csv"
    other.write_text("count_id,ad_female_count\nabc,0\n", encoding="utf-8")
    imported = import_resource(project, other, "counts")
    with pytest.raises(ValueError, match="Source bytes differ"):
        stage_csv_mapping(project, imported["resource_id"], EXAMPLE / "mapping-profile.json")
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM field_definition_revisions").fetchone()[0] == 0


def test_unknown_profile_column_rejected_without_draft(tmp_path):
    project, imported, _draft = _prepare(tmp_path)
    data = json.loads((EXAMPLE / "mapping-profile.json").read_text(encoding="utf-8"))
    data["version"] = "1.0.1"
    data["fields"][0]["source_column"] = "invented_count"
    bad = tmp_path / "bad-profile.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        stage_csv_mapping(project, imported["resource_id"], bad)


def test_reviewer_identity_mandatory(tmp_path):
    project, _, draft = _prepare(tmp_path)
    with pytest.raises(ValueError, match="reviewer"):
        approve_staged_mapping(project, draft["mapping_sha256"], "")


def test_headless_profile_review_cli(tmp_path):
    """Workbench can stage then explicitly approve without importing Python internals."""
    import subprocess
    import sys

    project = tmp_path / "cli.fairmorph"

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-m", "fairmorph_engine.cli", *map(str, args)],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout.splitlines()[-1])["data"]

    cli("init-project", "--project", project)
    imported = cli(
        "import-resource",
        "--project",
        project,
        "--source",
        EXAMPLE / "cs-phoc-counts.csv",
        "--role",
        "counts",
    )
    staged = cli(
        "stage-csv-mapping",
        "--project",
        project,
        "--resource-id",
        imported["resource_id"],
        "--profile",
        EXAMPLE / "mapping-profile.json",
    )
    assert staged["status"] == "draft"
    approved = cli(
        "approve-mapping",
        "--project",
        project,
        "--mapping-sha256",
        staged["mapping_sha256"],
        "--confirmed-by",
        "explicit-scientific-reviewer",
    )
    assert approved["status"] == "approved"
    assert approved["mapping_snapshot"]["mapping_sha256"] == staged["mapping_sha256"]


def test_scientific_acceptance_is_enforced_by_generic_run(tmp_path, monkeypatch):
    """No 16,940/11,599/79,232 constants are required inside the executor."""
    import sys
    import types

    from fairmorph_engine.core.run_executor import execute_mapping_run

    project, _, staged = _prepare(tmp_path)
    approve_staged_mapping(project, staged["mapping_sha256"], "reviewing-scientist")

    class FakeFrame:
        def __init__(self, data):
            self.data = data

        def select(self, *columns):
            return FakeFrame([{col: row[col] for col in columns} for row in self.data])

        def write_parquet(self, path):
            path.write_text(json.dumps(self.data), encoding="utf-8")

    monkeypatch.setitem(sys.modules, "polars", types.SimpleNamespace(DataFrame=FakeFrame))
    manifest = execute_mapping_run(project, staged["mapping_sha256"])
    report = json.loads(
        (project / "runs" / manifest["run_id"] / "reports" / "quality.json").read_text()
    )
    assert report["output_rows"] == 16940
    assert report["explicit_zeros"] == 11599
    assert report["value_sum"] == 79232
    assert manifest["configuration_sha256"] == staged["mapping_sha256"]


def test_wrong_declared_acceptance_blocks_run_publication(tmp_path, monkeypatch):
    import sys
    import types

    from fairmorph_engine.core.run_executor import execute_mapping_run

    project = tmp_path / "example.fairmorph"
    initialize_project(project)
    resource = import_resource(project, EXAMPLE / "cs-phoc-counts.csv", "counts")
    profile = json.loads((EXAMPLE / "mapping-profile.json").read_text(encoding="utf-8"))
    profile["version"] = "1.0.1"
    profile["acceptance"]["explicit_zeros"] += 1
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(profile), encoding="utf-8")
    staged = stage_csv_mapping(project, resource["resource_id"], altered)
    approve_staged_mapping(project, staged["mapping_sha256"], "reviewing-scientist")
    monkeypatch.setitem(sys.modules, "polars", types.SimpleNamespace(DataFrame=object))
    with pytest.raises(ValueError, match="Mapping acceptance failed for explicit_zeros"):
        execute_mapping_run(project, staged["mapping_sha256"])
    index = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert index["run_ids"] == []
    with sqlite3.connect(project / "catalog" / "catalog.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert len(list((project / "runs").glob(".pending-*/FAILED"))) == 1


def test_profile_file_hash_is_embedded_in_approved_mapping(tmp_path):
    from fairmorph_engine.core.registry import _catalog

    project, _, staged = _prepare(tmp_path)
    with _catalog(project) as db:
        row = db.execute(
            "SELECT content_json FROM mapping_versions WHERE mapping_sha256=?",
            (staged["mapping_sha256"],),
        ).fetchone()
    frozen_mapping = json.loads(row[0])
    profile_file = EXAMPLE / "mapping-profile.json"
    assert frozen_mapping["profile_sha256"] == hashlib.sha256(profile_file.read_bytes()).hexdigest()
    assert frozen_mapping["acceptance"] == {
        "output_rows": 16940,
        "explicit_zeros": 11599,
        "value_sum": 79232,
    }
    assert frozen_mapping["bindings"][0]["attributes"] == {"life_stage": "adult", "sex": "female"}


def test_same_profile_api_accepts_unrelated_census(tmp_path):
    project = tmp_path / "other.fairmorph"
    initialize_project(project)
    source = tmp_path / "birds.csv"
    source.write_text("plot,early,late\nP1,0,2\n", encoding="utf-8")
    imported = import_resource(project, source, "bird-stations")
    profile = {
        "mapping_id": "bird-counts",
        "version": "1.0.0",
        "operation": "wide-to-long-counts/1",
        "source_sha256": imported["sha256"],
        "identifier": "plot",
        "empty_cell_policy": "omit",
        "zero_cell_policy": "preserve",
        "fields": [
            {
                "source_column": column,
                "target_field": column,
                "description": f"Count of individual birds in {column} sampling window.",
                "definition_source": "user_confirmed",
                "counting_unit": "individual",
                "zero_meaning": "true_zero",
                "missing_values": [],
            }
            for column in ("early", "late")
        ],
        "acceptance": {"output_rows": 2, "explicit_zeros": 1, "value_sum": 2},
    }
    profile_file = tmp_path / "bird-profile.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    staged = stage_csv_mapping(project, imported["resource_id"], profile_file)
    approved = approve_staged_mapping(project, staged["mapping_sha256"], "bird-researcher")
    assert approved["mapping_snapshot"]["mapping_id"] == "bird-counts"
    assert len(approved["mapping_snapshot"]["field_definition_revisions"]) == 2
