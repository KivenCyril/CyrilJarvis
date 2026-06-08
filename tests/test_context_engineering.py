"""Tests for context engineering utilities.

Tests context window management, source prioritization,
token estimation, and prompt building.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Context models (from examples/advanced/context_engineering.py)
# ---------------------------------------------------------------------------

@dataclass
class ContextSource:
    name: str
    content: str
    priority: int = 0
    token_estimate: int = 0
    source_type: str = "static"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.token_estimate:
            self.token_estimate = len(self.content) // 4


@dataclass
class ContextWindow:
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

    @property
    def utilization(self) -> float:
        if self.available_tokens == 0:
            return 0.0
        return round(self.used_tokens / self.available_tokens * 100, 1)

    def add_source(self, source: ContextSource) -> bool:
        if source.token_estimate <= self.remaining_tokens:
            self.sources.append(source)
            return True
        return False

    def remove_source(self, name: str) -> bool:
        before = len(self.sources)
        self.sources = [s for s in self.sources if s.name != name]
        return len(self.sources) < before

    def get_source(self, name: str) -> ContextSource | None:
        return next((s for s in self.sources if s.name == name), None)

    def clear(self) -> None:
        self.sources.clear()

    def build_prompt(self, separator: str = "\n\n") -> str:
        sorted_sources = sorted(self.sources, key=lambda s: s.priority, reverse=True)
        parts = []
        for source in sorted_sources:
            parts.append(f"--- {source.name} ---")
            parts.append(source.content)
        return separator.join(parts)

    def summary(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "available_tokens": self.available_tokens,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "utilization": self.utilization,
            "source_count": len(self.sources),
        }


# ---------------------------------------------------------------------------
# Token Estimator
# ---------------------------------------------------------------------------

class TokenEstimator:
    """Estimate token counts for different content types."""

    @staticmethod
    def estimate_text(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def estimate_code(code: str) -> int:
        # Code typically uses more tokens per character
        return int(len(code) / 3.5)

    @staticmethod
    def estimate_json(data: Any) -> int:
        text = json.dumps(data)
        return len(text) // 4

    @staticmethod
    def estimate_messages(messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            # Each message has overhead (~4 tokens for role/separators)
            total += 4
            total += len(msg.get("content", "")) // 4
        return total


# ---------------------------------------------------------------------------
# Prompt Template
# ---------------------------------------------------------------------------

@dataclass
class PromptTemplate:
    template: str
    variables: dict[str, str] = field(default_factory=dict)
    required_variables: list[str] = field(default_factory=list)

    def validate(self) -> tuple[bool, list[str]]:
        missing = [v for v in self.required_variables if v not in self.variables]
        return len(missing) == 0, missing

    def render(self) -> str:
        valid, missing = self.validate()
        if not valid:
            raise ValueError(f"Missing required variables: {missing}")
        return self.template.format(**self.variables)

    @property
    def estimated_tokens(self) -> int:
        try:
            rendered = self.render()
            return len(rendered) // 4
        except ValueError:
            return len(self.template) // 4


# ---------------------------------------------------------------------------
# Tests: ContextSource
# ---------------------------------------------------------------------------

class TestContextSource:
    def test_create_source(self):
        src = ContextSource(name="test", content="hello world")
        assert src.name == "test"
        assert src.token_estimate > 0

    def test_auto_token_estimate(self):
        content = "a" * 400
        src = ContextSource(name="test", content=content)
        assert src.token_estimate == 100

    def test_custom_token_estimate(self):
        src = ContextSource(name="test", content="short", token_estimate=50)
        assert src.token_estimate == 50

    def test_source_types(self):
        for stype in ["static", "dynamic", "user", "system"]:
            src = ContextSource(name="test", content="x", source_type=stype)
            assert src.source_type == stype

    def test_metadata(self):
        src = ContextSource(
            name="test", content="x",
            metadata={"key": "value", "count": 42},
        )
        assert src.metadata["key"] == "value"


# ---------------------------------------------------------------------------
# Tests: ContextWindow
# ---------------------------------------------------------------------------

class TestContextWindow:
    def test_empty_window(self):
        window = ContextWindow(max_tokens=4096)
        assert window.used_tokens == 0
        assert window.remaining_tokens == 4096 - 2048

    def test_add_source(self):
        window = ContextWindow(max_tokens=4096)
        src = ContextSource(name="test", content="hello world", token_estimate=10)
        assert window.add_source(src) is True
        assert window.used_tokens == 10

    def test_add_source_too_large(self):
        window = ContextWindow(max_tokens=100, reserved_for_output=50)
        src = ContextSource(name="huge", content="x" * 10000, token_estimate=100)
        assert window.add_source(src) is False
        assert window.used_tokens == 0

    def test_multiple_sources(self):
        window = ContextWindow(max_tokens=4096)
        for i in range(5):
            src = ContextSource(name=f"src-{i}", content=f"content {i}", token_estimate=10)
            window.add_source(src)
        assert window.used_tokens == 50
        assert len(window.sources) == 5

    def test_remove_source(self):
        window = ContextWindow()
        window.add_source(ContextSource(name="keep", content="a", token_estimate=10))
        window.add_source(ContextSource(name="remove", content="b", token_estimate=10))
        assert window.remove_source("remove") is True
        assert window.used_tokens == 10
        assert len(window.sources) == 1

    def test_remove_nonexistent(self):
        window = ContextWindow()
        assert window.remove_source("missing") is False

    def test_get_source(self):
        window = ContextWindow()
        window.add_source(ContextSource(name="target", content="found", token_estimate=5))
        src = window.get_source("target")
        assert src is not None
        assert src.content == "found"

    def test_get_nonexistent_source(self):
        window = ContextWindow()
        assert window.get_source("missing") is None

    def test_clear(self):
        window = ContextWindow()
        window.add_source(ContextSource(name="a", content="x", token_estimate=10))
        window.add_source(ContextSource(name="b", content="y", token_estimate=10))
        window.clear()
        assert window.used_tokens == 0
        assert len(window.sources) == 0

    def test_utilization(self):
        window = ContextWindow(max_tokens=4096, reserved_for_output=2048)
        window.add_source(ContextSource(name="half", content="x", token_estimate=1024))
        assert window.utilization == 50.0

    def test_build_prompt_priority_order(self):
        window = ContextWindow()
        window.add_source(ContextSource(name="low", content="LOW", priority=1, token_estimate=5))
        window.add_source(ContextSource(name="high", content="HIGH", priority=100, token_estimate=5))
        window.add_source(ContextSource(name="mid", content="MID", priority=50, token_estimate=5))
        prompt = window.build_prompt()
        high_pos = prompt.index("HIGH")
        mid_pos = prompt.index("MID")
        low_pos = prompt.index("LOW")
        assert high_pos < mid_pos < low_pos

    def test_build_prompt_contains_all(self):
        window = ContextWindow()
        window.add_source(ContextSource(name="A", content="Content A", token_estimate=5))
        window.add_source(ContextSource(name="B", content="Content B", token_estimate=5))
        prompt = window.build_prompt()
        assert "Content A" in prompt
        assert "Content B" in prompt
        assert "--- A ---" in prompt
        assert "--- B ---" in prompt

    def test_summary(self):
        window = ContextWindow(max_tokens=4096)
        window.add_source(ContextSource(name="test", content="x", token_estimate=100))
        summary = window.summary()
        assert summary["max_tokens"] == 4096
        assert summary["used_tokens"] == 100
        assert summary["source_count"] == 1


# ---------------------------------------------------------------------------
# Tests: TokenEstimator
# ---------------------------------------------------------------------------

class TestTokenEstimator:
    def test_estimate_text(self):
        assert TokenEstimator.estimate_text("a" * 100) == 25

    def test_estimate_empty_text(self):
        assert TokenEstimator.estimate_text("") == 0

    def test_estimate_code(self):
        code = "def hello():\n    return 'world'"
        tokens = TokenEstimator.estimate_code(code)
        assert tokens > 0

    def test_estimate_json(self):
        data = {"key": "value", "list": [1, 2, 3]}
        tokens = TokenEstimator.estimate_json(data)
        assert tokens > 0

    def test_estimate_messages(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help?"},
        ]
        tokens = TokenEstimator.estimate_messages(messages)
        assert tokens > 0
        # Should include overhead per message
        assert tokens > len("Hello") // 4 + len("Hi there! How can I help?") // 4

    def test_code_more_tokens_than_text(self):
        content = "x" * 100
        code_tokens = TokenEstimator.estimate_code(content)
        text_tokens = TokenEstimator.estimate_text(content)
        assert code_tokens >= text_tokens


# ---------------------------------------------------------------------------
# Tests: PromptTemplate
# ---------------------------------------------------------------------------

class TestPromptTemplate:
    def test_render_template(self):
        template = PromptTemplate(
            template="Hello, {name}! You are a {role}.",
            variables={"name": "JARVIS", "role": "assistant"},
            required_variables=["name", "role"],
        )
        result = template.render()
        assert result == "Hello, JARVIS! You are a assistant."

    def test_validate_all_present(self):
        template = PromptTemplate(
            template="{a} {b}",
            variables={"a": "1", "b": "2"},
            required_variables=["a", "b"],
        )
        valid, missing = template.validate()
        assert valid is True
        assert missing == []

    def test_validate_missing(self):
        template = PromptTemplate(
            template="{a} {b}",
            variables={"a": "1"},
            required_variables=["a", "b"],
        )
        valid, missing = template.validate()
        assert valid is False
        assert "b" in missing

    def test_render_missing_raises(self):
        template = PromptTemplate(
            template="{name}",
            variables={},
            required_variables=["name"],
        )
        with pytest.raises(ValueError, match="Missing"):
            template.render()

    def test_estimated_tokens(self):
        template = PromptTemplate(
            template="Hello {name}",
            variables={"name": "World"},
        )
        assert template.estimated_tokens > 0

    def test_no_required_variables(self):
        template = PromptTemplate(
            template="Static prompt with no vars",
        )
        valid, missing = template.validate()
        assert valid is True
        assert template.render() == "Static prompt with no vars"

    def test_extra_variables_ignored(self):
        template = PromptTemplate(
            template="Hello {name}",
            variables={"name": "World", "extra": "ignored"},
            required_variables=["name"],
        )
        result = template.render()
        assert result == "Hello World"


# ---------------------------------------------------------------------------
# Tests: Integration - Full context building
# ---------------------------------------------------------------------------

class TestContextBuilding:
    def test_full_context_build(self):
        window = ContextWindow(max_tokens=16384)

        # System prompt
        window.add_source(ContextSource(
            name="System", content="You are JARVIS.",
            priority=100, source_type="system", token_estimate=10,
        ))

        # Task
        window.add_source(ContextSource(
            name="Task", content="Review this code for bugs.",
            priority=80, source_type="user", token_estimate=10,
        ))

        # Memory
        window.add_source(ContextSource(
            name="Memory", content="User prefers Python.",
            priority=60, source_type="dynamic", token_estimate=10,
        ))

        # Knowledge
        window.add_source(ContextSource(
            name="Knowledge", content="Python 3.12 added new typing features.",
            priority=50, source_type="dynamic", token_estimate=15,
        ))

        prompt = window.build_prompt()
        # System should come first (highest priority)
        assert prompt.index("JARVIS") < prompt.index("Review")
        assert prompt.index("Review") < prompt.index("prefers Python")

    def test_context_overflow_handling(self):
        window = ContextWindow(max_tokens=200, reserved_for_output=100)
        # Available: 100 tokens

        # This should fit
        assert window.add_source(ContextSource(
            name="small", content="x", token_estimate=50,
        )) is True

        # This should NOT fit
        assert window.add_source(ContextSource(
            name="large", content="y" * 1000, token_estimate=80,
        )) is False

        assert len(window.sources) == 1

    def test_context_with_all_types(self):
        window = ContextWindow(max_tokens=32768)
        types = ["system", "dynamic", "user", "static"]
        for i, stype in enumerate(types):
            window.add_source(ContextSource(
                name=f"src-{stype}", content=f"Content for {stype}",
                priority=100 - i * 10, source_type=stype, token_estimate=20,
            ))
        assert len(window.sources) == 4
        prompt = window.build_prompt()
        for stype in types:
            assert f"Content for {stype}" in prompt
