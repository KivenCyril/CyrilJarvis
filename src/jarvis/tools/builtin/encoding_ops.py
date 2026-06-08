"""Encoding and hashing tools: base64, hash, URL encode/decode."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Any
from urllib.parse import quote, unquote

from jarvis.tools.base import BaseTool, ToolResult


class Base64Tool(BaseTool):
    """Encode or decode base64 data."""

    name = "base64_codec"
    description = (
        "Encode a string to base64 or decode a base64 string back to text."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "The string to encode or decode.",
            },
            "action": {
                "type": "string",
                "enum": ["encode", "decode"],
                "description": "Whether to 'encode' or 'decode'.",
            },
        },
        "required": ["input", "action"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        data: str = arguments["input"]
        action: str = arguments["action"]

        try:
            if action == "encode":
                result = base64.b64encode(data.encode("utf-8")).decode("ascii")
                return ToolResult(
                    success=True,
                    output=result,
                    data={"action": "encode", "result": result},
                )
            elif action == "decode":
                result = base64.b64decode(data).decode("utf-8")
                return ToolResult(
                    success=True,
                    output=result,
                    data={"action": "decode", "result": result},
                )
            else:
                return ToolResult(success=False, output=f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult(success=False, output=f"Base64 error: {exc}")


class HashTool(BaseTool):
    """Compute hash of text or a file."""

    name = "hash"
    description = (
        "Compute a cryptographic hash of text or a file. "
        "Supports md5, sha1, sha256, and sha512 algorithms."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Text to hash, or file path if is_file=true.",
            },
            "algorithm": {
                "type": "string",
                "enum": ["md5", "sha1", "sha256", "sha512"],
                "description": "Hash algorithm (default: sha256).",
                "default": "sha256",
            },
            "is_file": {
                "type": "boolean",
                "description": "If true, treat input as a file path and hash the file contents. Default false.",
                "default": False,
            },
        },
        "required": ["input"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        data: str = arguments["input"]
        algorithm: str = arguments.get("algorithm", "sha256")
        is_file: bool = arguments.get("is_file", False)

        if algorithm not in ("md5", "sha1", "sha256", "sha512"):
            return ToolResult(success=False, output=f"Unsupported algorithm: {algorithm}")

        try:
            h = hashlib.new(algorithm)

            if is_file:
                if not os.path.exists(data):
                    return ToolResult(success=False, output=f"File not found: {data}")
                with open(data, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        h.update(chunk)
                source = f"file:{os.path.basename(data)}"
            else:
                h.update(data.encode("utf-8"))
                source = f"text ({len(data)} chars)"

            digest = h.hexdigest()
            return ToolResult(
                success=True,
                output=f"{algorithm}({source}) = {digest}",
                data={"algorithm": algorithm, "hash": digest, "is_file": is_file},
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Hash error: {exc}")


class URLEncodeTool(BaseTool):
    """URL encode or decode a string."""

    name = "url_codec"
    description = (
        "URL encode or decode a string. Useful for preparing query parameters "
        "or decoding URL-encoded data."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "The string to encode or decode.",
            },
            "action": {
                "type": "string",
                "enum": ["encode", "decode"],
                "description": "Whether to 'encode' or 'decode'.",
            },
        },
        "required": ["input", "action"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        data: str = arguments["input"]
        action: str = arguments["action"]

        try:
            if action == "encode":
                result = quote(data, safe="")
                return ToolResult(
                    success=True,
                    output=result,
                    data={"action": "encode", "result": result},
                )
            elif action == "decode":
                result = unquote(data)
                return ToolResult(
                    success=True,
                    output=result,
                    data={"action": "decode", "result": result},
                )
            else:
                return ToolResult(success=False, output=f"Unknown action: {action}")
        except Exception as exc:
            return ToolResult(success=False, output=f"URL codec error: {exc}")
