"""Docker operation tools: list containers, logs, exec, and images."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class DockerListTool(BaseTool):
    """List running Docker containers."""

    name = "docker_ps"
    description = (
        "List running Docker containers with their ID, image, status, "
        "ports, and names. Optionally include stopped containers."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "all": {
                "type": "boolean",
                "description": "If true, show all containers (including stopped). Default false.",
                "default": False,
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        show_all = arguments.get("all", False)
        cmd = ["docker", "ps", "--format", "{{json .}}"]
        if show_all:
            cmd.insert(2, "-a")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="docker ps timed out")
        except FileNotFoundError:
            return ToolResult(success=False, output="Docker is not installed or not in PATH")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run docker ps: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        raw = stdout.decode(errors="replace").strip()
        if not raw:
            return ToolResult(
                success=True,
                output="No containers running",
                data={"containers": [], "count": 0},
            )

        containers = []
        for line in raw.splitlines():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        lines = []
        for c in containers:
            cid = c.get("ID", "")[:12]
            image = c.get("Image", "")
            status = c.get("Status", "")
            name = c.get("Names", "")
            ports = c.get("Ports", "")
            lines.append(f"{cid}  {image}  {status}  {name}  {ports}")

        output = "\n".join(lines)
        return ToolResult(
            success=True,
            output=output,
            data={"containers": containers, "count": len(containers)},
        )


class DockerLogsTool(BaseTool):
    """Get logs from a Docker container."""

    name = "docker_logs"
    description = (
        "Retrieve logs from a Docker container. Returns the most recent "
        "lines of output from the specified container."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "container_id": {
                "type": "string",
                "description": "Container ID or name.",
            },
            "tail": {
                "type": "integer",
                "description": "Number of lines to show from the end (default 50).",
                "default": 50,
            },
        },
        "required": ["container_id"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        container_id: str = arguments["container_id"]
        tail: int = arguments.get("tail", 50)

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "--tail", str(tail), container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="docker logs timed out")
        except FileNotFoundError:
            return ToolResult(success=False, output="Docker is not installed or not in PATH")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run docker logs: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        # Docker may write to both stdout and stderr for logs
        log_output = stdout.decode(errors="replace")
        stderr_text = stderr.decode(errors="replace")
        combined = log_output + stderr_text if stderr_text else log_output

        return ToolResult(
            success=True,
            output=combined or "(no log output)",
            data={"container_id": container_id, "lines": tail},
        )


class DockerExecTool(BaseTool):
    """Execute a command inside a running Docker container."""

    name = "docker_exec"
    description = (
        "Execute a command inside a running Docker container and return "
        "the output. The command runs non-interactively."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "container_id": {
                "type": "string",
                "description": "Container ID or name.",
            },
            "command": {
                "type": "string",
                "description": "Command to execute inside the container.",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory inside the container.",
            },
        },
        "required": ["container_id", "command"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        container_id: str = arguments["container_id"]
        command: str = arguments["command"]
        workdir = arguments.get("workdir")

        cmd = ["docker", "exec"]
        if workdir:
            cmd.extend(["-w", workdir])
        cmd.extend([container_id, "sh", "-c", command])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="docker exec timed out")
        except FileNotFoundError:
            return ToolResult(success=False, output="Docker is not installed or not in PATH")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run docker exec: {exc}")

        stdout_text = stdout.decode(errors="replace") if stdout else ""
        stderr_text = stderr.decode(errors="replace") if stderr else ""

        success = proc.returncode == 0
        parts: list[str] = []
        if stdout_text:
            parts.append(stdout_text)
        if stderr_text:
            parts.append(f"[stderr]\n{stderr_text}")

        output = "\n".join(parts) or "(no output)"

        return ToolResult(
            success=success,
            output=output,
            data={"returncode": proc.returncode},
        )


class DockerImagesTool(BaseTool):
    """List Docker images on the local system."""

    name = "docker_images"
    description = (
        "List Docker images available on the local system with their "
        "repository, tag, image ID, and size."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "description": "Filter images by repository name (substring match).",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name_filter = arguments.get("filter")

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "images", "--format", "{{json .}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="docker images timed out")
        except FileNotFoundError:
            return ToolResult(success=False, output="Docker is not installed or not in PATH")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run docker images: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        raw = stdout.decode(errors="replace").strip()
        if not raw:
            return ToolResult(
                success=True,
                output="No images found",
                data={"images": [], "count": 0},
            )

        images = []
        for line in raw.splitlines():
            try:
                img = json.loads(line)
                if name_filter and name_filter.lower() not in img.get("Repository", "").lower():
                    continue
                images.append(img)
            except json.JSONDecodeError:
                continue

        lines = []
        for img in images:
            repo = img.get("Repository", "<none>")
            tag = img.get("Tag", "<none>")
            img_id = img.get("ID", "")[:12]
            size = img.get("Size", "")
            lines.append(f"{repo}:{tag}  {img_id}  {size}")

        output = "\n".join(lines) or "No images match the filter"
        return ToolResult(
            success=True,
            output=output,
            data={"images": images, "count": len(images)},
        )
