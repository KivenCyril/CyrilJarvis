"""UUID tools: generate and validate UUIDs."""

from __future__ import annotations

import re
import uuid
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult

# UUID regex pattern
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class UUIDGenerateTool(BaseTool):
    """Generate one or more UUIDs."""

    name = "uuid_generate"
    description = (
        "Generate UUID(s). Supports version 1 (time-based) and version 4 (random). "
        "Can generate multiple UUIDs at once."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "version": {
                "type": "integer",
                "enum": [1, 4],
                "description": "UUID version: 1 (time-based) or 4 (random). Default: 4.",
                "default": 4,
            },
            "count": {
                "type": "integer",
                "description": "Number of UUIDs to generate (1-100). Default: 1.",
                "default": 1,
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        version: int = arguments.get("version", 4)
        count: int = arguments.get("count", 1)

        if version not in (1, 4):
            return ToolResult(success=False, output=f"Unsupported UUID version: {version}. Use 1 or 4.")

        if count < 1 or count > 100:
            return ToolResult(success=False, output="Count must be between 1 and 100.")

        generator = uuid.uuid1 if version == 1 else uuid.uuid4
        uuids = [str(generator()) for _ in range(count)]

        if count == 1:
            output = uuids[0]
        else:
            output = "\n".join(f"{i+1}. {u}" for i, u in enumerate(uuids))

        return ToolResult(
            success=True,
            output=output,
            data={"version": version, "count": count, "uuids": uuids},
        )


class UUIDValidateTool(BaseTool):
    """Validate a UUID string."""

    name = "uuid_validate"
    description = (
        "Validate a UUID string. Checks format and determines the UUID version."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "description": "The UUID string to validate.",
            },
        },
        "required": ["value"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        value = arguments["value"].strip()

        # Check basic format
        if not _UUID_PATTERN.match(value):
            # Try without dashes
            nodash = value.replace("-", "")
            if len(nodash) == 32 and all(c in "0123456789abcdefABCDEF" for c in nodash):
                return ToolResult(
                    success=True,
                    output=f"Invalid UUID format (missing dashes). Did you mean: "
                           f"{nodash[:8]}-{nodash[8:12]}-{nodash[12:16]}-{nodash[16:20]}-{nodash[20:]}?",
                    data={"valid": False, "reason": "missing dashes"},
                )
            return ToolResult(
                success=True,
                output=f"Invalid UUID: '{value}' does not match UUID format.",
                data={"valid": False, "reason": "invalid format"},
            )

        try:
            parsed = uuid.UUID(value)
            version = parsed.version
            variant = str(parsed.variant)

            return ToolResult(
                success=True,
                output=f"Valid UUID (version {version}): {parsed}",
                data={
                    "valid": True,
                    "uuid": str(parsed),
                    "version": version,
                    "variant": variant,
                    "hex": parsed.hex,
                    "int": str(parsed.int),
                },
            )
        except ValueError as e:
            return ToolResult(
                success=True,
                output=f"Invalid UUID: {e}",
                data={"valid": False, "reason": str(e)},
            )
