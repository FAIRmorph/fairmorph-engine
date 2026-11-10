"""Sparse value-change audit for version-pinned declarative RUN/2 pipelines.

Unchanged values and structural reshaping are reproducible from immutable inputs
and the saved DAG. Only comparable *changed* values get per-row audit records.
"""

import json
import math
from datetime import date, datetime

import polars as pl


def _value_sources(expression: dict) -> set[str]:
    """Find source *values*, not predicates, used to compute an expression."""
    op, value = next(iter(expression.items()))
    if op == "column":
        return {value}
    if op == "literal":
        return set()
    if op == "concat":
        return set().union(*(_value_sources(part) for part in value))
    if op == "when":
        return _value_sources(value["then"]) | _value_sources(value["otherwise"])
    raise ValueError(f"Unsupported audited expression: {op}")


def _equal(left, right) -> bool:
    """Compare the actual value and its Python type; null != zero."""
    if left is None or right is None:
        return left is right
    if type(left) is not type(right):
        return False
    if isinstance(left, float) and math.isnan(left) and math.isnan(right):
        return True
    return bool(left == right)


def _json_value(value, dtype: pl.DataType) -> str:
    """Retain null, scalar type and special values in an inspectable JSON cell."""
    if value is None:
        encoded = None
    elif isinstance(value, float) and not math.isfinite(value):
        encoded = {"non_finite": str(value)}
    elif isinstance(value, (date, datetime)):
        encoded = value.isoformat()
    elif isinstance(value, bytes):
        encoded = {"hex": value.hex()}
    else:
        encoded = value
    return json.dumps(
        {"dtype": str(dtype), "value": encoded},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
        allow_nan=False,
    )


CHANGE_SCHEMA = {
    "step_id": pl.String,
    "operator": pl.String,
    "input_table": pl.String,
    "input_row_index": pl.Int64,
    "input_column": pl.String,
    "output_table": pl.String,
    "output_row_index": pl.Int64,
    "output_column": pl.String,
    "before_json": pl.String,
    "after_json": pl.String,
}


class ChangeAudit:
    """Observe the actual DAG execution without duplicating source-cell lineage."""

    def __init__(self):
        self.steps: list[dict] = []
        self.changes: list[tuple] = []

    def observe(self, step: dict, inputs: list[pl.DataFrame], output: pl.DataFrame) -> None:
        operation = step["operator"]
        differences = 0
        without_baseline = []
        if operation == "table.derive/1":
            original = inputs[0]
            # Derive preserves row order and count; no identity guessing needed.
            if original.height != output.height:
                raise ValueError("Derive changed row cardinality unexpectedly")
            for target, expression in step["parameters"]["expressions"].items():
                if target in original.columns:
                    baseline = target
                else:
                    sources = _value_sources(expression)
                    baseline = next(iter(sources)) if len(sources) == 1 else None
                if baseline is None:
                    without_baseline.append(target)
                    continue
                before = original.get_column(baseline)
                after = output.get_column(target)
                for index, (old, new) in enumerate(
                    zip(before.to_list(), after.to_list(), strict=True)
                ):
                    if _equal(old, new):
                        continue
                    differences += 1
                    self.changes.append(
                        (
                            step["id"],
                            operation,
                            step["inputs"][0],
                            index,
                            baseline,
                            step["output"],
                            index,
                            target,
                            _json_value(old, before.dtype),
                            _json_value(new, after.dtype),
                        )
                    )
        self.steps.append(
            {
                "step_id": step["id"],
                "operator": operation,
                "input_tables": step["inputs"],
                "input_rows": [frame.height for frame in inputs],
                "output_table": step["output"],
                "output_rows": output.height,
                "value_changes": differences,
                "fields_without_direct_value_comparison": sorted(without_baseline),
            }
        )

    def changes_frame(self) -> pl.DataFrame:
        return pl.DataFrame(self.changes, schema=CHANGE_SCHEMA, orient="row")
