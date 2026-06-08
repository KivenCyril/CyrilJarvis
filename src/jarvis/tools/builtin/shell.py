from __future__ import annotations

import asyncio
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult

# Patterns that are too destructive to allow through a general-purpose shell
# tool.  The check is intentionally simple -- it catches the most common
# catastrophic mistakes without trying to be a full sandbox.
_BLOCKED_PATTERNS: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf ~/*",
    "mkfs.",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    ":(){:|:&};:",       # fork bomb
    "chmod -R 777 /",
    "chown -R",
    "> /dev/sda",
    "mv / ",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
]


class ShellTool(BaseTool):
    """Execute a shell command and capture its output."""

    name = "shell_execute"
    description = (
        "Execute a shell command and return its stdout and stderr. "
        "Use for running CLI tools, scripts, or system commands."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to wait for the command (default 30).",
                "default": 30,
            },
        },
        "required": ["command"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command: str = arguments["command"]
        timeout: int = arguments.get("timeout", 30)

        # Safety check
        cmd_lower = command.lower().strip()
        for pattern in _BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return ToolResult(
                    success=False,
                    output=f"Blocked: command matches dangerous pattern '{pattern}'",
                )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()  # type: ignore[union-attr]
            return ToolResult(
                success=False,
                output=f"Command timed out after {timeout}s",
            )
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run command: {exc}")

        stdout_text = stdout.decode(errors="replace") if stdout else ""
        stderr_text = stderr.decode(errors="replace") if stderr else ""

        success = proc.returncode == 0
        parts: list[str] = []
        if stdout_text:
            parts.append(stdout_text)
        if stderr_text:
            parts.append(f"[stderr]\n{stderr_text}")

        output = "\n".join(parts) or ("(no output)" if success else "(no output)")

        return ToolResult(
            success=success,
            output=output,
            data={"returncode": proc.returncode},
        )
