"""Git operation tools: status, diff, and log."""

from __future__ import annotations

import asyncio
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class GitStatusTool(BaseTool):
    """Run ``git status`` and return structured output."""

    name = "git_status"
    description = (
        "Run git status in the current or specified directory and return "
        "the working-tree status including staged, unstaged, and untracked files."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "repo_path": {
                "type": "string",
                "description": "Path to the git repository (default: current directory).",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        repo_path = arguments.get("repo_path", ".")
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", repo_path, "status", "--porcelain=v1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="git status timed out")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run git status: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        raw = stdout.decode(errors="replace")
        staged, unstaged, untracked = [], [], []
        for line in raw.splitlines():
            if len(line) < 3:
                continue
            x, y = line[0], line[1]
            filepath = line[3:]
            if x == "?":
                untracked.append(filepath)
            else:
                if x not in (" ", "?"):
                    staged.append(filepath)
                if y not in (" ", "?"):
                    unstaged.append(filepath)

        summary_parts = []
        if staged:
            summary_parts.append(f"Staged ({len(staged)}): {', '.join(staged)}")
        if unstaged:
            summary_parts.append(f"Unstaged ({len(unstaged)}): {', '.join(unstaged)}")
        if untracked:
            summary_parts.append(f"Untracked ({len(untracked)}): {', '.join(untracked)}")

        output = "\n".join(summary_parts) if summary_parts else "Working tree clean"
        return ToolResult(
            success=True,
            output=output,
            data={"staged": staged, "unstaged": unstaged, "untracked": untracked},
        )


class GitDiffTool(BaseTool):
    """Show the diff of staged or unstaged changes."""

    name = "git_diff"
    description = (
        "Show the git diff of staged or unstaged changes, optionally for a specific file."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "If true, show staged (--cached) diff. Default false.",
                "default": False,
            },
            "file_path": {
                "type": "string",
                "description": "Limit diff to a specific file path.",
            },
            "repo_path": {
                "type": "string",
                "description": "Path to the git repository (default: current directory).",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        repo_path = arguments.get("repo_path", ".")
        staged = arguments.get("staged", False)
        file_path = arguments.get("file_path")

        cmd = ["git", "-C", repo_path, "diff"]
        if staged:
            cmd.append("--cached")
        if file_path:
            cmd.extend(["--", file_path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="git diff timed out")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run git diff: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        diff_text = stdout.decode(errors="replace")
        if not diff_text.strip():
            diff_text = "(no differences)"

        return ToolResult(success=True, output=diff_text)


class GitLogTool(BaseTool):
    """Show recent git commits."""

    name = "git_log"
    description = (
        "Show the most recent git commits with hash, author, date, and message."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of commits to show (default 10).",
                "default": 10,
            },
            "file_path": {
                "type": "string",
                "description": "Limit log to a specific file path.",
            },
            "repo_path": {
                "type": "string",
                "description": "Path to the git repository (default: current directory).",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        repo_path = arguments.get("repo_path", ".")
        count = arguments.get("count", 10)
        file_path = arguments.get("file_path")

        fmt = "%H|%an|%ai|%s"
        cmd = ["git", "-C", repo_path, "log", f"-{count}", f"--format={fmt}"]
        if file_path:
            cmd.extend(["--", file_path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="git log timed out")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run git log: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        raw = stdout.decode(errors="replace").strip()
        if not raw:
            return ToolResult(success=True, output="(no commits)", data={"commits": []})

        commits = []
        for line in raw.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })

        display_lines = [
            f"{c['hash'][:8]} {c['date'][:10]} {c['author']} - {c['message']}"
            for c in commits
        ]
        return ToolResult(
            success=True,
            output="\n".join(display_lines),
            data={"commits": commits},
        )
