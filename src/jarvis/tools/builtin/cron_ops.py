"""Cron expression tools: parse and validate cron expressions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult

# ---------------------------------------------------------------------------
# Cron field specifications
# ---------------------------------------------------------------------------

_FIELD_SPECS = [
    {"name": "minute",     "min": 0,  "max": 59},
    {"name": "hour",       "min": 0,  "max": 23},
    {"name": "day_of_month", "min": 1, "max": 31},
    {"name": "month",      "min": 1,  "max": 12},
    {"name": "day_of_week", "min": 0,  "max": 6},
]

_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DOW_NAMES = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}


def _parse_field(field: str, spec: dict[str, Any]) -> tuple[bool, str, set[int]]:
    """Parse a single cron field and return (valid, description, values)."""
    name = spec["name"]
    lo, hi = spec["min"], spec["max"]

    # Replace named values
    f = field.lower()
    if name == "month":
        for k, v in _MONTH_NAMES.items():
            f = f.replace(k, str(v))
    elif name == "day_of_week":
        for k, v in _DOW_NAMES.items():
            f = f.replace(k, str(v))

    values: set[int] = set()

    if f == "*":
        return True, f"every {name}", set(range(lo, hi + 1))

    parts = f.split(",")
    descriptions: list[str] = []
    for part in parts:
        # Handle step: */N or M-N/S
        step = 1
        if "/" in part:
            range_part, step_str = part.split("/", 1)
            try:
                step = int(step_str)
                if step < 1:
                    return False, f"invalid step '{step_str}' in {name}", set()
            except ValueError:
                return False, f"invalid step '{step_str}' in {name}", set()
        else:
            range_part = part

        # Handle range: M-N or * or single value
        if range_part == "*":
            r_lo, r_hi = lo, hi
            descriptions.append(f"every {step} {name}(s)" if step > 1 else f"every {name}")
        elif "-" in range_part:
            try:
                a, b = range_part.split("-", 1)
                r_lo, r_hi = int(a), int(b)
            except ValueError:
                return False, f"invalid range '{range_part}' in {name}", set()
            if r_lo < lo or r_hi > hi or r_lo > r_hi:
                return False, f"range {r_lo}-{r_hi} out of bounds for {name} ({lo}-{hi})", set()
            descriptions.append(f"{name} {r_lo}-{r_hi}" + (f" step {step}" if step > 1 else ""))
        else:
            try:
                val = int(range_part)
            except ValueError:
                return False, f"invalid value '{range_part}' in {name}", set()
            if val < lo or val > hi:
                return False, f"value {val} out of bounds for {name} ({lo}-{hi})", set()
            r_lo, r_hi = val, val
            descriptions.append(f"{name} {val}")

        values.update(range(r_lo, r_hi + 1, step))

    return True, ", ".join(descriptions), values


def _describe_cron(expression: str) -> tuple[bool, str, list[dict[str, Any]]]:
    """Parse a full cron expression and return (valid, description, field_details)."""
    parts = expression.strip().split()
    if len(parts) != 5:
        return False, f"Expected 5 fields, got {len(parts)}", []

    descriptions: list[str] = []
    field_details: list[dict[str, Any]] = []
    for i, (field, spec) in enumerate(zip(parts, _FIELD_SPECS)):
        valid, desc, values = _parse_field(field, spec)
        if not valid:
            return False, desc, []
        descriptions.append(desc)
        field_details.append({
            "field": spec["name"],
            "expression": field,
            "description": desc,
            "values": sorted(values)[:20],  # cap for display
        })

    human = "At " + descriptions[0] + " past " + descriptions[1]
    if descriptions[2] != "every day_of_month":
        human += ", on " + descriptions[2]
    if descriptions[3] != "every month":
        human += ", in " + descriptions[3]
    if descriptions[4] != "every day_of_week":
        human += ", on " + descriptions[4]

    return True, human, field_details


def _next_runs(expression: str, count: int = 5, from_time: datetime | None = None) -> list[str]:
    """Compute the next N run times for a cron expression (simplified)."""
    parts = expression.strip().split()
    if len(parts) != 5:
        return []

    field_values: list[set[int]] = []
    for field, spec in zip(parts, _FIELD_SPECS):
        valid, _, values = _parse_field(field, spec)
        if not valid:
            return []
        field_values.append(values)

    minute_vals, hour_vals, dom_vals, month_vals, dow_vals = field_values

    now = from_time or datetime.now(timezone.utc)
    # Start from next minute
    current = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

    results: list[str] = []
    max_iterations = 60 * 24 * 400  # up to ~400 days
    for _ in range(max_iterations):
        if (current.month in month_vals and
                current.day in dom_vals and
                current.weekday() in {(d - 1) % 7 for d in dow_vals} | ({6} if 0 in dow_vals else set()) and
                current.hour in hour_vals and
                current.minute in minute_vals):
            # Re-check day_of_week properly: cron uses 0=Sun
            py_dow = current.weekday()  # 0=Mon
            cron_dow = (py_dow + 1) % 7  # convert to 0=Sun
            if cron_dow in dow_vals:
                results.append(current.strftime("%Y-%m-%d %H:%M UTC"))
                if len(results) >= count:
                    break
        current += timedelta(minutes=1)

    return results


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class CronParseTool(BaseTool):
    """Parse a cron expression into a human-readable schedule."""

    name = "cron_parse"
    description = (
        "Parse a cron expression (5 fields: minute hour day month weekday) "
        "into a human-readable schedule and compute the next 5 run times."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Cron expression with 5 fields (e.g. '0 9 * * 1-5').",
            },
        },
        "required": ["expression"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        expr = arguments["expression"]
        valid, description, fields = _describe_cron(expr)
        if not valid:
            return ToolResult(success=False, output=f"Invalid cron expression: {description}")

        next_times = _next_runs(expr, count=5)
        output_lines = [
            f"Expression: {expr}",
            f"Schedule: {description}",
            "",
            "Next 5 runs (UTC):",
        ]
        for i, t in enumerate(next_times, 1):
            output_lines.append(f"  {i}. {t}")
        if not next_times:
            output_lines.append("  (could not compute -- expression may be too restrictive)")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "expression": expr,
                "description": description,
                "fields": fields,
                "next_runs": next_times,
            },
        )


class CronValidateTool(BaseTool):
    """Validate a cron expression and explain any errors."""

    name = "cron_validate"
    description = (
        "Validate a cron expression (5 fields). "
        "Returns whether the expression is valid and explains any errors."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Cron expression to validate.",
            },
        },
        "required": ["expression"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        expr = arguments["expression"]
        valid, description, fields = _describe_cron(expr)

        if valid:
            return ToolResult(
                success=True,
                output=f"Valid cron expression: {expr}\nSchedule: {description}",
                data={"valid": True, "expression": expr, "description": description, "fields": fields},
            )
        else:
            return ToolResult(
                success=True,
                output=f"Invalid cron expression: {expr}\nError: {description}",
                data={"valid": False, "expression": expr, "error": description},
            )
