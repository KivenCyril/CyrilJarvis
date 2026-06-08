"""Environment variable tools: get and list environment variables."""

from __future__ import annotations

import fnmatch
import os
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class EnvVarTool(BaseTool):
    """Get the value of an environment variable."""

    name = "env_get"
    description = (
        "Get the value of an environment variable. "
        "Returns the value or a default if the variable is not set."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the environment variable.",
            },
            "default": {
                "type": "string",
                "description": "Default value if the variable is not set.",
                "default": "",
            },
        },
        "required": ["name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        var_name: str = arguments["name"]
        default: str = arguments.get("default", "")

        if not var_name:
            return ToolResult(success=False, output="Variable name cannot be empty.")

        value = os.environ.get(var_name)
        is_set = value is not None

        if is_set:
            # Mask potentially sensitive values
            display_value = value
            sensitive_patterns = ["password", "secret", "token", "key", "credential", "api_key"]
            if any(p in var_name.lower() for p in sensitive_patterns):
                display_value = value[:3] + "***" + value[-2:] if len(value) > 5 else "***"
                output = f"{var_name}={display_value} (masked for security)"
            else:
                output = f"{var_name}={value}"
        else:
            value = default
            output = f"{var_name} is not set"
            if default:
                output += f" (using default: {default})"

        return ToolResult(
            success=True,
            output=output,
            data={"name": var_name, "value": value, "is_set": is_set},
        )


class EnvListTool(BaseTool):
    """List environment variables matching a pattern."""

    name = "env_list"
    description = (
        "List environment variables matching a glob pattern. "
        "Uses fnmatch-style pattern matching (e.g., 'PATH*', 'JAVA_*', '*HOME*')."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match variable names (default: '*').",
                "default": "*",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        pattern: str = arguments.get("pattern", "*")

        matching: dict[str, str] = {}
        for key, value in sorted(os.environ.items()):
            if fnmatch.fnmatch(key, pattern):
                matching[key] = value

        if not matching:
            return ToolResult(
                success=True,
                output=f"No environment variables matching '{pattern}'.",
                data={"pattern": pattern, "count": 0, "variables": {}},
            )

        # Mask sensitive values in display
        sensitive_patterns = ["password", "secret", "token", "key", "credential", "api_key"]
        lines: list[str] = [f"Environment variables matching '{pattern}' ({len(matching)} found):"]
        display_vars: dict[str, str] = {}
        for key, value in matching.items():
            if any(p in key.lower() for p in sensitive_patterns):
                display = value[:3] + "***" if len(value) > 3 else "***"
            else:
                display = value[:80] + "..." if len(value) > 80 else value
            lines.append(f"  {key}={display}")
            display_vars[key] = display

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"pattern": pattern, "count": len(matching), "variables": display_vars},
        )
