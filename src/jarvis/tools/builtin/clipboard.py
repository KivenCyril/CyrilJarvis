"""Clipboard tool for reading and writing system clipboard."""

from __future__ import annotations

import asyncio
import platform
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class ClipboardTool(BaseTool):
    """Read from or write to the system clipboard."""

    name = "clipboard"
    description = (
        "Read from or write to the system clipboard. "
        "Uses pbcopy/pbpaste on macOS and xclip on Linux."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write"],
                "description": "Whether to 'read' from or 'write' to the clipboard.",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the clipboard (required when action is 'write').",
            },
        },
        "required": ["action"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        action: str = arguments["action"]
        content: str | None = arguments.get("content")

        system = platform.system()

        if action == "write":
            if content is None:
                return ToolResult(
                    success=False,
                    output="Content is required when action is 'write'.",
                )
            return await self._write(content, system)
        elif action == "read":
            return await self._read(system)
        else:
            return ToolResult(success=False, output=f"Unknown action: {action}")

    async def _read(self, system: str) -> ToolResult:
        if system == "Darwin":
            cmd = ["pbpaste"]
        elif system == "Linux":
            cmd = ["xclip", "-selection", "clipboard", "-o"]
        else:
            return ToolResult(
                success=False,
                output=f"Clipboard not supported on {system}",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="Clipboard read timed out")
        except OSError as exc:
            return ToolResult(success=False, output=f"Clipboard read failed: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=f"Clipboard read error: {stderr.decode(errors='replace')}",
            )

        text = stdout.decode(errors="replace")
        return ToolResult(
            success=True,
            output=text,
            data={"length": len(text)},
        )

    async def _write(self, content: str, system: str) -> ToolResult:
        if system == "Darwin":
            cmd = ["pbcopy"]
        elif system == "Linux":
            cmd = ["xclip", "-selection", "clipboard"]
        else:
            return ToolResult(
                success=False,
                output=f"Clipboard not supported on {system}",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                proc.communicate(input=content.encode()), timeout=5
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="Clipboard write timed out")
        except OSError as exc:
            return ToolResult(success=False, output=f"Clipboard write failed: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=f"Clipboard write error: {stderr.decode(errors='replace')}",
            )

        return ToolResult(
            success=True,
            output=f"Wrote {len(content)} characters to clipboard.",
            data={"length": len(content)},
        )
