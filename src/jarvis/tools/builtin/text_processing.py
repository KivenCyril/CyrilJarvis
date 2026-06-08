"""Text processing tools: regex, summarization, and diffing."""

from __future__ import annotations

import difflib
import re
from collections import Counter
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class RegexTool(BaseTool):
    """Search text with a regular expression, optionally replacing matches."""

    name = "regex_search"
    description = (
        "Search text using a Python regular expression. Returns all matches "
        "with their positions and captured groups. Optionally replaces matches."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to search.",
            },
            "pattern": {
                "type": "string",
                "description": "A Python-syntax regular expression.",
            },
            "replace_with": {
                "type": "string",
                "description": (
                    "If provided, replace all matches with this string. "
                    "Supports back-references like \\1."
                ),
            },
        },
        "required": ["text", "pattern"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        text: str = arguments["text"]
        pattern_str: str = arguments["pattern"]
        replace_with: str | None = arguments.get("replace_with")

        try:
            regex = re.compile(pattern_str)
        except re.error as exc:
            return ToolResult(success=False, output=f"Invalid regex: {exc}")

        if replace_with is not None:
            try:
                result_text = regex.sub(replace_with, text)
            except re.error as exc:
                return ToolResult(success=False, output=f"Replacement error: {exc}")
            return ToolResult(
                success=True,
                output=result_text,
                data={"replaced": True, "count": len(regex.findall(text))},
            )

        matches = []
        for m in regex.finditer(text):
            match_info: dict[str, Any] = {
                "match": m.group(),
                "start": m.start(),
                "end": m.end(),
            }
            if m.groups():
                match_info["groups"] = list(m.groups())
            if m.groupdict():
                match_info["named_groups"] = m.groupdict()
            matches.append(match_info)

        if not matches:
            return ToolResult(
                success=True,
                output="No matches found.",
                data={"matches": [], "count": 0},
            )

        lines = [f"Found {len(matches)} match(es):"]
        for i, match in enumerate(matches):
            lines.append(f"  [{i}] \"{match['match']}\" at {match['start']}..{match['end']}")
            if "groups" in match:
                lines.append(f"       groups: {match['groups']}")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"matches": matches, "count": len(matches)},
        )


class TextSummaryTool(BaseTool):
    """Produce a simple extractive summary of a text."""

    name = "text_summary"
    description = (
        "Summarize text using extractive summarization. Scores sentences "
        "by word frequency and returns the top N sentences in order."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to summarize.",
            },
            "max_sentences": {
                "type": "integer",
                "description": "Maximum number of sentences in the summary (default 3).",
                "default": 3,
            },
        },
        "required": ["text"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        text: str = arguments["text"]
        max_sentences: int = arguments.get("max_sentences", 3)

        # Split text into sentences (simple heuristic)
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return ToolResult(success=True, output="(empty text)")

        if len(sentences) <= max_sentences:
            return ToolResult(
                success=True,
                output=" ".join(sentences),
                data={"sentence_count": len(sentences)},
            )

        # Score sentences by word frequency
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        freq = Counter(words)

        scored: list[tuple[int, float, str]] = []
        for idx, sentence in enumerate(sentences):
            sent_words = re.findall(r'\b[a-zA-Z]{2,}\b', sentence.lower())
            if not sent_words:
                score = 0.0
            else:
                score = sum(freq.get(w, 0) for w in sent_words) / len(sent_words)
            scored.append((idx, score, sentence))

        # Pick top sentences by score, then present in original order
        scored.sort(key=lambda x: x[1], reverse=True)
        top = sorted(scored[:max_sentences], key=lambda x: x[0])

        summary = " ".join(s[2] for s in top)
        return ToolResult(
            success=True,
            output=summary,
            data={"sentence_count": len(top), "total_sentences": len(sentences)},
        )


class DiffTool(BaseTool):
    """Compare two texts and produce a unified diff."""

    name = "text_diff"
    description = (
        "Compare two text strings and return a unified diff showing the differences."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text_a": {
                "type": "string",
                "description": "The first (original) text.",
            },
            "text_b": {
                "type": "string",
                "description": "The second (modified) text.",
            },
            "label_a": {
                "type": "string",
                "description": "Label for the first text (default 'a').",
                "default": "a",
            },
            "label_b": {
                "type": "string",
                "description": "Label for the second text (default 'b').",
                "default": "b",
            },
        },
        "required": ["text_a", "text_b"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        text_a: str = arguments["text_a"]
        text_b: str = arguments["text_b"]
        label_a: str = arguments.get("label_a", "a")
        label_b: str = arguments.get("label_b", "b")

        lines_a = text_a.splitlines(keepends=True)
        lines_b = text_b.splitlines(keepends=True)

        diff_lines = list(difflib.unified_diff(
            lines_a, lines_b,
            fromfile=label_a, tofile=label_b,
        ))

        if not diff_lines:
            return ToolResult(
                success=True,
                output="(no differences)",
                data={"has_diff": False},
            )

        output = "".join(diff_lines)
        return ToolResult(
            success=True,
            output=output,
            data={"has_diff": True, "diff_lines": len(diff_lines)},
        )
