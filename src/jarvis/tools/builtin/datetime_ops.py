"""Date and time tools: current datetime and date arithmetic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


def _get_timezone(tz_name: str) -> timezone:
    """Parse a timezone string into a timezone object.

    Supports 'UTC', fixed offsets like '+08:00', '-05:00', and common
    abbreviation-like names mapped to offsets.
    """
    tz_upper = tz_name.upper().strip()
    if tz_upper == "UTC":
        return timezone.utc

    # Common named offsets
    _named: dict[str, float] = {
        "EST": -5, "EDT": -4,
        "CST": -6, "CDT": -5,
        "MST": -7, "MDT": -6,
        "PST": -8, "PDT": -7,
        "GMT": 0,
        "CET": 1, "CEST": 2,
        "JST": 9,
        "KST": 9,
        "IST": 5.5,
        "CST_CN": 8,  # China Standard Time
        "AEST": 10, "AEDT": 11,
    }

    if tz_upper in _named:
        hours = _named[tz_upper]
        return timezone(timedelta(hours=hours))

    # Try parsing as offset like +08:00 or -5
    try:
        if ":" in tz_name:
            sign = -1 if tz_name.startswith("-") else 1
            parts = tz_name.lstrip("+-").split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
        else:
            offset_hours = float(tz_name)
            return timezone(timedelta(hours=offset_hours))
    except (ValueError, IndexError):
        pass

    raise ValueError(f"Unknown timezone: {tz_name}")


class DateTimeTool(BaseTool):
    """Get the current date and time."""

    name = "datetime_info"
    description = (
        "Get the current date and time in various formats. Supports different "
        "timezones including UTC, EST, PST, JST, CST, and fixed offsets like +08:00."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone name or offset (default: UTC). Examples: UTC, EST, PST, +08:00.",
                "default": "UTC",
            },
            "format": {
                "type": "string",
                "description": "Custom strftime format string. If omitted, returns multiple formats.",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        tz_name: str = arguments.get("timezone", "UTC")
        fmt: str | None = arguments.get("format")

        try:
            tz = _get_timezone(tz_name)
        except ValueError as exc:
            return ToolResult(success=False, output=str(exc))

        now = datetime.now(tz)

        if fmt:
            try:
                formatted = now.strftime(fmt)
                return ToolResult(
                    success=True,
                    output=formatted,
                    data={"datetime": now.isoformat(), "timezone": tz_name, "formatted": formatted},
                )
            except (ValueError, KeyError) as exc:
                return ToolResult(success=False, output=f"Invalid format string: {exc}")

        iso = now.isoformat()
        unix = int(now.timestamp())
        date = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        day_of_week = now.strftime("%A")

        output = (
            f"Timezone: {tz_name}\n"
            f"ISO 8601: {iso}\n"
            f"Date: {date}\n"
            f"Time: {time_str}\n"
            f"Day: {day_of_week}\n"
            f"Unix timestamp: {unix}"
        )
        return ToolResult(
            success=True,
            output=output,
            data={
                "iso": iso,
                "date": date,
                "time": time_str,
                "day_of_week": day_of_week,
                "unix_timestamp": unix,
                "timezone": tz_name,
            },
        )


class DateCalcTool(BaseTool):
    """Perform date arithmetic (add or subtract time)."""

    name = "date_calc"
    description = (
        "Add or subtract days, hours, and minutes from a date. "
        "Input date should be in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). "
        "Returns the resulting date."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Starting date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).",
            },
            "operation": {
                "type": "string",
                "enum": ["add", "subtract"],
                "description": "Whether to 'add' or 'subtract' time.",
            },
            "days": {
                "type": "integer",
                "description": "Number of days to add/subtract (default 0).",
                "default": 0,
            },
            "hours": {
                "type": "integer",
                "description": "Number of hours to add/subtract (default 0).",
                "default": 0,
            },
            "minutes": {
                "type": "integer",
                "description": "Number of minutes to add/subtract (default 0).",
                "default": 0,
            },
        },
        "required": ["date", "operation"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        date_str: str = arguments["date"]
        operation: str = arguments["operation"]
        days: int = arguments.get("days", 0)
        hours: int = arguments.get("hours", 0)
        minutes: int = arguments.get("minutes", 0)

        try:
            # Try full ISO format first, then date-only
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str)
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return ToolResult(
                success=False,
                output=f"Invalid date format: {date_str}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.",
            )

        delta = timedelta(days=days, hours=hours, minutes=minutes)
        if operation == "subtract":
            delta = -delta

        result_dt = dt + delta
        result_iso = result_dt.isoformat()
        result_date = result_dt.strftime("%Y-%m-%d")
        result_day = result_dt.strftime("%A")

        # Describe the operation
        parts = []
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        delta_desc = ", ".join(parts) if parts else "0"

        output = (
            f"{date_str} {operation} {delta_desc}\n"
            f"Result: {result_iso}\n"
            f"Day: {result_day}"
        )
        return ToolResult(
            success=True,
            output=output,
            data={
                "original": date_str,
                "operation": operation,
                "result": result_iso,
                "result_date": result_date,
                "day_of_week": result_day,
            },
        )
