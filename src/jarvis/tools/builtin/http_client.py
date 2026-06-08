"""HTTP client tools: request and download."""

from __future__ import annotations

import os
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


class HttpRequestTool(BaseTool):
    """Make an HTTP request and return the response."""

    name = "http_request"
    description = (
        "Make an HTTP request (GET, POST, PUT, DELETE) and return the "
        "status code, response headers, and body."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to send the request to.",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                "description": "HTTP method (default GET).",
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs.",
            },
            "body": {
                "type": "string",
                "description": "Optional request body.",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default 30).",
                "default": 30,
            },
        },
        "required": ["url"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if httpx is None:
            return ToolResult(success=False, output="httpx is not installed")

        url: str = arguments["url"]
        method: str = arguments.get("method", "GET").upper()
        headers: dict[str, str] = arguments.get("headers") or {}
        body: str | None = arguments.get("body")
        timeout: int = arguments.get("timeout", 30)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body.encode() if body else None,
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, output=f"Request timed out after {timeout}s")
        except httpx.RequestError as exc:
            return ToolResult(success=False, output=f"Request failed: {exc}")

        # Truncate very large bodies
        body_text = response.text
        truncated = False
        if len(body_text) > 50_000:
            body_text = body_text[:50_000]
            truncated = True

        resp_headers = dict(response.headers)
        output_parts = [
            f"HTTP {response.status_code}",
            f"Content-Type: {response.headers.get('content-type', 'unknown')}",
            f"Body length: {len(response.text)} chars",
            "",
            body_text,
        ]
        if truncated:
            output_parts.append("\n... (truncated)")

        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            data={
                "status_code": response.status_code,
                "headers": resp_headers,
                "truncated": truncated,
            },
        )


class HttpDownloadTool(BaseTool):
    """Download a file from a URL."""

    name = "http_download"
    description = (
        "Download a file from a URL using streaming and save it to disk. "
        "Returns the file path and size."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to download from.",
            },
            "save_path": {
                "type": "string",
                "description": "Local path to save the downloaded file.",
            },
            "timeout": {
                "type": "integer",
                "description": "Download timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": ["url", "save_path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if httpx is None:
            return ToolResult(success=False, output="httpx is not installed")

        url: str = arguments["url"]
        save_path: str = arguments["save_path"]
        timeout: int = arguments.get("timeout", 120)

        # Ensure parent directory exists
        parent = os.path.dirname(os.path.abspath(save_path))
        os.makedirs(parent, exist_ok=True)

        total_bytes = 0
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code >= 400:
                        return ToolResult(
                            success=False,
                            output=f"Download failed with HTTP {response.status_code}",
                        )
                    with open(save_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            total_bytes += len(chunk)
        except httpx.TimeoutException:
            return ToolResult(success=False, output=f"Download timed out after {timeout}s")
        except httpx.RequestError as exc:
            return ToolResult(success=False, output=f"Download failed: {exc}")
        except OSError as exc:
            return ToolResult(success=False, output=f"Cannot write to {save_path}: {exc}")

        return ToolResult(
            success=True,
            output=f"Downloaded {total_bytes} bytes to {save_path}",
            data={"path": os.path.abspath(save_path), "size": total_bytes},
        )
