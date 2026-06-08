"""Math operation tools: calculator and unit converter."""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


# Safe math operations for the calculator
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "pi": math.pi,
    "e": math.e,
    "max": max,
    "min": min,
}


def _safe_eval_node(node: ast.AST) -> Any:
    """Recursively evaluate an AST node with only safe operations."""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        # Guard against huge exponents
        if op_type == ast.Pow and isinstance(right, (int, float)) and abs(right) > 1000:
            raise ValueError("Exponent too large (max 1000)")
        return _SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _SAFE_OPERATORS[op_type](_safe_eval_node(node.operand))
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are supported")
        func_name = node.func.id
        if func_name not in _SAFE_FUNCTIONS:
            raise ValueError(f"Unknown function: {func_name}")
        func = _SAFE_FUNCTIONS[func_name]
        args = [_safe_eval_node(arg) for arg in node.args]
        return func(*args)
    elif isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCTIONS:
            val = _SAFE_FUNCTIONS[node.id]
            if isinstance(val, (int, float)):
                return val
        raise ValueError(f"Unknown variable: {node.id}")
    elif isinstance(node, ast.Tuple):
        return tuple(_safe_eval_node(elt) for elt in node.elts)
    elif isinstance(node, ast.List):
        return [_safe_eval_node(elt) for elt in node.elts]
    else:
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")


class CalculatorTool(BaseTool):
    """Safely evaluate mathematical expressions."""

    name = "calculator"
    description = (
        "Evaluate mathematical expressions safely without using eval(). "
        "Supports +, -, *, /, //, %, ** and functions: sqrt, abs, ceil, "
        "floor, round, log, log2, log10, sin, cos, tan, max, min. "
        "Constants: pi, e."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate, e.g. 'sqrt(144) + 3 * 2'.",
            },
        },
        "required": ["expression"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        expression: str = arguments["expression"]

        try:
            tree = ast.parse(expression, mode="eval")
            result = _safe_eval_node(tree)

            # Format the result nicely
            if isinstance(result, float):
                if result == int(result) and not math.isinf(result):
                    display = str(int(result))
                else:
                    display = f"{result:.10g}"
            else:
                display = str(result)

            return ToolResult(
                success=True,
                output=f"{expression} = {display}",
                data={"expression": expression, "result": result},
            )
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
            return ToolResult(success=False, output=f"Calculation error: {exc}")
        except SyntaxError:
            return ToolResult(success=False, output=f"Invalid expression syntax: {expression}")


# Unit conversion tables
_CONVERSIONS: dict[str, dict[str, float]] = {
    # Length: base unit = meters
    "length": {
        "m": 1.0,
        "km": 1000.0,
        "cm": 0.01,
        "mm": 0.001,
        "mi": 1609.344,
        "yd": 0.9144,
        "ft": 0.3048,
        "in": 0.0254,
    },
    # Weight: base unit = kilograms
    "weight": {
        "kg": 1.0,
        "g": 0.001,
        "mg": 0.000001,
        "lb": 0.45359237,
        "oz": 0.028349523125,
        "ton": 1000.0,
    },
    # Data: base unit = bytes
    "data": {
        "B": 1.0,
        "KB": 1024.0,
        "MB": 1024.0 ** 2,
        "GB": 1024.0 ** 3,
        "TB": 1024.0 ** 4,
        "PB": 1024.0 ** 5,
    },
    # Time: base unit = seconds
    "time": {
        "s": 1.0,
        "ms": 0.001,
        "min": 60.0,
        "h": 3600.0,
        "day": 86400.0,
        "week": 604800.0,
    },
    # Area: base unit = square meters
    "area": {
        "m2": 1.0,
        "km2": 1_000_000.0,
        "ft2": 0.09290304,
        "acre": 4046.8564224,
        "ha": 10_000.0,
    },
}

# Build a lookup from unit name to (category, factor)
_UNIT_LOOKUP: dict[str, tuple[str, float]] = {}
for _cat, _units in _CONVERSIONS.items():
    for _unit, _factor in _units.items():
        _UNIT_LOOKUP[_unit.lower()] = (_cat, _factor)


def _convert_temperature(value: float, from_u: str, to_u: str) -> float:
    """Convert between temperature units (C, F, K)."""
    # Normalise to Celsius first
    if from_u == "f":
        celsius = (value - 32) * 5 / 9
    elif from_u == "k":
        celsius = value - 273.15
    else:
        celsius = value

    # Convert from Celsius to target
    if to_u == "f":
        return celsius * 9 / 5 + 32
    elif to_u == "k":
        return celsius + 273.15
    return celsius


class UnitConvertTool(BaseTool):
    """Convert between common units."""

    name = "unit_convert"
    description = (
        "Convert a value between different units. Supported categories: "
        "length (m/km/cm/mm/mi/yd/ft/in), weight (kg/g/mg/lb/oz/ton), "
        "temperature (C/F/K), data (B/KB/MB/GB/TB/PB), "
        "time (s/ms/min/h/day/week), area (m2/km2/ft2/acre/ha)."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "value": {
                "type": "number",
                "description": "The numeric value to convert.",
            },
            "from_unit": {
                "type": "string",
                "description": "Source unit (e.g. 'km', 'lb', 'F', 'GB').",
            },
            "to_unit": {
                "type": "string",
                "description": "Target unit (e.g. 'mi', 'kg', 'C', 'MB').",
            },
        },
        "required": ["value", "from_unit", "to_unit"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        value: float = arguments["value"]
        from_unit: str = arguments["from_unit"]
        to_unit: str = arguments["to_unit"]

        from_lower = from_unit.lower()
        to_lower = to_unit.lower()

        # Handle temperature separately
        if from_lower in ("c", "f", "k") and to_lower in ("c", "f", "k"):
            result = _convert_temperature(value, from_lower, to_lower)
            return ToolResult(
                success=True,
                output=f"{value} {from_unit} = {result:.4g} {to_unit}",
                data={"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result},
            )

        from_info = _UNIT_LOOKUP.get(from_lower)
        to_info = _UNIT_LOOKUP.get(to_lower)

        if from_info is None:
            return ToolResult(success=False, output=f"Unknown unit: {from_unit}")
        if to_info is None:
            return ToolResult(success=False, output=f"Unknown unit: {to_unit}")

        from_cat, from_factor = from_info
        to_cat, to_factor = to_info

        if from_cat != to_cat:
            return ToolResult(
                success=False,
                output=f"Cannot convert between {from_cat} ({from_unit}) and {to_cat} ({to_unit})",
            )

        # Convert: value * from_factor gives base unit, then divide by to_factor
        result = value * from_factor / to_factor

        return ToolResult(
            success=True,
            output=f"{value} {from_unit} = {result:.6g} {to_unit}",
            data={"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": result},
        )
