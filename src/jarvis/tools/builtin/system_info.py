"""System information tools."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class SystemInfoTool(BaseTool):
    """Gather system information: OS, CPU, memory, disk usage."""

    name = "system_info"
    description = (
        "Return system information including OS, architecture, CPU count, "
        "memory usage, and disk usage for the root or specified mount point."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "disk_path": {
                "type": "string",
                "description": "Path to check disk usage for (default '/').",
                "default": "/",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        disk_path = arguments.get("disk_path", "/")

        info: dict[str, Any] = {
            "os": platform.system(),
            "os_version": platform.version(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "processor": platform.processor() or "unknown",
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
        }

        # Disk usage
        try:
            usage = shutil.disk_usage(disk_path)
            info["disk"] = {
                "path": disk_path,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": round(usage.used / usage.total * 100, 1),
            }
        except OSError as exc:
            info["disk"] = {"error": str(exc)}

        # Memory info (best-effort, platform-dependent)
        try:
            if platform.system() == "Darwin":
                proc = await asyncio.create_subprocess_exec(
                    "sysctl", "-n", "hw.memsize",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                total_mem = int(stdout.decode().strip())
                info["memory_total_gb"] = round(total_mem / (1024**3), 2)
            elif platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            info["memory_total_gb"] = round(kb / (1024**2), 2)
                            break
        except Exception:
            pass  # Non-critical

        lines = [
            f"OS: {info['os']} ({info['platform']})",
            f"Architecture: {info['architecture']}",
            f"Processor: {info['processor']}",
            f"CPU count: {info['cpu_count']}",
            f"Python: {info['python_version']}",
        ]
        if "memory_total_gb" in info:
            lines.append(f"Memory: {info['memory_total_gb']} GB")
        if isinstance(info.get("disk"), dict) and "total_gb" in info["disk"]:
            d = info["disk"]
            lines.append(f"Disk ({d['path']}): {d['used_gb']}/{d['total_gb']} GB ({d['percent_used']}% used)")

        return ToolResult(success=True, output="\n".join(lines), data=info)


class ProcessListTool(BaseTool):
    """List running processes."""

    name = "process_list"
    description = (
        "List running processes, optionally filtering by name. "
        "Uses 'ps aux' on macOS/Linux."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "description": "Only show processes matching this substring (case-insensitive).",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name_filter: str | None = arguments.get("filter")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ps", "aux",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="ps command timed out")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run ps: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        lines = stdout.decode(errors="replace").splitlines()
        if not lines:
            return ToolResult(success=True, output="(no processes)")

        header = lines[0]
        process_lines = lines[1:]

        if name_filter:
            filt = name_filter.lower()
            process_lines = [l for l in process_lines if filt in l.lower()]

        # Limit output to avoid overwhelming responses
        total = len(process_lines)
        if total > 100:
            process_lines = process_lines[:100]
            truncation_note = f"\n... ({total - 100} more processes not shown)"
        else:
            truncation_note = ""

        output = header + "\n" + "\n".join(process_lines) + truncation_note
        return ToolResult(
            success=True,
            output=output,
            data={"count": total, "truncated": total > 100},
        )
