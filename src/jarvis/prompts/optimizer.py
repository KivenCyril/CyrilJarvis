"""Prompt optimizer -- analysis, compression, and cache-friendliness."""

from __future__ import annotations

import re
from typing import Any


class PromptOptimizer:
    """Analyzes and optimizes prompts for better LLM performance.

    Provides
    --------
    - Token count estimation
    - Prompt compression
    - Redundancy detection / removal
    - Cache-friendliness scoring
    - Prompt analysis & suggestions
    """

    # ------------------------------------------------------------------ #
    # Token estimation
    # ------------------------------------------------------------------ #

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count (4 chars ~ 1 token for English text)."""
        return len(text) // 4 + 1

    # ------------------------------------------------------------------ #
    # Compression
    # ------------------------------------------------------------------ #

    @staticmethod
    def compress(text: str, target_tokens: int) -> str:
        """Compress *text* to fit within *target_tokens*.

        Strategy (applied in order until target is met):
        1. Collapse multiple blank lines.
        2. Strip trailing whitespace.
        3. Remove markdown horizontal rules.
        4. Truncate from the end.
        """
        # Step 1: collapse multiple blank lines to a single one.
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Step 2: strip trailing whitespace on each line.
        text = "\n".join(line.rstrip() for line in text.split("\n"))

        # Step 3: remove horizontal rules.
        text = re.sub(r"\n-{3,}\n", "\n", text)

        # Step 4: truncate if still over budget.
        current_tokens = len(text) // 4 + 1
        if current_tokens > target_tokens:
            max_chars = target_tokens * 4
            text = text[:max_chars] + "\n... (truncated)"

        return text

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #

    @staticmethod
    def analyze(prompt: str) -> dict[str, Any]:
        """Analyze a prompt and return optimisation suggestions.

        Returns a dict with keys:
        - ``estimated_tokens``
        - ``line_count``
        - ``section_count``
        - ``suggestions``
        - ``cache_friendly_prefix_ratio``
        """
        tokens = len(prompt) // 4 + 1
        lines = prompt.split("\n")
        sections = [l for l in lines if l.startswith("#")]

        suggestions: list[str] = []

        if tokens > 4000:
            suggestions.append(
                "Prompt exceeds 4K tokens. Consider compression."
            )
        if prompt.count("  ") > 10:
            suggestions.append(
                "Excessive whitespace detected. Compress spaces."
            )
        # Check for very long lines.
        long_lines = [l for l in lines if len(l) > 500]
        if long_lines:
            suggestions.append(
                f"{len(long_lines)} lines exceed 500 chars. Consider wrapping."
            )
        # Check for duplicated sentences.
        sentences = [
            s.strip()
            for s in re.split(r"[.!?]\s", prompt)
            if len(s.strip()) > 20
        ]
        seen: set[str] = set()
        dupes = 0
        for s in sentences:
            norm = s.lower()
            if norm in seen:
                dupes += 1
            seen.add(norm)
        if dupes:
            suggestions.append(
                f"{dupes} duplicate sentence(s) detected. Remove redundancy."
            )

        # Cache-friendliness: measure what fraction of the prompt is a
        # stable prefix (before the first dynamic-looking section).
        # Heuristic: sections marked ``## Context`` or ``## Relevant Memories``
        # are dynamic.
        dynamic_markers = [
            "## Context",
            "## Relevant Memories",
            "## Knowledge Graph Context",
        ]
        first_dynamic_pos = len(prompt)
        for marker in dynamic_markers:
            pos = prompt.find(marker)
            if pos != -1 and pos < first_dynamic_pos:
                first_dynamic_pos = pos

        cache_ratio = (
            round(first_dynamic_pos / len(prompt), 2)
            if prompt
            else 1.0
        )

        return {
            "estimated_tokens": tokens,
            "line_count": len(lines),
            "section_count": len(sections),
            "suggestions": suggestions,
            "cache_friendly_prefix_ratio": cache_ratio,
        }

    # ------------------------------------------------------------------ #
    # Redundancy removal
    # ------------------------------------------------------------------ #

    @staticmethod
    def remove_redundancy(prompt: str) -> str:
        """Remove redundant sentences and repetitive instructions.

        Keeps the *first* occurrence of each normalised sentence.  Also
        collapses consecutive duplicate blank lines.
        """
        lines = prompt.split("\n")
        seen_lines: set[str] = set()
        result: list[str] = []
        prev_blank = False

        for line in lines:
            stripped = line.strip()

            # Collapse multiple blank lines.
            if not stripped:
                if prev_blank:
                    continue
                prev_blank = True
                result.append(line)
                continue
            prev_blank = False

            # Keep headers and short lines as-is.
            if stripped.startswith("#") or len(stripped) < 20:
                result.append(line)
                continue

            norm = stripped.lower()
            if norm in seen_lines:
                continue  # skip duplicate
            seen_lines.add(norm)
            result.append(line)

        return "\n".join(result)
