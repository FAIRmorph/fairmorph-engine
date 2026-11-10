"""Dataset-independent, allowlisted Polars table operators.

This module does not execute user Python, load plugins, or infer scientific semantics.
It is a building block for the full immutable RUN/2 pipeline integration.
"""
import json
from pathlib import Path

import polars as pl
from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "pipeline.schema.json"


def _expression(spec):
    if not isinstance(spec, dict) or len(spec) != 1:
        raise ValueError("Expression must contain exactly one allowed operation")
    name, value = next(iter(spec.items()))
    if name == "column" and isinstance(value, str):
        return pl.col(value)
    if name == "literal" and isinstance(value, (str, int, float, bool, type(None))):
        return pl.lit(value)
    if name == "concat" and isinstance(value, list) and value:
        return pl.concat_str([_expression(item).cast(pl.String) for item in value], separator="")
    if (
        name == "when"
        and isinstance(value, dict)
        and set(value) == {"condition", "then", "otherwise"}
    ):
        return (
            pl.when(_predicate(value["condition"]))
            .then(_expression(value["then"]))
            .otherwise(_expression(value["otherwise"]))
        )
    raise ValueError(f"Unsupported expression: {name}")


def _predicate(spec):
    if not isinstance(spec, dict) or set(spec) != {"column", "op", "value"}:
        raise ValueError("Predicate must specify column, op and literal value")
    if not isinstance(spec["column"], str) or spec["op"] not in {
        "eq",
        "ne",
        "gt",
        "ge",
        "lt",
        "le",
        "is_null",
        "is_not_null",
    }:
        raise ValueError("Unsupported predicate")
    col = pl.col(spec["column"])
    op = spec["op"]
    if op == "is_null":
        return col.is_null()
    if op == "is_not_null":
        return col.is_not_null()
    value = pl.lit(spec["value"])
    return {
        "eq": lambda: col == value,
        "ne": lambda: col != value,
        "gt": lambda: col > value,
        "ge": lambda: col >= value,
        "lt": lambda: col < value,
        "le": lambda: col <= value,
    }[op]()


def _apply(operator, frames, params):
    if operator == "table.select/1":
        columns = params["columns"]
        if (
            not isinstance(columns, list)
            or not columns
            or not all(isinstance(c, str) for c in columns)
        ):
            raise ValueError("select requires a nonempty list of columns")
        return frames[0].select(columns)
    if operator == "table.filter/1":
        return frames[0].filter(_predicate(params["predicate"]))
    if operator == "table.derive/1":
        expressions = params["expressions"]
        if not isinstance(expressions, dict) or not expressions:
            raise ValueError("derive requires expressions")
        return frames[0].with_columns([_expression(expr).alias(name) for name, expr in expressions.items()])
    if operator == "table.distinct/1":
        return frames[0].unique(subset=params["keys"], keep="first", maintain_order=True)
    if operator == "table.unpivot/1":
        return frames[0].unpivot(on=params["columns"], index=params["identifiers"],
                                 variable_name=params["variable"], value_name=params["value"])
    if operator == "table.join/1":
        if len(frames) != 2:
            raise ValueError("join requires two inputs")
        keys = params["keys"]
        if not isinstance(keys, list) or not keys:
            raise ValueError("join requires keys")
        left, right = frames
        if (
            left.select(keys).null_count().sum_horizontal().sum()
            or right.select(keys).null_count().sum_horizontal().sum()
        ):
            raise ValueError("Join keys must not contain nulls")
        cardinality = params["cardinality"]
        if cardinality not in {"1:1", "1:m", "m:1", "m:m"}:
            raise ValueError("Unsupported join cardinality")
        if cardinality in {"1:1", "m:1"} and right.select(keys).is_duplicated().any():
            raise ValueError("Duplicate right-hand join key")
        if cardinality in {"1:1", "1:m"} and left.select(keys).is_duplicated().any():
            raise ValueError("Duplicate left-hand join key")
        result = left.join(
            right,
            on=keys,
            how="left",
            validate={"1:1": "1:1", "1:m": "1:m", "m:1": "m:1", "m:m": "m:m"}[cardinality],
        )
        if result.height != left.height and params.get("preserve_left_rows", True):
            raise ValueError("Join changes left row count")
        if params.get("require_match", True):
            missing = left.select(keys).join(right.select(keys).unique(), on=keys, how="anti")
            if missing.height:
                raise ValueError("Join contains unmatched keys")
        return result
    raise ValueError(f"Unknown operator: {operator}")


def execute_pipeline(config: dict, resources: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Execute a validated, deterministic DAG using only registered operators.

    Input resources are supplied by the caller, not read from arbitrary config paths.
    Returns named intermediate and final tables; persistence and RUN manifests belong
    to the separate RUN publisher.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(config)
    tables = dict(resources)
    if any(not isinstance(value, pl.DataFrame) for value in tables.values()):
        raise ValueError("All input resources must be Polars DataFrames")
    steps = config["steps"]
    ids = [step["id"] for step in steps]
    outputs = [step["output"] for step in steps]
    if len(set(ids)) != len(ids) or len(set(outputs)) != len(outputs):
        raise ValueError("Duplicate step identifier or output")
    if set(outputs) & set(tables):
        raise ValueError("Pipeline output shadows input resource")
    pending = {step["id"]: step for step in steps}
    while pending:
        ready = sorted(
            (
                step
                for step in pending.values()
                if all(source in tables for source in step["inputs"])
            ),
            key=lambda step: step["id"],
        )
        if not ready:
            raise ValueError("Unresolved pipeline dependencies or cycle")
        for step in ready:
            frames = [tables[name] for name in step["inputs"]]
            expected = 2 if step["operator"] == "table.join/1" else 1
            if len(frames) != expected:
                raise ValueError("Incorrect number of operator inputs")
            tables[step["output"]] = _apply(step["operator"], frames, step["parameters"])
            del pending[step["id"]]
    return tables
