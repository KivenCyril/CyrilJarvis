"""Image operation tools: info, resize, and screenshot."""

from __future__ import annotations

import asyncio
import os
import struct
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


def _read_png_dimensions(path: str) -> tuple[int, int]:
    """Read width and height from a PNG file header."""
    with open(path, "rb") as f:
        sig = f.read(8)
        if sig[:4] != b"\x89PNG":
            raise ValueError("Not a valid PNG file")
        # IHDR chunk follows the signature
        _length = f.read(4)
        chunk_type = f.read(4)
        if chunk_type != b"IHDR":
            raise ValueError("Missing IHDR chunk")
        width, height = struct.unpack(">II", f.read(8))
    return width, height


def _read_jpeg_dimensions(path: str) -> tuple[int, int]:
    """Read width and height from a JPEG file header."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"\xff\xd8":
        raise ValueError("Not a valid JPEG file")

    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xC0, 0xC1, 0xC2):  # SOF0, SOF1, SOF2
            # Skip length (2 bytes) and precision (1 byte)
            height = struct.unpack(">H", data[i + 3 : i + 5])[0]
            width = struct.unpack(">H", data[i + 5 : i + 7])[0]
            return width, height
        elif marker == 0xD9:  # EOI
            break
        elif marker == 0xDA:  # SOS - start of scan, stop parsing
            break
        else:
            if i + 2 <= len(data):
                seg_len = struct.unpack(">H", data[i : i + 2])[0]
                i += seg_len
            else:
                break

    raise ValueError("Could not find JPEG dimensions")


def _read_gif_dimensions(path: str) -> tuple[int, int]:
    """Read width and height from a GIF file header."""
    with open(path, "rb") as f:
        sig = f.read(6)
        if sig[:3] != b"GIF":
            raise ValueError("Not a valid GIF file")
        width, height = struct.unpack("<HH", f.read(4))
    return width, height


def _read_bmp_dimensions(path: str) -> tuple[int, int]:
    """Read width and height from a BMP file header."""
    with open(path, "rb") as f:
        sig = f.read(2)
        if sig != b"BM":
            raise ValueError("Not a valid BMP file")
        f.seek(18)
        width, height = struct.unpack("<ii", f.read(8))
    return width, abs(height)


class ImageInfoTool(BaseTool):
    """Get metadata about an image file without external dependencies."""

    name = "image_info"
    description = (
        "Get image metadata including width, height, format, and file size. "
        "Supports PNG, JPEG, GIF, and BMP by parsing file headers directly."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the image file.",
            },
        },
        "required": ["path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path: str = arguments["path"]

        if not os.path.exists(path):
            return ToolResult(success=False, output=f"File not found: {path}")

        file_size = os.path.getsize(path)
        ext = os.path.splitext(path)[1].lower()

        readers = {
            ".png": ("PNG", _read_png_dimensions),
            ".jpg": ("JPEG", _read_jpeg_dimensions),
            ".jpeg": ("JPEG", _read_jpeg_dimensions),
            ".gif": ("GIF", _read_gif_dimensions),
            ".bmp": ("BMP", _read_bmp_dimensions),
        }

        if ext not in readers:
            # Try to detect from magic bytes
            with open(path, "rb") as f:
                magic = f.read(8)
            if magic[:4] == b"\x89PNG":
                fmt, reader = "PNG", _read_png_dimensions
            elif magic[:2] == b"\xff\xd8":
                fmt, reader = "JPEG", _read_jpeg_dimensions
            elif magic[:3] == b"GIF":
                fmt, reader = "GIF", _read_gif_dimensions
            elif magic[:2] == b"BM":
                fmt, reader = "BMP", _read_bmp_dimensions
            else:
                return ToolResult(
                    success=True,
                    output=f"File: {os.path.basename(path)}\nSize: {file_size} bytes\nFormat: Unknown",
                    data={"path": path, "file_size": file_size, "format": "unknown"},
                )
        else:
            fmt, reader = readers[ext]

        try:
            width, height = reader(path)
        except (ValueError, struct.error, OSError) as exc:
            return ToolResult(
                success=False,
                output=f"Failed to read image dimensions: {exc}",
            )

        # Format size nicely
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"

        output = (
            f"File: {os.path.basename(path)}\n"
            f"Format: {fmt}\n"
            f"Dimensions: {width} x {height}\n"
            f"Size: {size_str}"
        )
        return ToolResult(
            success=True,
            output=output,
            data={
                "path": path,
                "format": fmt,
                "width": width,
                "height": height,
                "file_size": file_size,
            },
        )


class ImageResizeTool(BaseTool):
    """Resize an image using macOS built-in sips command."""

    name = "image_resize"
    description = (
        "Resize an image to specified dimensions using macOS sips command. "
        "Supports JPEG, PNG, TIFF, GIF, and BMP formats."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the source image file.",
            },
            "width": {
                "type": "integer",
                "description": "Target width in pixels.",
            },
            "height": {
                "type": "integer",
                "description": "Target height in pixels.",
            },
            "output_path": {
                "type": "string",
                "description": "Path for the resized image. If omitted, overwrites the original.",
            },
        },
        "required": ["path", "width", "height"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path: str = arguments["path"]
        width: int = arguments["width"]
        height: int = arguments["height"]
        output_path: str = arguments.get("output_path", "")

        if not os.path.exists(path):
            return ToolResult(success=False, output=f"File not found: {path}")

        if width <= 0 or height <= 0:
            return ToolResult(success=False, output="Width and height must be positive integers")

        # If output_path specified, copy first then resize in-place
        if output_path:
            try:
                import shutil
                shutil.copy2(path, output_path)
                target = output_path
            except OSError as exc:
                return ToolResult(success=False, output=f"Failed to copy file: {exc}")
        else:
            target = path

        try:
            proc = await asyncio.create_subprocess_exec(
                "sips", "--resampleHeightWidth", str(height), str(width), target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="sips command timed out")
        except FileNotFoundError:
            return ToolResult(success=False, output="sips is not available (macOS only)")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run sips: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip(),
            )

        return ToolResult(
            success=True,
            output=f"Resized to {width}x{height}: {target}",
            data={"path": target, "width": width, "height": height},
        )


class ScreenshotTool(BaseTool):
    """Take a screenshot using macOS screencapture."""

    name = "screenshot"
    description = (
        "Take a screenshot and save it to a file. Uses macOS screencapture "
        "in non-interactive mode (captures the full screen)."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Path to save the screenshot (default: /tmp/screenshot.png).",
                "default": "/tmp/screenshot.png",
            },
            "screen_id": {
                "type": "integer",
                "description": "Screen index to capture (for multi-display setups).",
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        output_path: str = arguments.get("output_path", "/tmp/screenshot.png")
        screen_id = arguments.get("screen_id")

        cmd = ["screencapture", "-x"]  # -x suppresses sound
        if screen_id is not None:
            cmd.extend(["-D", str(screen_id)])
        cmd.append(output_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="screencapture timed out")
        except FileNotFoundError:
            return ToolResult(success=False, output="screencapture is not available (macOS only)")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to take screenshot: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip() or "screencapture failed",
            )

        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            return ToolResult(
                success=True,
                output=f"Screenshot saved to {output_path} ({file_size} bytes)",
                data={"path": output_path, "file_size": file_size},
            )

        return ToolResult(success=False, output="Screenshot file was not created")
