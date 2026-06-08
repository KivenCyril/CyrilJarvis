"""Archive operation tools: create and extract zip archives."""

from __future__ import annotations

import os
import zipfile
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class ZipCreateTool(BaseTool):
    """Create a zip archive from a file or directory."""

    name = "zip_create"
    description = (
        "Create a zip archive from a file or directory. Recursively includes "
        "all files when given a directory path."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to the file or directory to archive.",
            },
            "output_path": {
                "type": "string",
                "description": "Path for the output zip file.",
            },
            "compression": {
                "type": "string",
                "enum": ["stored", "deflated"],
                "description": "Compression method (default: deflated).",
                "default": "deflated",
            },
        },
        "required": ["source_path", "output_path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        source_path: str = arguments["source_path"]
        output_path: str = arguments["output_path"]
        compression_name: str = arguments.get("compression", "deflated")

        if not os.path.exists(source_path):
            return ToolResult(success=False, output=f"Source not found: {source_path}")

        compression = (
            zipfile.ZIP_DEFLATED if compression_name == "deflated"
            else zipfile.ZIP_STORED
        )

        try:
            file_count = 0
            total_size = 0

            with zipfile.ZipFile(output_path, "w", compression=compression) as zf:
                if os.path.isfile(source_path):
                    zf.write(source_path, os.path.basename(source_path))
                    file_count = 1
                    total_size = os.path.getsize(source_path)
                elif os.path.isdir(source_path):
                    for root, _dirs, files in os.walk(source_path):
                        for fname in files:
                            filepath = os.path.join(root, fname)
                            arcname = os.path.relpath(filepath, os.path.dirname(source_path))
                            zf.write(filepath, arcname)
                            file_count += 1
                            total_size += os.path.getsize(filepath)
                else:
                    return ToolResult(
                        success=False,
                        output=f"Source is neither a file nor a directory: {source_path}",
                    )

            zip_size = os.path.getsize(output_path)
            ratio = (1 - zip_size / total_size) * 100 if total_size > 0 else 0

            return ToolResult(
                success=True,
                output=(
                    f"Created {output_path}\n"
                    f"Files: {file_count}, Original: {total_size} bytes, "
                    f"Compressed: {zip_size} bytes ({ratio:.1f}% reduction)"
                ),
                data={
                    "output_path": output_path,
                    "file_count": file_count,
                    "original_size": total_size,
                    "compressed_size": zip_size,
                },
            )
        except zipfile.BadZipFile as exc:
            return ToolResult(success=False, output=f"Zip error: {exc}")
        except OSError as exc:
            return ToolResult(success=False, output=f"File error: {exc}")


class ZipExtractTool(BaseTool):
    """Extract a zip archive."""

    name = "zip_extract"
    description = (
        "Extract a zip archive to a specified directory. Lists all "
        "extracted files and their sizes."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "zip_path": {
                "type": "string",
                "description": "Path to the zip file to extract.",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to extract into (created if absent).",
            },
            "password": {
                "type": "string",
                "description": "Password for encrypted zip files.",
            },
        },
        "required": ["zip_path", "output_dir"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        zip_path: str = arguments["zip_path"]
        output_dir: str = arguments["output_dir"]
        password: str | None = arguments.get("password")

        if not os.path.exists(zip_path):
            return ToolResult(success=False, output=f"Zip file not found: {zip_path}")

        try:
            os.makedirs(output_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zf:
                # Security check: prevent path traversal
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(output_dir, member))
                    if not member_path.startswith(os.path.realpath(output_dir)):
                        return ToolResult(
                            success=False,
                            output=f"Blocked: zip contains path traversal entry '{member}'",
                        )

                pwd = password.encode() if password else None
                zf.extractall(output_dir, pwd=pwd)

                file_list = []
                for info in zf.infolist():
                    file_list.append({
                        "name": info.filename,
                        "size": info.file_size,
                        "compressed_size": info.compress_size,
                    })

            return ToolResult(
                success=True,
                output=f"Extracted {len(file_list)} files to {output_dir}",
                data={
                    "output_dir": output_dir,
                    "files": file_list,
                    "count": len(file_list),
                },
            )
        except zipfile.BadZipFile:
            return ToolResult(success=False, output=f"Invalid or corrupted zip file: {zip_path}")
        except RuntimeError as exc:
            # zipfile raises RuntimeError for password-related errors
            return ToolResult(success=False, output=f"Zip extraction error: {exc}")
        except OSError as exc:
            return ToolResult(success=False, output=f"File error: {exc}")
