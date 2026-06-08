"""CSV operation tools: read, write, and compute basic statistics."""

from __future__ import annotations

import csv
import io
import json
import statistics
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class CSVReadTool(BaseTool):
    """Read a CSV string and optionally select specific columns."""

    name = "csv_read"
    description = (
        "Parse a CSV string and return structured data. Optionally select "
        "specific columns by name. Returns rows as a list of dicts. "
        "Supports custom delimiters and quoting."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "The CSV content as a string.",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of column names to select. "
                    "If omitted, all columns are returned."
                ),
            },
            "delimiter": {
                "type": "string",
                "description": "Column delimiter character (default: ',').",
            },
            "has_header": {
                "type": "boolean",
                "description": "Whether the first row is a header row (default: true).",
            },
            "max_rows": {
                "type": "integer",
                "description": "Maximum number of rows to return (default: 1000).",
            },
        },
        "required": ["data"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raw: str = arguments["data"]
        columns: list[str] | None = arguments.get("columns")
        delimiter: str = arguments.get("delimiter", ",")
        has_header: bool = arguments.get("has_header", True)
        max_rows: int = arguments.get("max_rows", 1000)

        try:
            reader_file = io.StringIO(raw)
            if has_header:
                reader = csv.DictReader(reader_file, delimiter=delimiter)
                rows: list[dict[str, str]] = []
                for i, row in enumerate(reader):
                    if i >= max_rows:
                        break
                    if columns:
                        filtered = {k: v for k, v in row.items() if k in columns}
                        rows.append(filtered)
                    else:
                        rows.append(dict(row))

                header = reader.fieldnames or []
                if columns:
                    header = [h for h in header if h in columns]

                return ToolResult(
                    success=True,
                    output=json.dumps(
                        {"headers": header, "row_count": len(rows), "rows": rows[:10]},
                        indent=2,
                        ensure_ascii=False,
                    ),
                    data={"headers": header, "row_count": len(rows), "rows": rows},
                )
            else:
                reader_list = csv.reader(reader_file, delimiter=delimiter)
                rows_list: list[list[str]] = []
                for i, row in enumerate(reader_list):
                    if i >= max_rows:
                        break
                    if columns:
                        # Treat columns as integer indices when no header
                        indices = []
                        for c in columns:
                            try:
                                indices.append(int(c))
                            except ValueError:
                                pass
                        row = [row[idx] for idx in indices if idx < len(row)]
                    rows_list.append(row)

                return ToolResult(
                    success=True,
                    output=json.dumps(
                        {"row_count": len(rows_list), "rows": rows_list[:10]},
                        indent=2,
                        ensure_ascii=False,
                    ),
                    data={"row_count": len(rows_list), "rows": rows_list},
                )
        except csv.Error as exc:
            return ToolResult(success=False, output=f"CSV parse error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, output=f"Error reading CSV: {exc}")


class CSVWriteTool(BaseTool):
    """Write structured data as a CSV string."""

    name = "csv_write"
    description = (
        "Convert structured data (list of dicts or list of lists) into a "
        "CSV-formatted string. Supports custom delimiters and optional headers."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "description": (
                    "Data rows. Each element can be a dict (keys become headers) "
                    "or a list of values."
                ),
            },
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Column headers. Required when rows are lists, optional "
                    "when rows are dicts (keys are used)."
                ),
            },
            "delimiter": {
                "type": "string",
                "description": "Column delimiter character (default: ',').",
            },
            "path": {
                "type": "string",
                "description": "Optional file path to write to. If omitted, CSV is returned as a string.",
            },
        },
        "required": ["rows"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        rows: list = arguments["rows"]
        headers: list[str] | None = arguments.get("headers")
        delimiter: str = arguments.get("delimiter", ",")
        path: str | None = arguments.get("path")

        if not rows:
            return ToolResult(success=False, output="No rows provided")

        try:
            output = io.StringIO()
            first_row = rows[0]

            if isinstance(first_row, dict):
                # Dict rows
                if headers is None:
                    headers = list(first_row.keys())
                writer = csv.DictWriter(
                    output, fieldnames=headers, delimiter=delimiter,
                    extrasaction="ignore",
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            elif isinstance(first_row, (list, tuple)):
                # List rows
                writer_list = csv.writer(output, delimiter=delimiter)
                if headers:
                    writer_list.writerow(headers)
                for row in rows:
                    writer_list.writerow(row)
            else:
                return ToolResult(
                    success=False,
                    output=f"Unsupported row type: {type(first_row).__name__}. Use dicts or lists.",
                )

            csv_content = output.getvalue()

            if path:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    f.write(csv_content)
                return ToolResult(
                    success=True,
                    output=f"CSV written to {path} ({len(rows)} rows)",
                    data={"path": path, "row_count": len(rows)},
                )

            return ToolResult(
                success=True,
                output=csv_content,
                data={"row_count": len(rows), "csv": csv_content},
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Error writing CSV: {exc}")


class CSVStatsTool(BaseTool):
    """Compute basic statistics per column in a CSV string."""

    name = "csv_stats"
    description = (
        "Parse a CSV string and compute basic statistics for each numeric "
        "column: count, min, max, mean, median, stdev. Non-numeric columns "
        "report count and unique values."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "The CSV content as a string.",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of columns to compute stats for.",
            },
            "delimiter": {
                "type": "string",
                "description": "Column delimiter character (default: ',').",
            },
        },
        "required": ["data"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raw: str = arguments["data"]
        target_columns: list[str] | None = arguments.get("columns")
        delimiter: str = arguments.get("delimiter", ",")

        try:
            reader_file = io.StringIO(raw)
            reader = csv.DictReader(reader_file, delimiter=delimiter)
            all_headers = reader.fieldnames or []

            if target_columns:
                headers_to_analyze = [h for h in all_headers if h in target_columns]
            else:
                headers_to_analyze = list(all_headers)

            # Collect values per column
            column_values: dict[str, list[str]] = {h: [] for h in headers_to_analyze}
            total_rows = 0
            for row in reader:
                total_rows += 1
                for h in headers_to_analyze:
                    val = row.get(h, "")
                    if val is not None and val != "":
                        column_values[h].append(val)

            # Compute stats per column
            stats: dict[str, dict[str, Any]] = {}
            for col, values in column_values.items():
                col_stats: dict[str, Any] = {
                    "total_rows": total_rows,
                    "non_null_count": len(values),
                    "null_count": total_rows - len(values),
                }

                # Try to parse as numeric
                numeric_values: list[float] = []
                for v in values:
                    try:
                        numeric_values.append(float(v))
                    except (ValueError, TypeError):
                        pass

                if len(numeric_values) == len(values) and numeric_values:
                    # All values are numeric
                    col_stats["type"] = "numeric"
                    col_stats["min"] = min(numeric_values)
                    col_stats["max"] = max(numeric_values)
                    col_stats["mean"] = round(statistics.mean(numeric_values), 4)
                    col_stats["median"] = round(statistics.median(numeric_values), 4)
                    col_stats["sum"] = round(sum(numeric_values), 4)
                    if len(numeric_values) >= 2:
                        col_stats["stdev"] = round(statistics.stdev(numeric_values), 4)
                    else:
                        col_stats["stdev"] = 0.0
                elif numeric_values:
                    # Mixed content
                    col_stats["type"] = "mixed"
                    col_stats["numeric_count"] = len(numeric_values)
                    col_stats["text_count"] = len(values) - len(numeric_values)
                    col_stats["unique_values"] = len(set(values))
                    if numeric_values:
                        col_stats["numeric_min"] = min(numeric_values)
                        col_stats["numeric_max"] = max(numeric_values)
                        col_stats["numeric_mean"] = round(
                            statistics.mean(numeric_values), 4
                        )
                else:
                    # Text column
                    col_stats["type"] = "text"
                    col_stats["unique_values"] = len(set(values))
                    col_stats["most_common"] = max(
                        set(values), key=values.count
                    ) if values else None
                    col_stats["most_common_count"] = (
                        values.count(col_stats["most_common"])
                        if col_stats["most_common"]
                        else 0
                    )

                stats[col] = col_stats

            # Build readable output
            lines = [f"CSV Statistics ({total_rows} rows, {len(headers_to_analyze)} columns):"]
            for col, s in stats.items():
                lines.append(f"\n  {col} ({s['type']}):")
                lines.append(f"    Non-null: {s['non_null_count']}/{s['total_rows']}")
                if s["type"] == "numeric":
                    lines.append(f"    Min: {s['min']}, Max: {s['max']}")
                    lines.append(f"    Mean: {s['mean']}, Median: {s['median']}")
                    lines.append(f"    Sum: {s['sum']}, Stdev: {s['stdev']}")
                elif s["type"] == "text":
                    lines.append(f"    Unique: {s['unique_values']}")
                    lines.append(
                        f"    Most common: '{s['most_common']}' ({s['most_common_count']}x)"
                    )
                elif s["type"] == "mixed":
                    lines.append(
                        f"    Numeric: {s['numeric_count']}, Text: {s['text_count']}"
                    )
                    lines.append(f"    Unique: {s['unique_values']}")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"total_rows": total_rows, "stats": stats},
            )
        except csv.Error as exc:
            return ToolResult(success=False, output=f"CSV parse error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, output=f"Error computing CSV stats: {exc}")
