from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    """Read the contents of a file from the local filesystem."""

    name = "read_file"
    description = (
        "Read a file and return its contents. "
        "Optionally limit the number of lines returned."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file.",
            },
            "max_lines": {
                "type": "integer",
                "description": (
                    "Maximum number of lines to return. "
                    "Omit or set to 0 to return the full file."
                ),
                "default": 0,
            },
        },
        "required": ["path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path_str: str = arguments["path"]
        max_lines: int = arguments.get("max_lines", 0)

        target = Path(path_str).expanduser().resolve()

        if not target.exists():
            return ToolResult(success=False, output=f"File not found: {target}")

        if not target.is_file():
            return ToolResult(success=False, output=f"Not a file: {target}")

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(success=False, output=f"Cannot read file: {exc}")

        if max_lines and max_lines > 0:
            lines = text.splitlines(keepends=True)
            text = "".join(lines[:max_lines])
            truncated = len(lines) > max_lines
        else:
            truncated = False

        return ToolResult(
            success=True,
            output=text,
            data={
                "path": str(target),
                "size": target.stat().st_size,
                "truncated": truncated,
            },
        )


class WriteFileTool(BaseTool):
    """Write content to a file, creating parent directories as needed."""

    name = "write_file"
    description = "Write text content to a file. Creates the file and parent directories if they do not exist."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file.",
            },
            "content": {
                "type": "string",
                "description": "The text content to write.",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path_str: str = arguments["path"]
        content: str = arguments["content"]

        target = Path(path_str).expanduser().resolve()

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, output=f"Cannot write file: {exc}")

        return ToolResult(
            success=True,
            output=f"Wrote {len(content)} bytes to {target}",
            data={"path": str(target), "bytes_written": len(content)},
        )
