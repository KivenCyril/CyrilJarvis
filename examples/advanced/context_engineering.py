"""Context Engineering Demo.

Shows advanced prompt building techniques using all available
context sources in JARVIS: memory, knowledge graph, conversation
history, spec state, agent cards, and tool results.

Usage:
    python examples/advanced/context_engineering.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Context sources
# ---------------------------------------------------------------------------

@dataclass
class ContextSource:
    """A source of context for prompt building."""
    name: str
    content: str
    priority: int = 0  # Higher = more important
    token_estimate: int = 0
    source_type: str = "static"  # static, dynamic, user, system
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.token_estimate:
            # Rough estimate: 1 token per 4 characters
            self.token_estimate = len(self.content) // 4


@dataclass
class ContextWindow:
    """Manages the context window for prompt building."""
    max_tokens: int = 8192
    sources: list[ContextSource] = field(default_factory=list)
    reserved_for_output: int = 2048

    @property
    def available_tokens(self) -> int:
        return self.max_tokens - self.reserved_for_output

    @property
    def used_tokens(self) -> int:
        return sum(s.token_estimate for s in self.sources)

    @property
    def remaining_tokens(self) -> int:
        return self.available_tokens - self.used_tokens

    def add_source(self, source: ContextSource) -> bool:
        """Add a context source if it fits in the window."""
        if source.token_estimate <= self.remaining_tokens:
            self.sources.append(source)
            return True
        return False

    def build_prompt(self) -> str:
        """Build the final prompt from all sources, ordered by priority."""
        sorted_sources = sorted(self.sources, key=lambda s: s.priority, reverse=True)
        parts = []
        for source in sorted_sources:
            parts.append(f"--- {source.name} ({source.source_type}) ---")
            parts.append(source.content)
            parts.append("")
        return "\n".join(parts)

    def summary(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "available_tokens": self.available_tokens,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "utilization": round(self.used_tokens / self.available_tokens * 100, 1),
            "source_count": len(self.sources),
            "sources": [
                {"name": s.name, "tokens": s.token_estimate, "type": s.source_type}
                for s in self.sources
            ],
        }


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

class ContextBuilder:
    """Build rich context from multiple sources."""

    def __init__(self, max_tokens: int = 8192):
        self.window = ContextWindow(max_tokens=max_tokens)

    def add_system_prompt(self, agent_name: str, domain: str) -> None:
        """Add the base system prompt."""
        prompt = (
            f"You are {agent_name}, a specialist AI agent in the domain of {domain}.\n"
            f"You are part of JARVIS, a Streaming Spec driven personal AI assistant.\n"
            f"You should be helpful, accurate, and concise in your responses.\n"
            f"Always explain your reasoning and cite sources when possible."
        )
        self.window.add_source(ContextSource(
            name="System Prompt",
            content=prompt,
            priority=100,
            source_type="system",
        ))

    def add_agent_card(self, card: dict) -> None:
        """Add agent card context."""
        content = (
            f"Agent: {card['name']}\n"
            f"Description: {card['description']}\n"
            f"Skills: {', '.join(card.get('skills', []))}\n"
            f"Can delegate: {card.get('can_delegate', False)}"
        )
        self.window.add_source(ContextSource(
            name="Agent Card",
            content=content,
            priority=90,
            source_type="system",
        ))

    def add_spec_context(self, spec: dict) -> None:
        """Add current Streaming Spec state."""
        steps_text = "\n".join(
            f"  {i+1}. [{s['status']}] {s['name']}"
            for i, s in enumerate(spec.get("steps", []))
        )
        constraints_text = "\n".join(
            f"  - {c['content']}"
            for c in spec.get("constraints", [])
        )
        content = (
            f"Current Task: {spec.get('intent', 'N/A')}\n"
            f"Status: {spec.get('status', 'unknown')}\n"
            f"Progress: {spec.get('progress', '0/0')}\n"
            f"Steps:\n{steps_text}\n"
            f"Constraints:\n{constraints_text}"
        )
        self.window.add_source(ContextSource(
            name="Streaming Spec",
            content=content,
            priority=80,
            source_type="dynamic",
        ))

    def add_memories(self, memories: list[dict]) -> None:
        """Add relevant memories."""
        if not memories:
            return
        content_parts = ["Relevant memories:"]
        for mem in memories[:10]:  # Limit to 10 memories
            content_parts.append(
                f"  - [{mem.get('type', 'fact')}] {mem.get('content', '')}"
                f" (importance: {mem.get('importance', 0):.2f})"
            )
        self.window.add_source(ContextSource(
            name="Memories",
            content="\n".join(content_parts),
            priority=60,
            source_type="dynamic",
        ))

    def add_knowledge(self, entities: list[dict], relations: list[dict] | None = None) -> None:
        """Add knowledge graph context."""
        if not entities:
            return
        content_parts = ["Relevant knowledge:"]
        for entity in entities[:15]:
            content_parts.append(
                f"  - {entity.get('label', '')} ({entity.get('type', '')})"
            )
        if relations:
            content_parts.append("\nRelations:")
            for rel in relations[:10]:
                content_parts.append(
                    f"  - {rel.get('source', '')} --[{rel.get('type', '')}]--> {rel.get('target', '')}"
                )
        self.window.add_source(ContextSource(
            name="Knowledge Graph",
            content="\n".join(content_parts),
            priority=50,
            source_type="dynamic",
        ))

    def add_conversation_history(self, messages: list[dict]) -> None:
        """Add recent conversation history."""
        if not messages:
            return
        content_parts = ["Recent conversation:"]
        for msg in messages[-10:]:  # Last 10 messages
            role = msg.get("role", "user")
            text = msg.get("content", "")[:200]  # Truncate long messages
            content_parts.append(f"  {role}: {text}")
        self.window.add_source(ContextSource(
            name="Conversation History",
            content="\n".join(content_parts),
            priority=70,
            source_type="dynamic",
        ))

    def add_tool_results(self, results: list[dict]) -> None:
        """Add recent tool execution results."""
        if not results:
            return
        content_parts = ["Recent tool results:"]
        for res in results[-5:]:
            status = "SUCCESS" if res.get("success") else "FAILED"
            content_parts.append(
                f"  - [{status}] {res.get('tool', 'unknown')}: "
                f"{res.get('output', '')[:150]}"
            )
        self.window.add_source(ContextSource(
            name="Tool Results",
            content="\n".join(content_parts),
            priority=40,
            source_type="dynamic",
        ))

    def add_custom_context(self, name: str, content: str, priority: int = 30) -> None:
        """Add arbitrary custom context."""
        self.window.add_source(ContextSource(
            name=name,
            content=content,
            priority=priority,
            source_type="user",
        ))

    def build(self) -> str:
        """Build the final prompt."""
        return self.window.build_prompt()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main():
    """Demonstrate context engineering."""
    builder = ContextBuilder(max_tokens=8192)

    # 1. System prompt
    builder.add_system_prompt("code-agent", "Software Engineering")

    # 2. Agent card
    builder.add_agent_card({
        "name": "code-agent",
        "description": "Expert in code review, refactoring, and best practices",
        "skills": ["python", "javascript", "code review", "refactoring", "testing"],
        "can_delegate": True,
    })

    # 3. Current spec
    builder.add_spec_context({
        "intent": "Review and optimize the authentication module",
        "status": "executing",
        "progress": "2/5",
        "steps": [
            {"name": "Analyze current code", "status": "completed"},
            {"name": "Identify performance bottlenecks", "status": "completed"},
            {"name": "Propose optimizations", "status": "executing"},
            {"name": "Implement changes", "status": "pending"},
            {"name": "Write tests", "status": "pending"},
        ],
        "constraints": [
            {"content": "Must maintain backward compatibility"},
            {"content": "No new dependencies allowed"},
            {"content": "Must improve response time by at least 20%"},
        ],
    })

    # 4. Memories
    builder.add_memories([
        {"type": "fact", "content": "Auth module uses bcrypt for password hashing", "importance": 0.9},
        {"type": "preference", "content": "User prefers async/await pattern over callbacks", "importance": 0.7},
        {"type": "skill_learned", "content": "JWT token rotation reduces attack surface", "importance": 0.8},
        {"type": "fact", "content": "Database queries account for 60% of auth latency", "importance": 0.95},
    ])

    # 5. Knowledge graph
    builder.add_knowledge(
        entities=[
            {"label": "AuthModule", "type": "component"},
            {"label": "UserService", "type": "service"},
            {"label": "SessionManager", "type": "component"},
            {"label": "bcrypt", "type": "library"},
            {"label": "JWT", "type": "technology"},
        ],
        relations=[
            {"source": "AuthModule", "type": "depends_on", "target": "UserService"},
            {"source": "AuthModule", "type": "uses", "target": "bcrypt"},
            {"source": "SessionManager", "type": "generates", "target": "JWT"},
        ],
    )

    # 6. Conversation history
    builder.add_conversation_history([
        {"role": "user", "content": "Can you review the auth module for performance?"},
        {"role": "assistant", "content": "I'll analyze the authentication module. Let me start by examining the current code structure."},
        {"role": "user", "content": "Focus especially on the login flow - it's slow."},
        {"role": "assistant", "content": "I've identified that database queries in the login flow are the main bottleneck."},
    ])

    # 7. Tool results
    builder.add_tool_results([
        {"tool": "read_file", "success": True, "output": "Read auth/service.py (342 lines)"},
        {"tool": "shell", "success": True, "output": "Profiling results: login() avg 450ms, 60% in DB queries"},
        {"tool": "git_log", "success": True, "output": "Last modified 3 days ago by alice: 'Add rate limiting'"},
    ])

    # 8. Custom context
    builder.add_custom_context(
        "Performance Requirements",
        "Target: Login response time < 200ms\n"
        "Current: Login response time ~450ms\n"
        "SLA: 99.9% uptime for auth service",
        priority=55,
    )

    # Build and display the prompt
    prompt = builder.build()

    print("=" * 60)
    print("CONTEXT ENGINEERING DEMO")
    print("=" * 60)
    print()

    # Print summary
    summary = builder.window.summary()
    print("Context Window Summary:")
    print(f"  Max tokens: {summary['max_tokens']}")
    print(f"  Used tokens: {summary['used_tokens']} / {summary['available_tokens']}")
    print(f"  Utilization: {summary['utilization']}%")
    print(f"  Sources: {summary['source_count']}")
    for src in summary["sources"]:
        print(f"    - {src['name']} ({src['type']}): ~{src['tokens']} tokens")

    print(f"\n{'='*60}")
    print("BUILT PROMPT:")
    print("=" * 60)
    print(prompt)
    print(f"\nTotal prompt length: {len(prompt)} characters (~{len(prompt)//4} tokens)")


if __name__ == "__main__":
    main()
