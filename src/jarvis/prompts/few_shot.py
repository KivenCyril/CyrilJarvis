"""Few-shot example manager for prompt engineering."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class FewShotExample:
    """A single few-shot example with metadata."""

    input: str
    output: str
    category: str = "general"
    quality_score: float = 1.0


class FewShotManager:
    """Manages few-shot examples for prompt engineering.

    Features
    --------
    - Example storage and categorization
    - Dynamic example selection based on textual similarity
    - Example quality tracking
    - Token-budget-aware example selection
    """

    def __init__(self) -> None:
        self._examples: dict[str, list[FewShotExample]] = {}  # category -> examples

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def add(
        self,
        input: str,
        output: str,
        category: str = "general",
        quality: float = 1.0,
    ) -> None:
        """Add a new few-shot example."""
        example = FewShotExample(
            input=input, output=output, category=category, quality_score=quality
        )
        self._examples.setdefault(category, []).append(example)

    def remove_low_quality(self, threshold: float = 0.3) -> int:
        """Remove examples below the quality *threshold*.  Returns count removed."""
        removed = 0
        for cat in list(self._examples):
            before = len(self._examples[cat])
            self._examples[cat] = [
                e for e in self._examples[cat] if e.quality_score >= threshold
            ]
            removed += before - len(self._examples[cat])
            if not self._examples[cat]:
                del self._examples[cat]
        return removed

    def clear(self, category: str | None = None) -> None:
        """Clear examples.  If *category* is given, only clear that category."""
        if category is None:
            self._examples.clear()
        else:
            self._examples.pop(category, None)

    # ------------------------------------------------------------------ #
    # Selection
    # ------------------------------------------------------------------ #

    def get_examples(
        self,
        category: str = "general",
        max_examples: int = 3,
        max_tokens: int = 2000,
        query: str = "",
    ) -> list[FewShotExample]:
        """Select the best examples within the token budget.

        If *query* is provided, examples are ranked by textual similarity
        to the query (using :func:`difflib.SequenceMatcher`).  Otherwise,
        examples are ranked by *quality_score* (highest first).
        """
        pool = list(self._examples.get(category, []))
        if not pool:
            return []

        if query:
            # Rank by textual similarity to the query.
            pool.sort(
                key=lambda e: SequenceMatcher(None, query.lower(), e.input.lower()).ratio(),
                reverse=True,
            )
        else:
            pool.sort(key=lambda e: e.quality_score, reverse=True)

        selected: list[FewShotExample] = []
        tokens_used = 0
        for ex in pool:
            if len(selected) >= max_examples:
                break
            ex_tokens = (len(ex.input) + len(ex.output)) // 4 + 1
            if tokens_used + ex_tokens > max_tokens:
                continue
            selected.append(ex)
            tokens_used += ex_tokens

        return selected

    def get_all(self, category: str | None = None) -> list[FewShotExample]:
        """Return all examples, optionally filtered by *category*."""
        if category is not None:
            return list(self._examples.get(category, []))
        return [ex for exs in self._examples.values() for ex in exs]

    # ------------------------------------------------------------------ #
    # Formatting helpers
    # ------------------------------------------------------------------ #

    def format_examples(
        self,
        category: str = "general",
        max_examples: int = 3,
        max_tokens: int = 2000,
        query: str = "",
    ) -> list[dict[str, str]]:
        """Return examples as dicts suitable for :meth:`PromptBuilder.add_few_shot`."""
        return [
            {"input": ex.input, "output": ex.output}
            for ex in self.get_examples(category, max_examples, max_tokens, query)
        ]

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def list_categories(self) -> list[str]:
        """Return sorted list of category names that have examples."""
        return sorted(self._examples)

    def count(self, category: str | None = None) -> int:
        """Count examples, optionally filtered by *category*."""
        if category is not None:
            return len(self._examples.get(category, []))
        return sum(len(v) for v in self._examples.values())
