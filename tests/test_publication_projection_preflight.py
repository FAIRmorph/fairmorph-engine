"""Projection validation reads only explicitly pinned RUN output schemas."""

import hashlib
import json

import polars as pl
import pytest

from fairmorph_engine.core.publication_projection import validate_publication_projection


def test_projection_validates_pinned_columns(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    (run_dir / "outputs").mkdir(parents=True)
    artifact = run_dir / "outputs" / "records.parquet"
    pl.DataFrame({"record_key": ["r1"], "taxon_key": ["t1"]}).write_parquet(artifact)
    manifest_file = run_dir / "manifest.json"
    manifest_file.write_text("{}", encoding="utf-8")
    manifest = {
        "schema_version": "fairmorph.poc.run/2",
        "artifacts": [{"path": "outputs/records.parquet"}],
    }

    def fake_verified_run(_project, _run_id):
        return run_dir, manifest

    monkeypatch.setattr(
        "fairmorph_engine.core.publication_projection.verified_run", fake_verified_run
    )
    plan = {
        "schema_version": "fairmorph.poc.publication-projection/1",
        "run_manifest_sha256": hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
        "tables": [
            {
                "row_type": "Occurrence",
                "artifact_path": "outputs/records.parquet",
                "columns": ["record_key"],
            }
        ],
    }
    plan_file = tmp_path / "plan.json"

    def check():
        plan_file.write_text(json.dumps(plan), encoding="utf-8")
        return validate_publication_projection(tmp_path, "synthetic-run", plan_file)

    result = check()
    assert result["artifact_columns_verified"] is True
    assert result["field_bindings_verified"] is False
    assert result["publication_ready"] is False

    plan["tables"][0]["columns"] = ["missing_key"]
    with pytest.raises(ValueError, match="Projection columns missing"):
        check()

    plan["tables"][0]["columns"] = ["record_key"]
    plan["tables"][0]["artifact_path"] = "outputs/unpinned.parquet"
    with pytest.raises(ValueError, match="not pinned"):
        check()

    plan["tables"][0]["artifact_path"] = "outputs/records.parquet"
    plan["run_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="RUN manifest SHA-256 mismatch"):
        check()

    plan["run_manifest_sha256"] = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    plan["tables"].append(dict(plan["tables"][0]))
    with pytest.raises(ValueError, match="Duplicate projection row type"):
        check()
