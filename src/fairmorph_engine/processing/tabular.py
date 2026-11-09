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
