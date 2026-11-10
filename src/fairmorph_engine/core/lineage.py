"""Cell- and record-level source lineage for the small v0.12 vertical PoC.

Lineage uses zero-based source data-row offsets, not scientific entity IDs.
It is deliberately eager and in-memory; large-scale streaming is a later package.
"""

from dataclasses import dataclass

import polars as pl

from fairmorph_engine.core.pipeline import _predicate

# (resource_id, immutable object hash, source data-row offset, source column, origin kind)
Cell = tuple[str, str, int | None, str, str]
# (resource_id, immutable object hash, source data-row offset)
Record = tuple[str, str, int]


@dataclass
class TableTrace:
    cells: list[dict[str, frozenset[Cell]]]
    records: list[frozenset[Record]]


def _marker(frames: list[pl.DataFrame], label: str) -> str:
    """Create a tracking column that cannot shadow a real input column."""
    columns = {column for frame in frames for column in frame.columns}
    marker = f"__fairmorph_{label}"
    while marker in columns:
        marker += "_"
    return marker


def _select_rows(trace: TableTrace, indices: list[int]) -> TableTrace:
    return TableTrace(
        cells=[trace.cells[index] for index in indices],
        records=[trace.records[index] for index in indices],
    )


def _sources_of_expression(
    spec: dict, trace: TableTrace, index: int, frame: pl.DataFrame, masks: dict
) -> frozenset[Cell]:
    name, value = next(iter(spec.items()))
    if name == "column":
        return trace.cells[index][value]
    if name == "literal":
        return frozenset()
    if name == "concat":
        return frozenset().union(
            *(_sources_of_expression(item, trace, index, frame, masks) for item in value)
        )
    if name == "when":
        condition = value["condition"]
        key = (condition["column"], condition["op"], str(condition["value"]))
        if key not in masks:
            masks[key] = frame.select(_predicate(condition)).to_series().to_list()
        branch = value["then"] if masks[key][index] else value["otherwise"]
        return frozenset().union(
            trace.cells[index][condition["column"]],
            _sources_of_expression(branch, trace, index, frame, masks),
        )
    raise ValueError("Unsupported expression for lineage")


def _step_trace(
    step: dict,
    frames: list[pl.DataFrame],
    inputs: list[TableTrace],
    output: pl.DataFrame,
) -> TableTrace:
    operator = step["operator"]
    params = step["parameters"]
    base = inputs[0]
    frame = frames[0]
    if operator == "table.select/1":
        traced = TableTrace(
            cells=[{column: row[column] for column in params["columns"]} for row in base.cells],
            records=base.records,
        )
    elif operator == "table.filter/1":
        marker = _marker(frames, "row")
        indices = (
            frame.with_row_index(marker)
            .filter(_predicate(params["predicate"]))
            .get_column(marker)
            .to_list()
        )
        traced = _select_rows(base, indices)
    elif operator == "table.distinct/1":
        marker = _marker(frames, "row")
        indices = (
            frame.with_row_index(marker)
            .unique(subset=params["keys"], keep="first", maintain_order=True)
            .get_column(marker)
            .to_list()
        )
        traced = _select_rows(base, indices)
    elif operator == "table.derive/1":
        masks = {}
        cells = []
        for index, row in enumerate(base.cells):
            updated = dict(row)
            for column, expression in params["expressions"].items():
                updated[column] = _sources_of_expression(expression, base, index, frame, masks)
            cells.append(updated)
        traced = TableTrace(cells=cells, records=base.records)
    elif operator == "table.unpivot/1":
        marker = _marker(frames, "row")
        tagged = frame.with_row_index(marker).unpivot(
            on=params["columns"],
            index=[*params["identifiers"], marker],
            variable_name=params["variable"],
            value_name=params["value"],
        )
        cells = []
        records = []
        for source_index, variable in zip(
            tagged.get_column(marker).to_list(),
            tagged.get_column(params["variable"]).to_list(),
            strict=True,
        ):
            row = base.cells[source_index]
            origins = row[variable]
            # A transformed column name is generated, not a source-file header.
            headers = (
                frozenset(
                    (resource, checksum, None, column, "column_header")
                    for resource, checksum, _, column, _ in origins
                )
                if origins and all(column == variable for _, _, _, column, _ in origins)
                else frozenset()
            )
            cells.append(
                {
                    **{column: row[column] for column in params["identifiers"]},
                    params["variable"]: headers,
                    params["value"]: origins,
                }
            )
            records.append(base.records[source_index])
        traced = TableTrace(cells=cells, records=records)
    elif operator == "table.join/1":
        left, right = frames
        left_trace, right_trace = inputs
        left_marker = _marker(frames, "left_row")
        right_marker = _marker(frames, "right_row")
        tagged = left.with_row_index(left_marker).join(
            right.with_row_index(right_marker),
            on=params["keys"],
            how="left",
            validate={
                "1:1": "1:1",
                "1:m": "1:m",
                "m:1": "m:1",
                "m:m": "m:m",
            }[params["cardinality"]],
            maintain_order="left_right",
        )
        cells = []
        records = []
        for left_index, right_index in zip(
            tagged.get_column(left_marker).to_list(),
            tagged.get_column(right_marker).to_list(),
            strict=True,
        ):
            row = dict(left_trace.cells[left_index])
            origins = set(left_trace.records[left_index])
            for column in right.columns:
                if column in params["keys"]:
                    continue
                target = column if column not in left.columns else f"{column}_right"
                row[target] = (
                    right_trace.cells[right_index][column]
                    if right_index is not None
                    else frozenset()
                )
            if right_index is not None:
                origins.update(right_trace.records[right_index])
            cells.append(row)
            records.append(frozenset(origins))
        traced = TableTrace(cells=cells, records=records)
    else:
        raise ValueError(f"No source-lineage support for {operator}")
    if len(traced.cells) != output.height or len(traced.records) != output.height:
        raise ValueError("Lineage row count differs from DAG output")
    if any(set(row) != set(output.columns) for row in traced.cells):
        raise ValueError("Lineage columns differ from DAG output")
    return traced


def trace_pipeline(
    config: dict, tables: dict[str, pl.DataFrame], pins: list[dict]
) -> dict[str, TableTrace]:
    """Trace every executed DAG output back to immutable source rows/cells."""
    traces = {}
    by_name = {pin["name"]: pin for pin in pins}
    for name in config["resources"]:
        frame = tables[name]
        pin = by_name[name]
        resource, checksum = pin["resource_id"], pin["sha256"]
        traces[name] = TableTrace(
            cells=[
                {
                    column: frozenset({(resource, checksum, row, column, "data_cell")})
                    for column in frame.columns
                }
                for row in range(frame.height)
            ],
            records=[
                frozenset({(resource, checksum, row)}) for row in range(frame.height)
            ],
        )
    pending = {step["id"]: step for step in config["steps"]}
    while pending:
        ready = sorted(
            (
                step
                for step in pending.values()
                if all(source in traces for source in step["inputs"])
            ),
            key=lambda step: step["id"],
        )
        if not ready:
            raise ValueError("Unresolved DAG dependencies in lineage")
        for step in ready:
            sources = step["inputs"]
            traces[step["output"]] = _step_trace(
                step,
                [tables[source] for source in sources],
                [traces[source] for source in sources],
                tables[step["output"]],
            )
            del pending[step["id"]]
    return traces


def trace_entities(config: dict, traces: dict[str, TableTrace]) -> dict[str, TableTrace]:
    """A semantic projection copies cells, not guessed scientific identities."""
    result = {}
    for kind, spec in config.get("entities", {}).items():
        source = traces[spec["source_table"]]
        result[kind.lower()] = TableTrace(
            cells=[
                {target: row[binding["column"]] for target, binding in spec["fields"].items()}
                for row in source.cells
            ],
            records=source.records,
        )
    return result


LINEAGE_SCHEMA = {
    "output_table": pl.String,
    "output_row_index": pl.Int64,
    "output_column": pl.String,
    "lineage_type": pl.String,
    "source_resource_id": pl.String,
    "source_object_sha256": pl.String,
    "source_row_index": pl.Int64,
    "source_column": pl.String,
    "source_kind": pl.String,
}


def lineage_frame(
    published: dict[str, pl.DataFrame], traces: dict[str, TableTrace]
) -> pl.DataFrame:
    """One record link per input row plus cell links for each output field."""
    rows = []
    for name in sorted(published):
        frame = published[name]
        trace = traces[name]
        if len(trace.cells) != frame.height:
            raise ValueError("Published output has no matching row-level lineage")
        for output_index, (cells, records) in enumerate(
            zip(trace.cells, trace.records, strict=True)
        ):
            if set(cells) != set(frame.columns):
                raise ValueError("Published output has no matching cell-level lineage")
            for resource, checksum, index in sorted(records):
                rows.append(
                    (
                        name,
                        output_index,
                        None,
                        "record",
                        resource,
                        checksum,
                        index,
                        None,
                        "data_row",
                    )
                )
            for column in frame.columns:
                origins = cells[column]
                if not origins:
                    rows.append(
                        (name, output_index, column, "cell", None, None, None, None, "derived")
                    )
                for resource, checksum, index, field, kind in sorted(
                    origins,
                    key=lambda ref: (
                        ref[0],
                        ref[1],
                        -1 if ref[2] is None else ref[2],
                        ref[3],
                        ref[4],
                    ),
                ):
                    rows.append(
                        (name, output_index, column, "cell", resource, checksum, index, field, kind)
                    )
    return pl.DataFrame(rows, schema=LINEAGE_SCHEMA, orient="row")
