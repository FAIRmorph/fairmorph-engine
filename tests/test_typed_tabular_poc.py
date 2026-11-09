"""PoC guardrails for explicitly typed CSV values."""

import pytest

from fairmorph_engine.processing.tabular import unpivot_typed_csv


def test_declared_missing_token_is_omitted_without_inference(tmp_path):
    source = tmp_path / "values.csv"
    source.write_text("site,measure,label\nA,NA,wet\nB,-1.25,NA\n", encoding="utf-8")
    rows = list(
        unpivot_typed_csv(
            source,
            identifier="site",
            value_types={"measure": "decimal", "label": "text"},
            missing_tokens={"measure": ["NA"], "label": ["NA"]},
        )
    )
    assert [(row["source_column"], row["value"]) for row in rows] == [
        ("label", "wet"),
        ("measure", "-1.25"),
    ]


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "invalid"])
def test_invalid_decimal_fails_explicitly(tmp_path, raw):
    source = tmp_path / "values.csv"
    source.write_text(f"site,measure\nA,{raw}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="decimal"):
        list(unpivot_typed_csv(source, identifier="site", value_types={"measure": "decimal"}))
