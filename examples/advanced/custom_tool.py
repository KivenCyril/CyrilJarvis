"""Custom Tool Creation Demo.

Shows how to create, register, and use custom tools in JARVIS.
Includes examples of sync tools, async tools, and tools with
complex parameter schemas.

Usage:
    python examples/advanced/custom_tool.py
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult
from jarvis.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Example 1: Simple synchronous tool
# ---------------------------------------------------------------------------

class WordCountTool(BaseTool):
    """Count words, characters, and lines in text."""

    name = "word_count"
    description = (
        "Analyze text and return word count, character count, line count, "
        "and average word length."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to analyze.",
            },
            "include_whitespace": {
                "type": "boolean",
                "description": "Include whitespace in character count (default: false).",
            },
        },
        "required": ["text"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        text: str = arguments["text"]
        include_ws: bool = arguments.get("include_whitespace", False)

        words = text.split()
        lines = text.count("\n") + 1
        char_count = len(text) if include_ws else len(text.replace(" ", "").replace("\n", ""))
        avg_word_len = sum(len(w) for w in words) / len(words) if words else 0

        result = {
            "words": len(words),
            "characters": char_count,
            "lines": lines,
            "avg_word_length": round(avg_word_len, 2),
            "unique_words": len(set(w.lower() for w in words)),
        }

        return ToolResult(
            success=True,
            output=f"Words: {result['words']}, Characters: {result['characters']}, Lines: {result['lines']}",
            data=result,
        )


# ---------------------------------------------------------------------------
# Example 2: Tool with external service simulation
# ---------------------------------------------------------------------------

class WeatherTool(BaseTool):
    """Get weather information for a location (simulated)."""

    name = "weather"
    description = "Get current weather conditions for a specified location."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name or coordinates (e.g. 'London' or '51.5,-0.1').",
            },
            "units": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature units (default: celsius).",
            },
        },
        "required": ["location"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        location: str = arguments["location"]
        units: str = arguments.get("units", "celsius")

        # Simulated weather data
        import random
        temp_c = random.randint(-5, 35)
        temp = temp_c if units == "celsius" else int(temp_c * 9 / 5 + 32)
        unit_symbol = "C" if units == "celsius" else "F"

        conditions = random.choice(["Sunny", "Cloudy", "Rainy", "Partly Cloudy", "Foggy"])
        humidity = random.randint(30, 90)
        wind_speed = random.randint(0, 30)

        result = {
            "location": location,
            "temperature": temp,
            "unit": unit_symbol,
            "conditions": conditions,
            "humidity": humidity,
            "wind_speed_kmh": wind_speed,
        }

        return ToolResult(
            success=True,
            output=f"Weather in {location}: {temp}{unit_symbol}, {conditions}, Humidity: {humidity}%",
            data=result,
        )


# ---------------------------------------------------------------------------
# Example 3: Tool with validation and complex logic
# ---------------------------------------------------------------------------

class DataTransformTool(BaseTool):
    """Transform data between different structures."""

    name = "data_transform"
    description = (
        "Transform structured data: flatten nested objects, pivot tables, "
        "filter rows, and compute aggregations."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "JSON string of input data.",
            },
            "operation": {
                "type": "string",
                "enum": ["flatten", "pivot", "filter", "aggregate"],
                "description": "Transformation operation to apply.",
            },
            "options": {
                "type": "object",
                "description": "Operation-specific options.",
            },
        },
        "required": ["data", "operation"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raw_data: str = arguments["data"]
        operation: str = arguments["operation"]
        options: dict = arguments.get("options", {})

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            return ToolResult(success=False, output=f"Invalid JSON: {exc}")

        if operation == "flatten":
            result = self._flatten(data)
        elif operation == "filter":
            result = self._filter(data, options)
        elif operation == "aggregate":
            result = self._aggregate(data, options)
        else:
            return ToolResult(success=False, output=f"Operation '{operation}' not yet implemented")

        output = json.dumps(result, indent=2, ensure_ascii=False)
        return ToolResult(success=True, output=output, data={"result": result})

    def _flatten(self, data: Any, prefix: str = "") -> dict:
        """Flatten a nested dict into dot-notation keys."""
        result = {}
        if isinstance(data, dict):
            for key, value in data.items():
                new_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    result.update(self._flatten(value, new_key))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        result.update(self._flatten(item, f"{new_key}.{i}"))
                else:
                    result[new_key] = value
        else:
            result[prefix] = data
        return result

    def _filter(self, data: list, options: dict) -> list:
        """Filter a list of dicts by field value."""
        field_name = options.get("field", "")
        value = options.get("value")
        operator = options.get("operator", "eq")

        if not field_name or not isinstance(data, list):
            return data

        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            item_val = item.get(field_name)
            if operator == "eq" and item_val == value:
                result.append(item)
            elif operator == "gt" and isinstance(item_val, (int, float)) and item_val > value:
                result.append(item)
            elif operator == "lt" and isinstance(item_val, (int, float)) and item_val < value:
                result.append(item)
            elif operator == "contains" and isinstance(item_val, str) and value in item_val:
                result.append(item)
        return result

    def _aggregate(self, data: list, options: dict) -> dict:
        """Compute aggregations on a list of dicts."""
        field_name = options.get("field", "")
        group_by = options.get("group_by")

        if not isinstance(data, list):
            return {"error": "Data must be a list"}

        values = [
            item.get(field_name) for item in data
            if isinstance(item, dict) and isinstance(item.get(field_name), (int, float))
        ]

        if not values:
            return {"error": f"No numeric values found for field '{field_name}'"}

        return {
            "field": field_name,
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": round(sum(values) / len(values), 4),
        }


# ---------------------------------------------------------------------------
# Demo: Register and use custom tools
# ---------------------------------------------------------------------------

async def main():
    """Demonstrate custom tool registration and usage."""
    # Create a registry and register our custom tools
    registry = ToolRegistry()
    registry.register(WordCountTool())
    registry.register(WeatherTool())
    registry.register(DataTransformTool())

    print("Registered tools:")
    for tool in registry.list_tools():
        print(f"  - {tool.name}: {tool.description[:60]}...")

    # Use word count tool
    print("\n--- Word Count Tool ---")
    result = await registry.execute("word_count", {
        "text": "The quick brown fox jumps over the lazy dog.\nThis is a second line.",
    })
    print(f"  {result.output}")
    print(f"  Data: {json.dumps(result.data, indent=2)}")

    # Use weather tool
    print("\n--- Weather Tool ---")
    result = await registry.execute("weather", {"location": "Tokyo", "units": "celsius"})
    print(f"  {result.output}")

    # Use data transform tool
    print("\n--- Data Transform Tool ---")
    sample_data = json.dumps([
        {"name": "Alice", "age": 30, "dept": "Engineering"},
        {"name": "Bob", "age": 25, "dept": "Engineering"},
        {"name": "Charlie", "age": 35, "dept": "Marketing"},
    ])

    result = await registry.execute("data_transform", {
        "data": sample_data,
        "operation": "aggregate",
        "options": {"field": "age"},
    })
    print(f"  Aggregate result: {result.output}")

    result = await registry.execute("data_transform", {
        "data": sample_data,
        "operation": "filter",
        "options": {"field": "dept", "value": "Engineering", "operator": "eq"},
    })
    print(f"  Filter result: {result.output}")

    print("\nCustom tool demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
