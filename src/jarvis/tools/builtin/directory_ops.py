"""Directory operation tools: listing and searching."""

from __future__ import annotations

import fnmatch
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class ListDirectoryTool(BaseTool):
    """List directory contents with file details."""

    name = "list_directory"
    description = (
        "List the contents of a directory, showing file names, sizes, and "
        "modification times. Supports recursive listing and glob filtering."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The directory path to list.",
            },
            "recursive": {
                "type": "boolean",
                "description": "Whether to list recursively (default false).",
                "default": False,
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern to filter entries (e.g. '*.py').",
            },
        },
        "required": ["path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path_str: str = arguments["path"]
        recursive: bool = arguments.get("recursive", False)
        pattern: str | None = arguments.get("pattern")

        target = Path(path_str).expanduser().resolve()

        if not target.exists():
            return ToolResult(success=False, output=f"Path not found: {target}")
        if not target.is_dir():
            return ToolResult(success=False, output=f"Not a directory: {target}")

        entries: list[dict[str, Any]] = []
        max_entries = 1000  # Safety limit

        try:
            if recursive:
                iterator = target.rglob(pattern or "*")
            else:
                iterator = target.glob(pattern or "*")

            for item in iterator:
                if len(entries) >= max_entries:
                    break
                try:
                    stat = item.stat()
                    entries.append({
                        "name": str(item.relative_to(target)),
                        "type": "dir" if item.is_dir() else "file",
                        "size": stat.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    })
                except OSError:
                    entries.append({
                        "name": str(item.relative_to(target)),
                        "type": "unknown",
                        "size": 0,
                        "modified": "unknown",
                    })
        except PermissionError as exc:
            return ToolResult(success=False, output=f"Permission denied: {exc}")

        # Format output
        lines = []
        for e in sorted(entries, key=lambda x: x["name"]):
            type_indicator = "d" if e["type"] == "dir" else "f"
            size_str = _format_size(e["size"]) if e["type"] == "file" else "    -"
            lines.append(f"[{type_indicator}] {size_str:>8}  {e['modified']}  {e['name']}")

        header = f"Directory: {target} ({len(entries)} entries)"
        if len(entries) >= max_entries:
            header += f" (limited to {max_entries})"

        output = header + "\n" + "\n".join(lines) if lines else header + "\n(empty)"
        return ToolResult(
            success=True,
            output=output,
            data={"path": str(target), "entries": entries, "count": len(entries)},
        )


class FindFilesTool(BaseTool):
    """Find files matching name and content criteria."""

    name = "find_files"
    description = (
        "Find files in a directory matching a glob pattern, optionally "
        "filtering by content. Returns matching file paths."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "The directory to search in.",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern for file names (e.g. '*.py', '*.txt').",
                "default": "*",
            },
            "content_match": {
                "type": "string",
                "description": "Optional string to search for inside matching files.",
            },
        },
        "required": ["directory"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        directory: str = arguments["directory"]
        pattern: str = arguments.get("pattern", "*")
        content_match: str | None = arguments.get("content_match")

        target = Path(directory).expanduser().resolve()

        if not target.exists():
            return ToolResult(success=False, output=f"Directory not found: {target}")
        if not target.is_dir():
            return ToolResult(success=False, output=f"Not a directory: {target}")

        results: list[dict[str, Any]] = []
        max_results = 500
        files_searched = 0

        try:
            for filepath in target.rglob(pattern):
                if not filepath.is_file():
                    continue
                files_searched += 1

                if content_match:
                    try:
                        text = filepath.read_text(encoding="utf-8", errors="replace")
                        if content_match not in text:
                            continue
                        # Find line numbers of matches
                        match_lines = []
                        for i, line in enumerate(text.splitlines(), 1):
                            if content_match in line:
                                match_lines.append(i)
                                if len(match_lines) >= 5:
                                    break
                        results.append({
                            "path": str(filepath),
                            "match_lines": match_lines,
                        })
                    except (OSError, UnicodeDecodeError):
                        continue
                else:
                    results.append({"path": str(filepath)})

                if len(results) >= max_results:
                    break
        except PermissionError as exc:
            return ToolResult(success=False, output=f"Permission denied: {exc}")

        if not results:
            output = f"No files found matching '{pattern}'"
            if content_match:
                output += f" containing '{content_match}'"
            return ToolResult(success=True, output=output, data={"matches": [], "count": 0})

        lines = []
        for r in results:
            line = r["path"]
            if "match_lines" in r:
                line += f" (lines: {', '.join(map(str, r['match_lines']))})"
            lines.append(line)

        header = f"Found {len(results)} file(s) (searched {files_searched})"
        if len(results) >= max_results:
            header += f" (limited to {max_results})"

        output = header + "\n" + "\n".join(lines)
        return ToolResult(
            success=True,
            output=output,
            data={"matches": results, "count": len(results)},
        )


def _format_size(size: int) -> str:
    """Format a byte size into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f}TB"
