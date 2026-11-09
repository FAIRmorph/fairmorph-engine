import pytest
from fairmorph_engine.processing.tabular import unpivot_csv


def test_zero_and_empty_cells_are_not_conflated(tmp_path):
    source = tmp_path / "numbers.csv"
    source.write_text("id,female,male\na,0,\nb,2,1\n", encoding="utf-8")
    rows = list(unpivot_csv(source, identifier="id", columns=["female", "male"],
                            empty_cell_policy="omit", zero_cell_policy="preserve"))
    assert [(r["source_identifier"], r["source_column"], r["value"]) for r in rows] == [
        ("a", "female", 0), ("b", "female", 2), ("b", "male", 1)]
    assert rows[0]["source_line"] == 2


def test_unapproved_conversion_policy_fails(tmp_path):
    path = tmp_path / "numbers.csv"
    path.write_text("id,n\na,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="reviewed"):
        list(unpivot_csv(path, identifier="id", columns=["n"],
                         empty_cell_policy="zero", zero_cell_policy="preserve"))


def test_invalid_nonempty_value_is_not_silently_zero(tmp_path):
    path = tmp_path / "numbers.csv"
    path.write_text("id,n\na,N/A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid integer"):
        list(unpivot_csv(path, identifier="id", columns=["n"],
                         empty_cell_policy="omit", zero_cell_policy="preserve"))


def test_generic_unpivot_matches_csphoc_reference_cardinality():
    """A generic primitive processes published reference without dataset-specific code."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "examples" / "cs-phoc" / "cs-phoc-counts.csv"
    if not source.exists():
        pytest.skip("Real CS-PHOC example source only available in the repository checkout")
    columns = [
        "ad_female_count", "ad_male_count", "ad_unk_count", "juv_female_count",
        "juv_male_count", "juv_unk_count", "pup_count", "unk_female_count",
        "unk_male_count", "unk_unk_count",
    ]
    rows = list(unpivot_csv(source, identifier="count_id", columns=columns,
                            empty_cell_policy="omit", zero_cell_policy="preserve"))
    assert len(rows) == 16940
    assert sum(row["value"] == 0 for row in rows) == 11599
    assert sum(row["value"] for row in rows) == 79232
