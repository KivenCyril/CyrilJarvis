"""Color operation tools: format conversion and palette generation."""

from __future__ import annotations

import colorsys
import json
import re
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse a hex color string (with or without #) into an (R, G, B) tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    if len(hex_str) != 6:
        raise ValueError(f"Invalid hex color: #{hex_str}")
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB values to a hex color string."""
    return f"#{r:02x}{g:02x}{b:02x}"


def _rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB (0-255 each) to HSL (h: 0-360, s: 0-100, l: 0-100)."""
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return round(h * 360, 1), round(s * 100, 1), round(l * 100, 1)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    """Convert HSL (h: 0-360, s: 0-100, l: 0-100) to RGB (0-255)."""
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
    return round(r * 255), round(g * 255), round(b * 255)


def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB to HSV (h: 0-360, s: 0-100, v: 0-100)."""
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return round(h * 360, 1), round(s * 100, 1), round(v * 100, 1)


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    """Convert HSV to RGB."""
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, v / 100.0)
    return round(r * 255), round(g * 255), round(b * 255)


def _parse_color(value: str, fmt: str) -> tuple[int, int, int]:
    """Parse a color string in the given format into RGB."""
    if fmt == "hex":
        return _hex_to_rgb(value)
    elif fmt == "rgb":
        match = re.match(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
        if not match:
            raise ValueError(f"Invalid RGB format: {value}. Use 'R,G,B'")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    elif fmt == "hsl":
        match = re.match(r"([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", value)
        if not match:
            raise ValueError(f"Invalid HSL format: {value}. Use 'H,S,L'")
        h, s, l = float(match.group(1)), float(match.group(2)), float(match.group(3))
        return _hsl_to_rgb(h, s, l)
    elif fmt == "hsv":
        match = re.match(r"([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", value)
        if not match:
            raise ValueError(f"Invalid HSV format: {value}. Use 'H,S,V'")
        h, s, v = float(match.group(1)), float(match.group(2)), float(match.group(3))
        return _hsv_to_rgb(h, s, v)
    else:
        raise ValueError(f"Unknown color format: {fmt}")


def _format_color(r: int, g: int, b: int) -> dict[str, Any]:
    """Return all representations of an RGB color."""
    h_hsl, s_hsl, l_hsl = _rgb_to_hsl(r, g, b)
    h_hsv, s_hsv, v_hsv = _rgb_to_hsv(r, g, b)
    return {
        "hex": _rgb_to_hex(r, g, b),
        "rgb": {"r": r, "g": g, "b": b},
        "hsl": {"h": h_hsl, "s": s_hsl, "l": l_hsl},
        "hsv": {"h": h_hsv, "s": s_hsv, "v": v_hsv},
        "css_rgb": f"rgb({r}, {g}, {b})",
        "css_hsl": f"hsl({h_hsl}, {s_hsl}%, {l_hsl}%)",
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class ColorConvertTool(BaseTool):
    """Convert colours between hex, RGB, HSL, and HSV."""

    name = "color_convert"
    description = (
        "Convert a colour value between different formats: hex, RGB, HSL, HSV. "
        "Input a colour in any supported format and receive all other "
        "representations. Hex values may include or omit the leading '#'."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "description": (
                    "The colour value to convert. Examples: '#ff5733', "
                    "'255,87,51' (RGB), '11,100,76' (HSL), '11,80,100' (HSV)."
                ),
            },
            "from_format": {
                "type": "string",
                "enum": ["hex", "rgb", "hsl", "hsv"],
                "description": "The format of the input value.",
            },
        },
        "required": ["value", "from_format"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        value: str = arguments["value"]
        from_format: str = arguments["from_format"]

        try:
            r, g, b = _parse_color(value, from_format)
        except ValueError as exc:
            return ToolResult(success=False, output=str(exc))

        # Clamp values
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))

        result = _format_color(r, g, b)
        output = json.dumps(result, indent=2)

        return ToolResult(
            success=True,
            output=output,
            data={"color": result},
        )


class ColorPaletteTool(BaseTool):
    """Generate complementary colour palettes from a base colour."""

    name = "color_palette"
    description = (
        "Generate a palette of N harmonious colours from a base colour. "
        "Supports several palette types: complementary, analogous, triadic, "
        "tetradic, split-complementary, and monochromatic. Each colour in "
        "the palette is returned in hex, RGB, and HSL formats."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "base_color": {
                "type": "string",
                "description": "The base colour as a hex string (e.g. '#3498db').",
            },
            "count": {
                "type": "integer",
                "description": "Number of colours to generate (default: 5, max: 20).",
            },
            "palette_type": {
                "type": "string",
                "enum": [
                    "complementary",
                    "analogous",
                    "triadic",
                    "tetradic",
                    "split_complementary",
                    "monochromatic",
                ],
                "description": "Type of palette to generate (default: 'complementary').",
            },
        },
        "required": ["base_color"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        base_hex: str = arguments["base_color"]
        count: int = min(arguments.get("count", 5), 20)
        palette_type: str = arguments.get("palette_type", "complementary")

        try:
            r, g, b = _hex_to_rgb(base_hex)
        except ValueError as exc:
            return ToolResult(success=False, output=str(exc))

        h, s, l = _rgb_to_hsl(r, g, b)

        hue_offsets: list[float] = []

        if palette_type == "complementary":
            # Evenly space hues, starting with the base
            for i in range(count):
                offset = (360.0 / count) * i
                hue_offsets.append(offset)

        elif palette_type == "analogous":
            # Small hue shifts around the base colour
            spread = 30.0
            for i in range(count):
                offset = -spread + (2 * spread / max(count - 1, 1)) * i
                hue_offsets.append(offset)

        elif palette_type == "triadic":
            base_offsets = [0, 120, 240]
            idx = 0
            while len(hue_offsets) < count:
                hue_offsets.append(base_offsets[idx % 3])
                idx += 1

        elif palette_type == "tetradic":
            base_offsets = [0, 90, 180, 270]
            idx = 0
            while len(hue_offsets) < count:
                hue_offsets.append(base_offsets[idx % 4])
                idx += 1

        elif palette_type == "split_complementary":
            base_offsets = [0, 150, 210]
            idx = 0
            while len(hue_offsets) < count:
                hue_offsets.append(base_offsets[idx % 3])
                idx += 1

        elif palette_type == "monochromatic":
            # Same hue, vary lightness
            for i in range(count):
                hue_offsets.append(0)

        else:
            return ToolResult(
                success=False,
                output=f"Unknown palette type: {palette_type}",
            )

        palette = []
        for i, offset in enumerate(hue_offsets):
            new_h = (h + offset) % 360

            if palette_type == "monochromatic":
                # Vary lightness from 20% to 80%
                new_l = 20 + (60 / max(count - 1, 1)) * i
                new_s = s
            else:
                new_l = l
                new_s = s

            pr, pg, pb = _hsl_to_rgb(new_h, new_s, new_l)
            pr = max(0, min(255, pr))
            pg = max(0, min(255, pg))
            pb = max(0, min(255, pb))
            palette.append(_format_color(pr, pg, pb))

        output_lines = [f"Palette ({palette_type}, {count} colours from {base_hex}):"]
        for i, color in enumerate(palette):
            output_lines.append(
                f"  {i + 1}. {color['hex']}  RGB({color['rgb']['r']},{color['rgb']['g']},{color['rgb']['b']})"
            )

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            data={"palette_type": palette_type, "base": base_hex, "colors": palette},
        )
