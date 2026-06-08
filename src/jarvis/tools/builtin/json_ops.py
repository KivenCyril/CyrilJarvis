"""JSON and YAML processing tools."""

from __future__ import annotations

import json
import re
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def _query_json(data: Any, query: str) -> Any:
    """Simple dot-notation query with array index support.

    Supports paths like ``users.0.name``, ``config.database.host``, and
    the special ``*`` wildcard for mapping over arrays.
    """
    parts = query.split(".")
    current = data
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            if part == "*":
                # Wildcard: remaining path applied to each element
                remaining = ".".join(parts[parts.index(part) + 1 :])
                if remaining:
                    return [_query_json(item, remaining) for item in current]
                return current
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


class JsonQueryTool(BaseTool):
    """Query JSON data with a dot-notation path."""

    name = "json_query"
    description = (
        "Parse a JSON string and query it with a dot-notation path such as "
        "'users.0.name' or 'config.database.host'. Returns the matched value."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "A JSON string to query.",
            },
            "query": {
                "type": "string",
                "description": (
                    "Dot-notation query path, e.g. 'users.0.name'. "
                    "Use numeric indices for arrays."
                ),
            },
        },
        "required": ["data", "query"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raw: str = arguments["data"]
        query: str = arguments["query"]

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return ToolResult(success=False, output=f"Invalid JSON: {exc}")

        result = _query_json(parsed, query)

        if result is None:
            return ToolResult(
                success=True,
                output="null",
                data={"result": None},
            )

        output = json.dumps(result, indent=2, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)

        return ToolResult(
            success=True,
            output=output,
            data={"result": result},
        )


class YamlToJsonTool(BaseTool):
    """Convert between YAML and JSON formats."""

    name = "yaml_to_json"
    description = (
        "Convert data between YAML and JSON formats. "
        "Specify direction as 'yaml_to_json' or 'json_to_yaml'."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "The input data string (YAML or JSON).",
            },
            "direction": {
                "type": "string",
                "enum": ["yaml_to_json", "json_to_yaml"],
                "description": "Conversion direction.",
            },
        },
        "required": ["input", "direction"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raw: str = arguments["input"]
        direction: str = arguments["direction"]

        if direction == "yaml_to_json":
            if yaml is None:
                return ToolResult(success=False, output="PyYAML is not installed")
            try:
                data = yaml.safe_load(raw)
            except yaml.YAMLError as exc:
                return ToolResult(success=False, output=f"Invalid YAML: {exc}")
            output = json.dumps(data, indent=2, ensure_ascii=False)
            return ToolResult(success=True, output=output, data={"result": data})

        elif direction == "json_to_yaml":
            if yaml is None:
                return ToolResult(success=False, output="PyYAML is not installed")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                return ToolResult(success=False, output=f"Invalid JSON: {exc}")
            output = yaml.dump(data, default_flow_style=False, allow_unicode=True)
            return ToolResult(success=True, output=output, data={"result": data})

        else:
            return ToolResult(success=False, output=f"Unknown direction: {direction}")
