"""Tests for the prompts module and MockProvider.

Covers PromptBuilder, SystemPromptFactory, FewShotManager, PromptOptimizer,
and MockProvider (30+ tests).
"""

from __future__ import annotations

import asyncio

import pytest

from jarvis.llm.mock_provider import MockProvider
from jarvis.llm.provider import Message, Role, ToolDefinition
from jarvis.prompts.builder import PromptBuilder, PromptSection
from jarvis.prompts.factory import SystemPromptFactory
from jarvis.prompts.few_shot import FewShotExample, FewShotManager
from jarvis.prompts.optimizer import PromptOptimizer


# ====================================================================== #
# PromptBuilder
# ====================================================================== #


class TestPromptBuilder:
    def test_empty_build(self):
        builder = PromptBuilder()
        assert builder.build() == ""
        assert builder.section_count == 0

    def test_add_and_build_single_section(self):
        prompt = PromptBuilder().add_section("intro", "Hello world").build()
        assert "Hello world" in prompt

    def test_chaining(self):
        builder = (
            PromptBuilder()
            .add_section("a", "AAA")
            .add_section("b", "BBB")
        )
        assert builder.section_count == 2

    def test_priority_ordering(self):
        prompt = (
            PromptBuilder()
            .add_section("low", "LOW", priority=10)
            .add_section("high", "HIGH", priority=1)
            .build()
        )
        assert prompt.index("HIGH") < prompt.index("LOW")

    def test_remove_section(self):
        builder = PromptBuilder().add_section("a", "AAA").add_section("b", "BBB")
        builder.remove_section("a")
        assert builder.section_count == 1
        assert "AAA" not in builder.build()

    def test_has_section_and_get_section(self):
        builder = PromptBuilder().add_section("x", "content")
        assert builder.has_section("x")
        assert not builder.has_section("y")
        sec = builder.get_section("x")
        assert sec is not None
        assert sec.content == "content"

    def test_system_identity(self):
        prompt = (
            PromptBuilder()
            .add_system_identity("Jarvis", "a helpful AI", personality="witty")
            .build()
        )
        assert "You are Jarvis" in prompt
        assert "Personality: witty" in prompt

    def test_capabilities(self):
        prompt = (
            PromptBuilder()
            .add_capabilities(tools=["search", "execute"], skills=["coding"])
            .build()
        )
        assert "search" in prompt
        assert "coding" in prompt

    def test_constraints(self):
        prompt = PromptBuilder().add_constraints(["Be concise", "No PII"]).build()
        assert "- Be concise" in prompt
        assert "- No PII" in prompt

    def test_empty_constraints_noop(self):
        builder = PromptBuilder().add_constraints([])
        assert builder.section_count == 0

    def test_few_shot(self):
        prompt = (
            PromptBuilder()
            .add_few_shot([{"input": "2+2", "output": "4"}])
            .build()
        )
        assert "Example 1" in prompt
        assert "2+2" in prompt

    def test_output_format(self):
        prompt = PromptBuilder().add_output_format("JSON only").build()
        assert "JSON only" in prompt

    def test_memory_context_empty_noop(self):
        builder = PromptBuilder().add_memory_context("")
        assert builder.section_count == 0

    def test_memory_context(self):
        prompt = PromptBuilder().add_memory_context("user likes python").build()
        assert "user likes python" in prompt

    def test_knowledge_context(self):
        prompt = PromptBuilder().add_knowledge_context("graph data").build()
        assert "graph data" in prompt

    def test_token_budget_drops_low_priority(self):
        builder = PromptBuilder(max_tokens=50)
        builder.add_section("required", "short", priority=1, required=True)
        builder.add_section("optional", "x" * 1000, priority=10)
        prompt = builder.build()
        assert "short" in prompt
        assert "x" * 100 not in prompt  # dropped due to budget

    def test_section_level_truncation(self):
        builder = PromptBuilder()
        builder.add_section("big", "word " * 2000, max_tokens=50)
        prompt = builder.build()
        assert "(truncated)" in prompt

    def test_estimated_tokens(self):
        builder = PromptBuilder().add_section("a", "a" * 400)
        assert builder.estimated_tokens > 0

    def test_section_names(self):
        builder = (
            PromptBuilder()
            .add_section("alpha", "A")
            .add_section("beta", "B")
        )
        assert builder.section_names == ["alpha", "beta"]


# ====================================================================== #
# SystemPromptFactory
# ====================================================================== #


class TestSystemPromptFactory:
    def test_known_agent(self):
        prompt = SystemPromptFactory.for_agent("code-agent")
        assert "code-agent" in prompt
        assert "coding" in prompt.lower() or "code" in prompt.lower()

    def test_unknown_agent_fallback(self):
        prompt = SystemPromptFactory.for_agent("unknown-agent")
        assert "unknown-agent" in prompt
        assert "general-purpose" in prompt

    def test_agent_with_constraints(self):
        prompt = SystemPromptFactory.for_agent(
            "data-agent", constraints=["No external API calls"]
        )
        assert "No external API calls" in prompt

    def test_agent_with_memory_context(self):
        prompt = SystemPromptFactory.for_agent(
            "security-agent", memory_context="Previously found XSS"
        )
        assert "Previously found XSS" in prompt

    def test_for_task_known(self):
        prompt = SystemPromptFactory.for_task("decompose")
        assert "decomposition" in prompt.lower() or "sub-task" in prompt.lower()

    def test_for_task_unknown_fallback(self):
        prompt = SystemPromptFactory.for_task("unknown_task")
        assert "helpful AI assistant" in prompt

    def test_for_task_with_constraints(self):
        prompt = SystemPromptFactory.for_task(
            "review", constraints=["Max 500 words"]
        )
        assert "Max 500 words" in prompt

    def test_available_agents(self):
        agents = SystemPromptFactory.available_agents()
        assert "code-agent" in agents
        assert "security-agent" in agents
        assert len(agents) >= 5

    def test_available_tasks(self):
        tasks = SystemPromptFactory.available_tasks()
        assert "decompose" in tasks
        assert "debug" in tasks


# ====================================================================== #
# FewShotManager
# ====================================================================== #


class TestFewShotManager:
    def test_add_and_count(self):
        mgr = FewShotManager()
        mgr.add("in1", "out1")
        mgr.add("in2", "out2", category="math")
        assert mgr.count() == 2
        assert mgr.count("general") == 1
        assert mgr.count("math") == 1

    def test_get_examples_default(self):
        mgr = FewShotManager()
        mgr.add("a", "b", quality=0.9)
        mgr.add("c", "d", quality=0.5)
        examples = mgr.get_examples(max_examples=5)
        assert len(examples) == 2
        # highest quality first
        assert examples[0].quality_score >= examples[1].quality_score

    def test_get_examples_by_similarity(self):
        mgr = FewShotManager()
        mgr.add("how to sort a list", "use sorted()")
        mgr.add("what is the weather", "check forecast")
        mgr.add("sort array in python", "use .sort()")
        examples = mgr.get_examples(query="sorting in python", max_examples=2)
        # The sorting-related examples should be ranked higher.
        assert len(examples) == 2
        assert "sort" in examples[0].input.lower()

    def test_get_examples_token_budget(self):
        mgr = FewShotManager()
        mgr.add("x" * 4000, "y" * 4000)  # very large example
        mgr.add("small", "output")
        examples = mgr.get_examples(max_tokens=100)
        # The huge example should be skipped.
        assert len(examples) == 1
        assert examples[0].input == "small"

    def test_remove_low_quality(self):
        mgr = FewShotManager()
        mgr.add("a", "b", quality=0.1)
        mgr.add("c", "d", quality=0.8)
        removed = mgr.remove_low_quality(threshold=0.3)
        assert removed == 1
        assert mgr.count() == 1

    def test_list_categories(self):
        mgr = FewShotManager()
        mgr.add("a", "b", category="code")
        mgr.add("c", "d", category="math")
        cats = mgr.list_categories()
        assert cats == ["code", "math"]

    def test_clear(self):
        mgr = FewShotManager()
        mgr.add("a", "b", category="x")
        mgr.add("c", "d", category="y")
        mgr.clear("x")
        assert mgr.count("x") == 0
        assert mgr.count("y") == 1
        mgr.clear()
        assert mgr.count() == 0

    def test_format_examples(self):
        mgr = FewShotManager()
        mgr.add("q", "a")
        result = mgr.format_examples()
        assert result == [{"input": "q", "output": "a"}]

    def test_get_all(self):
        mgr = FewShotManager()
        mgr.add("a", "b", category="x")
        mgr.add("c", "d", category="y")
        assert len(mgr.get_all()) == 2
        assert len(mgr.get_all("x")) == 1


# ====================================================================== #
# PromptOptimizer
# ====================================================================== #


class TestPromptOptimizer:
    def test_estimate_tokens(self):
        assert PromptOptimizer.estimate_tokens("hello world") > 0

    def test_compress_within_budget(self):
        text = "short"
        result = PromptOptimizer.compress(text, target_tokens=100)
        assert "truncated" not in result

    def test_compress_truncates(self):
        text = "word " * 5000
        result = PromptOptimizer.compress(text, target_tokens=50)
        assert "(truncated)" in result

    def test_compress_collapses_blank_lines(self):
        text = "a\n\n\n\n\nb"
        result = PromptOptimizer.compress(text, target_tokens=1000)
        assert "\n\n\n" not in result

    def test_analyze_short_prompt(self):
        info = PromptOptimizer.analyze("Hello, world.")
        assert info["estimated_tokens"] > 0
        assert info["line_count"] == 1
        assert isinstance(info["suggestions"], list)

    def test_analyze_long_prompt_suggestion(self):
        text = "x " * 10000
        info = PromptOptimizer.analyze(text)
        assert any("4K" in s for s in info["suggestions"])

    def test_analyze_cache_friendly_ratio(self):
        text = "## Identity\nI am Jarvis.\n\n## Context\nDynamic stuff."
        info = PromptOptimizer.analyze(text)
        assert 0 < info["cache_friendly_prefix_ratio"] < 1.0

    def test_remove_redundancy(self):
        text = "This is a duplicate sentence.\nThis is a duplicate sentence.\nUnique line."
        result = PromptOptimizer.remove_redundancy(text)
        assert result.count("This is a duplicate sentence.") == 1
        assert "Unique line." in result

    def test_remove_redundancy_collapses_blanks(self):
        text = "A\n\n\n\nB"
        result = PromptOptimizer.remove_redundancy(text)
        assert "\n\n\n" not in result


# ====================================================================== #
# MockProvider
# ====================================================================== #


class TestMockProvider:
    @pytest.fixture
    def provider(self):
        return MockProvider()

    @pytest.mark.asyncio
    async def test_default_response(self, provider):
        msg = [Message(Role.USER, "Hi")]
        resp = await provider.chat(msg)
        assert resp.content == "Mock response from JARVIS"
        assert resp.finish_reason == "stop"
        assert provider.call_count == 1

    @pytest.mark.asyncio
    async def test_preset_responses(self, provider):
        provider.set_responses(["First", "Second"])
        msg = [Message(Role.USER, "Hi")]
        r1 = await provider.chat(msg)
        r2 = await provider.chat(msg)
        assert r1.content == "First"
        assert r2.content == "Second"
        # Third call falls back to default.
        r3 = await provider.chat(msg)
        assert r3.content == "Mock response from JARVIS"

    @pytest.mark.asyncio
    async def test_error_mode(self, provider):
        provider.set_error_mode(True)
        with pytest.raises(RuntimeError, match="Mock error"):
            await provider.chat([Message(Role.USER, "Hi")])

    @pytest.mark.asyncio
    async def test_tool_call_mode(self, provider):
        provider.set_tool_call_mode(True)
        tool = ToolDefinition(
            name="search", description="Search", parameters={"type": "object"}
        )
        msg = [Message(Role.USER, "Find something")]
        resp = await provider.chat(msg, tools=[tool])
        assert resp.has_tool_calls
        assert resp.tool_calls[0].name == "search"
        assert resp.finish_reason == "tool_calls"

    @pytest.mark.asyncio
    async def test_tool_call_mode_returns_text_after_tool_result(self, provider):
        provider.set_tool_call_mode(True)
        tool = ToolDefinition(
            name="search", description="Search", parameters={"type": "object"}
        )
        msgs = [
            Message(Role.USER, "Find something"),
            Message(Role.TOOL, "result", tool_call_id="tc_1"),
        ]
        resp = await provider.chat(msgs, tools=[tool])
        # After a tool result, should return text, not another tool call.
        assert not resp.has_tool_calls
        assert resp.content == "Mock response from JARVIS"

    @pytest.mark.asyncio
    async def test_stream(self, provider):
        provider.set_stream_delay(0)
        provider.set_responses(["Hello beautiful world"])
        chunks = []
        async for chunk in provider.stream([Message(Role.USER, "Hi")]):
            chunks.append(chunk)
        # Last chunk should have finish_reason.
        assert chunks[-1].finish_reason == "stop"
        text = "".join(c.delta for c in chunks)
        assert text == "Hello beautiful world"

    @pytest.mark.asyncio
    async def test_stream_error_mode(self, provider):
        provider.set_error_mode(True)
        with pytest.raises(RuntimeError):
            async for _ in provider.stream([Message(Role.USER, "Hi")]):
                pass

    def test_reset(self, provider):
        provider.set_responses(["a", "b"])
        provider.set_error_mode(True)
        provider.set_tool_call_mode(True)
        provider.calls.append({"test": True})
        provider.reset()
        assert provider.call_count == 0
        assert not provider._error_mode
        assert not provider._tool_call_mode
        assert len(provider._responses) == 0

    @pytest.mark.asyncio
    async def test_last_call(self, provider):
        assert provider.last_call is None
        await provider.chat([Message(Role.USER, "test")])
        assert provider.last_call is not None
        assert provider.last_call["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_usage_tracking(self, provider):
        resp = await provider.chat([Message(Role.USER, "hello")])
        assert "prompt_tokens" in resp.usage
        assert "completion_tokens" in resp.usage
        assert resp.model == "mock-model"


# ====================================================================== #
# Registry integration
# ====================================================================== #


class TestRegistryIntegration:
    def test_mock_provider_via_registry(self):
        from jarvis.llm.registry import LLMRegistry

        registry = LLMRegistry()
        provider = registry.get("mock-model")
        assert isinstance(provider, MockProvider)

    def test_model_hint_detection(self):
        from jarvis.llm.registry import LLMRegistry

        registry = LLMRegistry()
        # Should detect mock provider for mock- prefix.
        assert registry._detect_provider("mock-test") == "mock"
        assert registry._detect_provider("llama3") == "ollama"
        assert registry._detect_provider("mistral-7b") == "ollama"
        assert registry._detect_provider("codellama-13b") == "ollama"
        assert registry._detect_provider("phi-3") == "ollama"
