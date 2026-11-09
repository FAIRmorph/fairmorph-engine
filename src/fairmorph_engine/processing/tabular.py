"""Small dataset-neutral, audited wide-to-long transformation primitive.

The scientific interpretation and CSV field names arrive in a reviewed mapping;
this module never infers units, category meaning, null semantics or taxonomy.
"""

import csv
from collections.abc import Iterator
from pathlib import Path


def unpivot_csv(
    source: Path,
    *,
    identifier: str,
    columns: list[str],
    empty_cell_policy: str,
    zero_cell_policy: str,
) -> Iterator[dict]:
    """Stream original rows with lineage, preserving zeros and source positions."""
    if empty_cell_policy != "omit" or zero_cell_policy != "preserve":
        raise ValueError("Only explicitly reviewed omit-empty/preserve-zero policy is supported")
    if not columns or len(columns) != len(set(columns)) or identifier in columns:
        raise ValueError("Invalid source column selection")
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, restkey="__extra__", strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not {identifier, *columns}.issubset(headers):
            raise ValueError("Source header does not match approved mapping")
        for line_no, record in enumerate(reader, 2):
            if None in record or "__extra__" in record:
                raise ValueError(f"Malformed CSV row at line {line_no}")
            for column in columns:
                raw = record[column]
                if raw == "":
                    continue
                try:
                    value = int(raw)
                except (ValueError, TypeError) as error:
                    raise ValueError(
                        f"Invalid integer at line {line_no}, column {column}"
                    ) from error
                if value < 0:
                    raise ValueError(f"Negative count at line {line_no}, column {column}")
                yield {
                    "source_identifier": record[identifier],
                    "source_line": line_no,
                    "source_column": column,
                    "original_value": raw,
                    "value": value,
                }


def unpivot_typed_csv(
    source: Path,
    *,
    identifier: str,
    value_types: dict[str, str],
) -> Iterator[dict]:
    """Stream reviewed integer, decimal and text values without semantic inference.

    Typed values are serialized as canonical text to preserve one homogeneous
    Parquet column. The declared value_type is retained in each output record.
    """
    from decimal import Decimal, InvalidOperation

    if not value_types or identifier in value_types:
        raise ValueError("Invalid typed source column selection")
    if set(value_types.values()) - {"integer", "decimal", "text"}:
        raise ValueError("Unsupported declared value type")
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, restkey="__extra__", strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not {identifier, *value_types}.issubset(headers):
            raise ValueError("Source header does not match approved mapping")
        for line_no, record in enumerate(reader, 2):
            if None in record or "__extra__" in record or any(v is None for v in record.values()):
                raise ValueError(f"Malformed CSV row at line {line_no}")
            for column, value_type in value_types.items():
                raw = record[column]
                if raw == "":
                    continue
                if value_type == "integer":
                    try:
                        value = str(int(raw))
                    except ValueError as error:
                        raise ValueError(
                            f"Invalid integer at line {line_no}, column {column}"
                        ) from error
                elif value_type == "decimal":
                    try:
                        number = Decimal(raw)
                    except InvalidOperation as error:
                        raise ValueError(
                            f"Invalid decimal at line {line_no}, column {column}"
                        ) from error
                    if not number.is_finite():
                        raise ValueError(f"Non-finite decimal at line {line_no}, column {column}")
                    value = str(number)
                else:
                    value = raw
                yield {
                    "source_identifier": record[identifier],
                    "source_line": line_no,
                    "source_column": column,
                    "original_value": raw,
                    "value": value,
                    "value_type": value_type,
                }
