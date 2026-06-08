"""Database operation tools: SQLite query, schema inspection, CSV import."""

from __future__ import annotations

import csv
import os
import sqlite3
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class SQLiteQueryTool(BaseTool):
    """Execute SQL queries on a SQLite database."""

    name = "sqlite_query"
    description = (
        "Execute a SQL query on a SQLite database and return results as "
        "a list of rows. By default only SELECT queries are allowed; "
        "set allow_write=true for INSERT/UPDATE/DELETE/CREATE operations."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "db_path": {
                "type": "string",
                "description": "Path to the SQLite database file.",
            },
            "query": {
                "type": "string",
                "description": "SQL query to execute.",
            },
            "params": {
                "type": "array",
                "items": {},
                "description": "Optional list of query parameters for parameterized queries.",
            },
            "allow_write": {
                "type": "boolean",
                "description": "Allow write operations (INSERT, UPDATE, DELETE, CREATE, DROP). Default false.",
                "default": False,
            },
        },
        "required": ["db_path", "query"],
    }

    _WRITE_KEYWORDS = {"insert", "update", "delete", "drop", "alter", "create", "replace", "attach"}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        db_path: str = arguments["db_path"]
        query: str = arguments["query"]
        params: list = arguments.get("params", [])
        allow_write: bool = arguments.get("allow_write", False)

        # Safety check: block write ops unless explicitly allowed
        first_word = query.strip().split()[0].lower() if query.strip() else ""
        if first_word in self._WRITE_KEYWORDS and not allow_write:
            return ToolResult(
                success=False,
                output=f"Write operation '{first_word.upper()}' blocked. Set allow_write=true to enable.",
            )

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)

            if first_word == "select" or query.strip().lower().startswith("pragma"):
                rows = cursor.fetchall()
                if not rows:
                    conn.close()
                    return ToolResult(
                        success=True,
                        output="Query returned 0 rows",
                        data={"rows": [], "count": 0},
                    )

                columns = [desc[0] for desc in cursor.description]
                result_rows = [dict(zip(columns, row)) for row in rows]

                # Format as table
                lines = [" | ".join(columns)]
                lines.append("-+-".join("-" * len(c) for c in columns))
                for row in result_rows:
                    lines.append(" | ".join(str(row.get(c, "")) for c in columns))

                conn.close()
                return ToolResult(
                    success=True,
                    output="\n".join(lines),
                    data={"rows": result_rows, "count": len(result_rows), "columns": columns},
                )
            else:
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return ToolResult(
                    success=True,
                    output=f"Query executed successfully. Rows affected: {affected}",
                    data={"rows_affected": affected},
                )

        except sqlite3.Error as exc:
            return ToolResult(success=False, output=f"SQLite error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, output=f"Error: {exc}")


class SQLiteSchemasTool(BaseTool):
    """Get the schema of a SQLite database."""

    name = "sqlite_schema"
    description = (
        "Inspect a SQLite database and return its schema: tables, columns, "
        "types, and indexes."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "db_path": {
                "type": "string",
                "description": "Path to the SQLite database file.",
            },
        },
        "required": ["db_path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        db_path: str = arguments["db_path"]

        if not os.path.exists(db_path):
            return ToolResult(success=False, output=f"Database file not found: {db_path}")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get all tables
            cursor.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = cursor.fetchall()

            if not tables:
                conn.close()
                return ToolResult(
                    success=True,
                    output="Database has no tables",
                    data={"tables": []},
                )

            schema_data = []
            lines = []

            for table_name, create_sql in tables:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()

                col_info = []
                for col in columns:
                    # col: (cid, name, type, notnull, default, pk)
                    col_info.append({
                        "name": col[1],
                        "type": col[2],
                        "notnull": bool(col[3]),
                        "default": col[4],
                        "primary_key": bool(col[5]),
                    })

                schema_data.append({"table": table_name, "columns": col_info})

                lines.append(f"Table: {table_name}")
                for ci in col_info:
                    pk = " [PK]" if ci["primary_key"] else ""
                    nn = " NOT NULL" if ci["notnull"] else ""
                    lines.append(f"  {ci['name']} {ci['type']}{pk}{nn}")
                lines.append("")

            conn.close()
            return ToolResult(
                success=True,
                output="\n".join(lines).strip(),
                data={"tables": schema_data},
            )

        except sqlite3.Error as exc:
            return ToolResult(success=False, output=f"SQLite error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, output=f"Error: {exc}")


class CSVToSQLiteTool(BaseTool):
    """Import a CSV file into a SQLite database table."""

    name = "csv_to_sqlite"
    description = (
        "Import a CSV file into a SQLite database table. Creates the "
        "table if it does not exist, inferring column names from the CSV header."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "csv_path": {
                "type": "string",
                "description": "Path to the CSV file to import.",
            },
            "db_path": {
                "type": "string",
                "description": "Path to the SQLite database file (created if absent).",
            },
            "table_name": {
                "type": "string",
                "description": "Name of the table to import into.",
            },
        },
        "required": ["csv_path", "db_path", "table_name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        csv_path: str = arguments["csv_path"]
        db_path: str = arguments["db_path"]
        table_name: str = arguments["table_name"]

        if not os.path.exists(csv_path):
            return ToolResult(success=False, output=f"CSV file not found: {csv_path}")

        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader, None)
                if not headers:
                    return ToolResult(success=False, output="CSV file is empty or has no header")

                rows = list(reader)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Sanitize column names (replace non-alphanumeric with underscore)
            safe_cols = []
            for h in headers:
                safe = "".join(c if c.isalnum() or c == "_" else "_" for c in h)
                if not safe or safe[0].isdigit():
                    safe = f"col_{safe}"
                safe_cols.append(safe)

            # Create table
            col_defs = ", ".join(f'"{c}" TEXT' for c in safe_cols)
            cursor.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs})')

            # Insert rows
            placeholders = ", ".join("?" for _ in safe_cols)
            cursor.executemany(
                f'INSERT INTO "{table_name}" VALUES ({placeholders})',
                rows,
            )
            conn.commit()
            conn.close()

            return ToolResult(
                success=True,
                output=f"Imported {len(rows)} rows into table '{table_name}' ({len(safe_cols)} columns)",
                data={
                    "rows_imported": len(rows),
                    "columns": safe_cols,
                    "table_name": table_name,
                },
            )

        except csv.Error as exc:
            return ToolResult(success=False, output=f"CSV error: {exc}")
        except sqlite3.Error as exc:
            return ToolResult(success=False, output=f"SQLite error: {exc}")
        except Exception as exc:
            return ToolResult(success=False, output=f"Error: {exc}")
