"""Advanced prompt builder with section management and token budgeting.

Inspired by Hermes Agent's ``prompt_builder.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PromptSection:
    """A named section of a prompt with priority and token budget."""

    name: str
    content: str
    priority: int = 5  # 1 = highest, 10 = lowest
    max_tokens: int = 0  # 0 = unlimited
    required: bool = False
    cache_friendly: bool = True  # keep stable for prompt caching


class PromptBuilder:
    """Advanced prompt builder with section management and token budgeting.

    Features
    --------
    - Section-based prompt composition
    - Priority-based token budget allocation
    - Prompt caching friendliness (stable prefixes)
    - Dynamic section insertion/removal
    - Few-shot example management
    - Constraint injection

    Usage::

        prompt = (
            PromptBuilder(max_tokens=4000)
            .add_system_identity("Jarvis", "a helpful AI assistant")
            .add_constraints(["Be concise", "Use markdown"])
            .add_context("The user is working on a Python project")
            .build()
        )
    """

    def __init__(self, max_tokens: int = 8000) -> None:
        self._sections: list[PromptSection] = []
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------ #
    # Section management
    # ------------------------------------------------------------------ #

    def add_section(
        self,
        name: str,
        content: str,
        priority: int = 5,
        required: bool = False,
        cache_friendly: bool = True,
        max_tokens: int = 0,
    ) -> PromptBuilder:
        """Add a section to the prompt.  Returns *self* for chaining."""
        self._sections.append(
            PromptSection(
                name=name,
                content=content,
                priority=priority,
                required=required,
                cache_friendly=cache_friendly,
                max_tokens=max_tokens,
            )
        )
        return self

    def remove_section(self, name: str) -> PromptBuilder:
        """Remove all sections with the given *name*."""
        self._sections = [s for s in self._sections if s.name != name]
        return self

    def get_section(self, name: str) -> PromptSection | None:
        """Return the first section with the given *name*, or ``None``."""
        for s in self._sections:
            if s.name == name:
                return s
        return None

    def has_section(self, name: str) -> bool:
        return any(s.name == name for s in self._sections)

    # ------------------------------------------------------------------ #
    # Convenience adders
    # ------------------------------------------------------------------ #

    def add_system_identity(
        self,
        agent_name: str,
        description: str,
        personality: str = "",
    ) -> PromptBuilder:
        """Add the agent's identity section (highest priority, cache-friendly)."""
        content = f"You are {agent_name}, {description}"
        if personality:
            content += f"\n\nPersonality: {personality}"
        return self.add_section(
            "identity", content, priority=1, required=True, cache_friendly=True
        )

    def add_capabilities(
        self, tools: list[str], skills: list[str] | None = None
    ) -> PromptBuilder:
        """Describe available tools and skills."""
        parts = ["## Your Capabilities"]
        if tools:
            parts.append("Tools available: " + ", ".join(tools))
        if skills:
            parts.append("Skills: " + ", ".join(skills))
        content = "\n".join(parts)
        return self.add_section("capabilities", content, priority=2)

    def add_constraints(self, constraints: list[str]) -> PromptBuilder:
        """Add active constraints (high priority, required)."""
        if not constraints:
            return self
        content = "## Active Constraints\n" + "\n".join(
            f"- {c}" for c in constraints
        )
        return self.add_section("constraints", content, priority=3, required=True)

    def add_context(self, context: str, label: str = "Context") -> PromptBuilder:
        """Add a generic context section."""
        return self.add_section(
            f"context_{label}", f"## {label}\n{context}", priority=4
        )

    def add_few_shot(self, examples: list[dict[str, str]]) -> PromptBuilder:
        """Add few-shot examples.  Each dict must have ``input`` and ``output`` keys."""
        if not examples:
            return self
        parts = ["## Examples"]
        for i, ex in enumerate(examples, 1):
            parts.append(
                f"\nExample {i}:\nInput: {ex['input']}\nOutput: {ex['output']}"
            )
        content = "\n".join(parts)
        return self.add_section("few_shot", content, priority=6)

    def add_output_format(self, format_spec: str) -> PromptBuilder:
        """Describe the expected output format."""
        return self.add_section(
            "output_format", f"## Output Format\n{format_spec}", priority=7
        )

    def add_memory_context(self, memories: str) -> PromptBuilder:
        """Inject relevant memory context (token-limited)."""
        if memories:
            return self.add_section(
                "memories",
                f"## Relevant Memories\n{memories}",
                priority=8,
                max_tokens=1000,
            )
        return self

    def add_knowledge_context(self, knowledge: str) -> PromptBuilder:
        """Inject knowledge-graph context (token-limited)."""
        if knowledge:
            return self.add_section(
                "knowledge",
                f"## Knowledge Graph Context\n{knowledge}",
                priority=9,
                max_tokens=1000,
            )
        return self

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #

    def build(self) -> str:
        """Build the final prompt respecting token budgets and priorities.

        Sections are ordered by *priority* (ascending, 1 = first).  Sections
        that would exceed the global token budget are dropped unless they are
        marked ``required``.  Individual sections can also be truncated to
        their own ``max_tokens`` limit.
        """
        sorted_sections = sorted(self._sections, key=lambda s: s.priority)

        result_parts: list[str] = []
        tokens_used = 0

        for section in sorted_sections:
            content = section.content
            est_tokens = len(content) // 4 + 1

            # Apply section-level token limit.
            if section.max_tokens > 0 and est_tokens > section.max_tokens:
                max_chars = section.max_tokens * 4
                content = content[:max_chars] + "\n... (truncated)"
                est_tokens = section.max_tokens

            # Check global budget.
            if tokens_used + est_tokens > self._max_tokens and not section.required:
                continue

            result_parts.append(content)
            tokens_used += est_tokens

        return "\n\n".join(result_parts)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    @property
    def section_count(self) -> int:
        return len(self._sections)

    @property
    def estimated_tokens(self) -> int:
        return sum(len(s.content) // 4 + 1 for s in self._sections)

    @property
    def section_names(self) -> list[str]:
        return [s.name for s in self._sections]
