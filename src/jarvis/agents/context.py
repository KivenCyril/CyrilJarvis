from __future__ import annotations


class ContextBuilder:
    """Builds optimized context for agent prompts.

    Assembles context from multiple sources:
    - System prompt (agent's personality/role)
    - Memory context (relevant memories)
    - Knowledge context (relevant graph nodes)
    - Skill context (relevant skills)
    - Spec context (current streaming spec state)
    - Conversation history
    - Constraints

    Manages token budget across all context sources.
    """

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens

    def build(
        self,
        system_prompt: str,
        memory_context: str = "",
        knowledge_context: str = "",
        skill_context: str = "",
        spec_context: str = "",
        constraints: list[str] | None = None,
    ) -> str:
        """Assemble a complete system prompt from all context sources.

        Priority order (higher priority gets more token budget):
        1. System prompt (always included in full)
        2. Constraints (always included)
        3. Spec context (if in a spec execution)
        4. Memory context (relevant memories)
        5. Knowledge context (relevant graph nodes)
        6. Skill context (relevant skills - lowest priority)
        """
        parts = [system_prompt]

        if constraints:
            parts.append(
                "\n## Active Constraints\n" + "\n".join(f"- {c}" for c in constraints)
            )

        if spec_context:
            parts.append(f"\n## Current Task Context\n{spec_context}")

        remaining_budget = self.max_tokens - self._estimate_tokens("\n".join(parts))

        for label, content in [
            ("Relevant Memories", memory_context),
            ("Knowledge Graph Context", knowledge_context),
            ("Available Skills", skill_context),
        ]:
            if content and remaining_budget > 200:
                truncated = self._truncate(content, remaining_budget // 3)
                parts.append(f"\n## {label}\n{truncated}")
                remaining_budget -= self._estimate_tokens(truncated)

        return "\n".join(parts)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def _truncate(text: str, max_tokens: int) -> str:
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n... (truncated)"
