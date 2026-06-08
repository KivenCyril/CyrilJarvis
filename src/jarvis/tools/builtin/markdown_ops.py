"""Markdown tools: convert to HTML, generate tables."""

from __future__ import annotations

import re
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


def _markdown_to_html(md: str) -> str:
    """Convert markdown to HTML using regex-based rules.

    Supports: headings, bold, italic, inline code, code blocks,
    links, images, unordered lists, ordered lists, horizontal rules,
    blockquotes, and paragraphs.
    """
    lines = md.split("\n")
    html_lines: list[str] = []
    in_code_block = False
    in_list = False
    list_type = ""

    for line in lines:
        # Fenced code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                html_lines.append("</code></pre>")
                in_code_block = False
            else:
                lang = line.strip()[3:].strip()
                cls = f' class="language-{lang}"' if lang else ""
                html_lines.append(f"<pre><code{cls}>")
                in_code_block = True
            continue

        if in_code_block:
            # Escape HTML inside code blocks
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_lines.append(escaped)
            continue

        stripped = line.strip()

        # Close list if we left a list context
        if in_list and not stripped.startswith(("-", "*", "+")) and not re.match(r"^\d+\.", stripped):
            if stripped == "" or not stripped.startswith(" "):
                html_lines.append(f"</{list_type}>")
                in_list = False

        # Empty lines
        if not stripped:
            html_lines.append("")
            continue

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = _inline_format(heading_match.group(2))
            html_lines.append(f"<h{level}>{text}</h{level}>")
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            html_lines.append("<hr>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            text = _inline_format(stripped[1:].strip())
            html_lines.append(f"<blockquote>{text}</blockquote>")
            continue

        # Unordered list
        ul_match = re.match(r"^[-*+]\s+(.*)", stripped)
        if ul_match:
            if not in_list or list_type != "ul":
                if in_list:
                    html_lines.append(f"</{list_type}>")
                html_lines.append("<ul>")
                in_list = True
                list_type = "ul"
            text = _inline_format(ul_match.group(1))
            html_lines.append(f"<li>{text}</li>")
            continue

        # Ordered list
        ol_match = re.match(r"^\d+\.\s+(.*)", stripped)
        if ol_match:
            if not in_list or list_type != "ol":
                if in_list:
                    html_lines.append(f"</{list_type}>")
                html_lines.append("<ol>")
                in_list = True
                list_type = "ol"
            text = _inline_format(ol_match.group(1))
            html_lines.append(f"<li>{text}</li>")
            continue

        # Regular paragraph
        html_lines.append(f"<p>{_inline_format(stripped)}</p>")

    # Close any open list
    if in_list:
        html_lines.append(f"</{list_type}>")
    if in_code_block:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)


def _inline_format(text: str) -> str:
    """Apply inline markdown formatting: bold, italic, code, links, images."""
    # Images: ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1">', text)
    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Inline code: `code`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)
    return text


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class MarkdownToHTMLTool(BaseTool):
    """Convert markdown text to HTML."""

    name = "markdown_to_html"
    description = (
        "Convert markdown text to HTML. Supports headings, bold, italic, "
        "code blocks, links, images, lists, blockquotes, and horizontal rules."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": "Markdown text to convert to HTML.",
            },
        },
        "required": ["markdown"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        md = arguments["markdown"]
        try:
            html = _markdown_to_html(md)
            return ToolResult(
                success=True,
                output=html,
                data={"input_length": len(md), "output_length": len(html)},
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Markdown conversion error: {exc}")


class MarkdownTableTool(BaseTool):
    """Generate a markdown table from structured data."""

    name = "markdown_table"
    description = (
        "Generate a markdown table from headers and rows. "
        "Produces a properly aligned markdown table string."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Column headers.",
            },
            "rows": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "description": "Table rows, each row is a list of cell values.",
            },
            "alignment": {
                "type": "string",
                "enum": ["left", "center", "right"],
                "description": "Column alignment (default: left).",
                "default": "left",
            },
        },
        "required": ["headers", "rows"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        headers: list[str] = arguments["headers"]
        rows: list[list[str]] = arguments["rows"]
        alignment: str = arguments.get("alignment", "left")

        if not headers:
            return ToolResult(success=False, output="Headers list cannot be empty.")

        try:
            # Calculate column widths
            col_count = len(headers)
            widths = [len(h) for h in headers]
            for row in rows:
                for i, cell in enumerate(row):
                    if i < col_count:
                        widths[i] = max(widths[i], len(str(cell)))

            # Build header row
            header_cells = [h.ljust(widths[i]) for i, h in enumerate(headers)]
            header_line = "| " + " | ".join(header_cells) + " |"

            # Build separator
            if alignment == "center":
                sep_cells = [":" + "-" * (w) + ":" for w in widths]
            elif alignment == "right":
                sep_cells = ["-" * (w + 1) + ":" for w in widths]
            else:
                sep_cells = ["-" * (w + 2) for w in widths]
            sep_line = "|" + "|".join(sep_cells) + "|"

            # Build data rows
            data_lines: list[str] = []
            for row in rows:
                cells: list[str] = []
                for i in range(col_count):
                    val = str(row[i]) if i < len(row) else ""
                    cells.append(val.ljust(widths[i]))
                data_lines.append("| " + " | ".join(cells) + " |")

            table = "\n".join([header_line, sep_line] + data_lines)

            return ToolResult(
                success=True,
                output=table,
                data={
                    "columns": col_count,
                    "rows": len(rows),
                },
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Table generation error: {exc}")
