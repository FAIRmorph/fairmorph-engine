"""Generic pipeline contracts, ordering and rejection tests."""
import polars as pl
import pytest
from jsonschema.exceptions import ValidationError

from fairmorph_engine.core.pipeline import execute_pipeline


def step(name, operator, inputs, output, **parameters):
    return {"id": name, "operator": operator, "inputs": inputs, "output": output, "parameters": parameters}


def test_generic_dag_orders_steps_and_rejects_missing_join_keys():
    config = {"schema_version": "fairmorph.pipeline/1", "steps": [
        step("z-project", "table.select/1", ["enriched"], "result", columns=["id", "event", "value"]),
        step("a-join", "table.join/1", ["counts", "events"], "enriched",
             keys=["event"], cardinality="m:1", require_match=True),
    ]}
    sources = {
        "counts": pl.DataFrame({"id": ["c1", "c2"], "event": ["e1", "e2"], "value": [0, 3]}),
        "events": pl.DataFrame({"event": ["e1", "e2"], "location": ["north", "south"]}),
    }
    result = execute_pipeline(config, sources)
    assert result["result"].height == 2
    assert result["result"]["value"].to_list() == [0, 3]
    with pytest.raises(ValueError, match="unmatched"):
        execute_pipeline(config, {**sources, "events": sources["events"].filter(pl.col("event") == "e1")})


def test_generic_derived_ids_and_filter():
    config = {"schema_version": "fairmorph.pipeline/1", "steps": [
        step("derive", "table.derive/1", ["source"], "named",
             expressions={"record": {"concat": [{"column": "event"}, {"literal": "-"}, {"column": "category"}]},
                          "status": {"when": {"condition": {"column": "value", "op": "eq", "value": 0},
                                               "then": {"literal": "absent"}, "otherwise": {"literal": "present"}}}}),
        step("filter", "table.filter/1", ["named"], "positive",
             predicate={"column": "value", "op": "gt", "value": 0}),
    ]}
    result = execute_pipeline(config, {"source": pl.DataFrame({"event": ["e1", "e1"], "category": ["a", "b"], "value": [0, 2]})})
    assert result["named"]["record"].to_list() == ["e1-a", "e1-b"]
    assert result["named"]["status"].to_list() == ["absent", "present"]
    assert result["positive"].height == 1


def test_rejects_unsupported_operator_and_cycle():
    with pytest.raises(ValidationError):
        execute_pipeline({"schema_version": "fairmorph.pipeline/1", "steps": [
            step("exec", "python.eval", ["source"], "output", code="1+1")
        ]}, {"source": pl.DataFrame({"a": [1]})})
    with pytest.raises(ValueError, match="dependencies or cycle"):
        execute_pipeline({"schema_version": "fairmorph.pipeline/1", "steps": [
            step("a", "table.select/1", ["b"], "a", columns=["x"]),
            step("b", "table.select/1", ["a"], "b", columns=["x"]),
        ]}, {})
