"""Advanced tests for the JARVIS prompt engineering subsystem.

Covers PromptBuilder with all section types, section priority ordering,
token budget enforcement, cache-friendly section handling,
SystemPromptFactory for all agents and task types, FewShotManager
similarity and budget selection, PromptOptimizer compression / analysis /
redundancy removal, MockProvider response configuration / tool calls /
streaming / error mode, and OllamaProvider initialization.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from jarvis.llm.mock_provider import MockProvider
from jarvis.llm.provider import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)
from jarvis.prompts.builder import PromptBuilder, PromptSection
from jarvis.prompts.factory import SystemPromptFactory
from jarvis.prompts.few_shot import FewShotExample, FewShotManager
from jarvis.prompts.optimizer import PromptOptimizer


# ===========================================================================
# 1. PromptBuilder with all section types
# ===========================================================================


class TestPromptBuilderSections:
    def test_add_system_identity(self):
        builder = PromptBuilder()
        builder.add_system_identity("Jarvis", "a helpful AI")
        assert builder.has_section("identity")
        section = builder.get_section("identity")
        assert section is not None
        assert "Jarvis" in section.content

    def test_add_capabilities(self):
        builder = PromptBuilder()
        builder.add_capabilities(tools=["search", "code"], skills=["python"])
        assert builder.has_section("capabilities")
        built = builder.build()
        assert "search" in built

    def test_add_constraints(self):
        builder = PromptBuilder()
        builder.add_constraints(["Be concise", "Use markdown"])
        assert builder.has_section("constraints")
        built = builder.build()
        assert "Be concise" in built

    def test_add_constraints_empty(self):
        builder = PromptBuilder()
        builder.add_constraints([])
        assert not builder.has_section("constraints")

    def test_add_context(self):
        builder = PromptBuilder()
        builder.add_context("User is a Python expert", label="UserInfo")
        assert builder.has_section("context_UserInfo")

    def test_add_few_shot(self):
        builder = PromptBuilder()
        builder.add_few_shot([
            {"input": "What is 2+2?", "output": "4"},
            {"input": "What is 3+3?", "output": "6"},
        ])
        assert builder.has_section("few_shot")
        built = builder.build()
        assert "Example 1" in built
        assert "Example 2" in built

    def test_add_few_shot_empty(self):
        builder = PromptBuilder()
        builder.add_few_shot([])
        assert not builder.has_section("few_shot")

    def test_add_output_format(self):
        builder = PromptBuilder()
        builder.add_output_format("Return JSON")
        assert builder.has_section("output_format")

    def test_add_memory_context(self):
        builder = PromptBuilder()
        builder.add_memory_context("User prefers Python")
        assert builder.has_section("memories")

    def test_add_memory_context_empty(self):
        builder = PromptBuilder()
        builder.add_memory_context("")
        assert not builder.has_section("memories")

    def test_add_knowledge_context(self):
        builder = PromptBuilder()
        builder.add_knowledge_context("API docs for X")
        assert builder.has_section("knowledge")

    def test_add_knowledge_context_empty(self):
        builder = PromptBuilder()
        builder.add_knowledge_context("")
        assert not builder.has_section("knowledge")

    def test_remove_section(self):
        builder = PromptBuilder()
        builder.add_context("ctx")
        builder.remove_section("context_Context")
        assert not builder.has_section("context_Context")

    def test_chaining(self):
        prompt = (
            PromptBuilder()
            .add_system_identity("J", "ai")
            .add_constraints(["c1"])
            .add_context("ctx")
            .build()
        )
        assert "J" in prompt
        assert "c1" in prompt


# ===========================================================================
# 2. Section priority ordering
# ===========================================================================


class TestSectionPriorityOrdering:
    def test_higher_priority_first(self):
        builder = PromptBuilder()
        builder.add_section("low", "LOW_CONTENT", priority=10)
        builder.add_section("high", "HIGH_CONTENT", priority=1)
        built = builder.build()
        assert built.index("HIGH_CONTENT") < built.index("LOW_CONTENT")

    def test_identity_always_first(self):
        builder = PromptBuilder()
        builder.add_output_format("format")
        builder.add_system_identity("Agent", "description")
        built = builder.build()
        assert built.startswith("You are Agent")


# ===========================================================================
# 3. Token budget enforcement
# ===========================================================================


class TestTokenBudget:
    def test_global_budget_drops_optional(self):
        builder = PromptBuilder(max_tokens=50)
        builder.add_section("small", "Short text", priority=1, required=True)
        builder.add_section("big", "X" * 1000, priority=10, required=False)
        built = builder.build()
        assert "Short text" in built
        assert "X" * 100 not in built

    def test_required_always_included(self):
        builder = PromptBuilder(max_tokens=10)
        builder.add_section("req", "REQUIRED CONTENT", priority=1, required=True)
        built = builder.build()
        assert "REQUIRED CONTENT" in built

    def test_section_max_tokens_truncation(self):
        builder = PromptBuilder(max_tokens=10000)
        builder.add_section("big", "W" * 2000, max_tokens=10)
        built = builder.build()
        assert "truncated" in built
        assert len(built) < 2000

    def test_estimated_tokens(self):
        builder = PromptBuilder()
        builder.add_section("s", "Hello world")
        assert builder.estimated_tokens > 0

    def test_section_count(self):
        builder = PromptBuilder()
        assert builder.section_count == 0
        builder.add_section("a", "A")
        builder.add_section("b", "B")
        assert builder.section_count == 2

    def test_section_names(self):
        builder = PromptBuilder()
        builder.add_section("alpha", "A")
        builder.add_section("beta", "B")
        assert builder.section_names == ["alpha", "beta"]


# ===========================================================================
# 4. Cache-friendly section handling
# ===========================================================================


class TestCacheFriendly:
    def test_cache_friendly_section(self):
        builder = PromptBuilder()
        builder.add_system_identity("Agent", "desc")
        section = builder.get_section("identity")
        assert section.cache_friendly is True

    def test_non_cache_friendly_section(self):
        builder = PromptBuilder()
        builder.add_section("dynamic", "new data", cache_friendly=False)
        section = builder.get_section("dynamic")
        assert section.cache_friendly is False


# ===========================================================================
# 5. SystemPromptFactory for all 10 agents
# ===========================================================================


class TestSystemPromptFactoryAgents:
    AGENTS = [
        "code-agent", "knowledge-agent", "data-agent",
        "security-agent", "devops-agent", "writing-agent",
        "research-agent", "ops-agent", "calendar-agent", "comms-agent",
    ]

    def test_available_agents(self):
        agents = SystemPromptFactory.available_agents()
        assert len(agents) == 10
        for a in self.AGENTS:
            assert a in agents

    @pytest.mark.parametrize("agent_name", AGENTS)
    def test_for_agent(self, agent_name: str):
        prompt = SystemPromptFactory.for_agent(agent_name)
        assert len(prompt) > 0
        assert agent_name in prompt

    def test_unknown_agent_uses_default(self):
        prompt = SystemPromptFactory.for_agent("unknown-agent")
        assert "general-purpose" in prompt

    def test_for_agent_with_context(self):
        prompt = SystemPromptFactory.for_agent(
            "code-agent",
            tools=["git", "python"],
            constraints=["No eval"],
            memory_context="User prefers TypeScript",
        )
        assert "git" in prompt
        assert "No eval" in prompt
        assert "TypeScript" in prompt

    def test_for_agent_with_few_shot(self):
        prompt = SystemPromptFactory.for_agent(
            "code-agent",
            few_shot_examples=[
                {"input": "Fix the bug", "output": "Fixed!"},
            ],
        )
        assert "Fix the bug" in prompt


# ===========================================================================
# 6. SystemPromptFactory for all 6 task types
# ===========================================================================


class TestSystemPromptFactoryTasks:
    TASKS = ["decompose", "review", "summarize", "extract", "plan", "debug"]

    def test_available_tasks(self):
        tasks = SystemPromptFactory.available_tasks()
        assert len(tasks) == 6
        for t in self.TASKS:
            assert t in tasks

    @pytest.mark.parametrize("task_type", TASKS)
    def test_for_task(self, task_type: str):
        prompt = SystemPromptFactory.for_task(task_type)
        assert len(prompt) > 0

    def test_unknown_task_uses_fallback(self):
        prompt = SystemPromptFactory.for_task("unknown_task")
        assert "helpful AI assistant" in prompt

    def test_for_task_with_constraints(self):
        prompt = SystemPromptFactory.for_task(
            "review",
            constraints=["Focus on security"],
        )
        assert "Focus on security" in prompt


# ===========================================================================
# 7. FewShotManager similarity selection
# ===========================================================================


class TestFewShotSimilarity:
    def test_similarity_ranking(self):
        mgr = FewShotManager()
        mgr.add("How to sort a list in Python", "Use sorted()", category="python")
        mgr.add("How to read a file in Python", "Use open()", category="python")
        mgr.add("How to deploy Docker", "Use docker-compose", category="python")

        examples = mgr.get_examples(
            category="python",
            query="sorting in Python",
            max_examples=2,
        )
        assert len(examples) == 2
        # The most similar should come first
        assert "sort" in examples[0].input.lower()

    def test_quality_ranking_without_query(self):
        mgr = FewShotManager()
        mgr.add("Low", "L", quality=0.1)
        mgr.add("High", "H", quality=0.9)
        mgr.add("Mid", "M", quality=0.5)

        examples = mgr.get_examples(max_examples=2)
        assert examples[0].input == "High"

    def test_empty_category(self):
        mgr = FewShotManager()
        assert mgr.get_examples(category="nonexistent") == []


# ===========================================================================
# 8. FewShotManager token budget selection
# ===========================================================================


class TestFewShotTokenBudget:
    def test_token_budget_limits_examples(self):
        mgr = FewShotManager()
        # Each example ~ 50 chars = ~13 tokens
        for i in range(10):
            mgr.add(f"Input example number {i}" * 5, f"Output {i}" * 5)

        examples = mgr.get_examples(max_examples=10, max_tokens=20)
        assert len(examples) < 10

    def test_max_examples_limits(self):
        mgr = FewShotManager()
        for i in range(10):
            mgr.add(f"In{i}", f"Out{i}")
        examples = mgr.get_examples(max_examples=3)
        assert len(examples) == 3

    def test_format_examples(self):
        mgr = FewShotManager()
        mgr.add("Q1", "A1")
        mgr.add("Q2", "A2")
        formatted = mgr.format_examples(max_examples=2)
        assert len(formatted) == 2
        assert formatted[0]["input"] == "Q1"
        assert formatted[0]["output"] == "A1"

    def test_remove_low_quality(self):
        mgr = FewShotManager()
        mgr.add("Good", "G", quality=0.8)
        mgr.add("Bad", "B", quality=0.1)
        removed = mgr.remove_low_quality(threshold=0.5)
        assert removed == 1
        assert mgr.count() == 1

    def test_clear_category(self):
        mgr = FewShotManager()
        mgr.add("A", "A", category="cat1")
        mgr.add("B", "B", category="cat2")
        mgr.clear(category="cat1")
        assert mgr.count(category="cat1") == 0
        assert mgr.count(category="cat2") == 1

    def test_clear_all(self):
        mgr = FewShotManager()
        mgr.add("A", "A")
        mgr.add("B", "B")
        mgr.clear()
        assert mgr.count() == 0

    def test_list_categories(self):
        mgr = FewShotManager()
        mgr.add("A", "A", category="beta")
        mgr.add("B", "B", category="alpha")
        cats = mgr.list_categories()
        assert cats == ["alpha", "beta"]

    def test_get_all(self):
        mgr = FewShotManager()
        mgr.add("A", "A", category="c1")
        mgr.add("B", "B", category="c2")
        all_ex = mgr.get_all()
        assert len(all_ex) == 2
        c1 = mgr.get_all(category="c1")
        assert len(c1) == 1


# ===========================================================================
# 9. PromptOptimizer compression
# ===========================================================================


class TestPromptOptimizerCompression:
    def test_compress_collapses_blank_lines(self):
        text = "Line 1\n\n\n\n\nLine 2"
        result = PromptOptimizer.compress(text, target_tokens=1000)
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_compress_strips_trailing_whitespace(self):
        text = "Hello   \nWorld   "
        result = PromptOptimizer.compress(text, target_tokens=1000)
        assert "   " not in result

    def test_compress_removes_horizontal_rules(self):
        text = "Above\n---\nBelow"
        result = PromptOptimizer.compress(text, target_tokens=1000)
        assert "---" not in result

    def test_compress_truncates_when_over_budget(self):
        text = "A" * 10000
        result = PromptOptimizer.compress(text, target_tokens=50)
        assert "truncated" in result
        assert len(result) < 10000

    def test_compress_short_text_unchanged(self):
        text = "Short text"
        result = PromptOptimizer.compress(text, target_tokens=1000)
        assert result == "Short text"


# ===========================================================================
# 10. PromptOptimizer redundancy removal
# ===========================================================================


class TestPromptOptimizerRedundancy:
    def test_remove_duplicate_lines(self):
        text = "First line\nSecond line\nFirst line\nThird line"
        result = PromptOptimizer.remove_redundancy(text)
        # "First line" is short (<20 chars), so it's kept as-is
        assert "Third line" in result

    def test_remove_duplicate_long_lines(self):
        long = "This is a sufficiently long line to be deduplicated by the optimizer"
        text = f"{long}\nOther content\n{long}"
        result = PromptOptimizer.remove_redundancy(text)
        assert result.count(long) == 1

    def test_collapse_blank_lines(self):
        text = "A\n\n\n\nB"
        result = PromptOptimizer.remove_redundancy(text)
        assert "\n\n\n" not in result

    def test_headers_preserved(self):
        text = "# Header\nContent\n# Header\nMore content"
        result = PromptOptimizer.remove_redundancy(text)
        assert result.count("# Header") == 2


# ===========================================================================
# 11. PromptOptimizer analysis suggestions
# ===========================================================================


class TestPromptOptimizerAnalysis:
    def test_basic_analysis(self):
        text = "Hello world"
        analysis = PromptOptimizer.analyze(text)
        assert "estimated_tokens" in analysis
        assert analysis["estimated_tokens"] > 0
        assert analysis["line_count"] == 1
        assert analysis["section_count"] == 0

    def test_large_prompt_suggestion(self):
        text = "X" * 20000
        analysis = PromptOptimizer.analyze(text)
        assert any("4K" in s for s in analysis["suggestions"])

    def test_excessive_whitespace_suggestion(self):
        text = "word  " * 50
        analysis = PromptOptimizer.analyze(text)
        assert any("whitespace" in s.lower() for s in analysis["suggestions"])

    def test_long_line_suggestion(self):
        text = "x" * 600
        analysis = PromptOptimizer.analyze(text)
        assert any("500 chars" in s for s in analysis["suggestions"])

    def test_duplicate_sentence_analyzed(self):
        sentence = "This is a sufficiently long sentence for detection."
        text = f"{sentence} {sentence}"
        analysis = PromptOptimizer.analyze(text)
        assert "estimated_tokens" in analysis

    def test_cache_friendly_ratio(self):
        text = "Static prefix\n## Context\nDynamic stuff"
        analysis = PromptOptimizer.analyze(text)
        assert 0 < analysis["cache_friendly_prefix_ratio"] < 1

    def test_cache_friendly_no_dynamic(self):
        text = "All static content"
        analysis = PromptOptimizer.analyze(text)
        assert analysis["cache_friendly_prefix_ratio"] == 1.0

    def test_estimate_tokens(self):
        assert PromptOptimizer.estimate_tokens("Hello World") > 0
        assert PromptOptimizer.estimate_tokens("") == 1


# ===========================================================================
# 12. MockProvider response configuration
# ===========================================================================


class TestMockProviderResponses:
    @pytest.mark.asyncio
    async def test_default_response(self):
        provider = MockProvider()
        resp = await provider.chat([Message(Role.USER, "hi")])
        assert resp.content == "Mock response from JARVIS"

    @pytest.mark.asyncio
    async def test_set_responses(self):
        provider = MockProvider()
        provider.set_responses(["Reply 1", "Reply 2"])
        r1 = await provider.chat([Message(Role.USER, "a")])
        r2 = await provider.chat([Message(Role.USER, "b")])
        assert r1.content == "Reply 1"
        assert r2.content == "Reply 2"

    @pytest.mark.asyncio
    async def test_responses_exhausted_falls_back(self):
        provider = MockProvider()
        provider.set_responses(["Only one"])
        await provider.chat([Message(Role.USER, "a")])
        r = await provider.chat([Message(Role.USER, "b")])
        assert r.content == "Mock response from JARVIS"

    @pytest.mark.asyncio
    async def test_call_tracking(self):
        provider = MockProvider()
        await provider.chat([Message(Role.USER, "test")])
        assert provider.call_count == 1
        assert provider.last_call is not None
        assert provider.last_call["messages"][0]["content"] == "test"

    @pytest.mark.asyncio
    async def test_reset(self):
        provider = MockProvider()
        provider.set_responses(["x"])
        await provider.chat([Message(Role.USER, "a")])
        provider.reset()
        assert provider.call_count == 0
        assert provider._responses == []

    @pytest.mark.asyncio
    async def test_usage_stats(self):
        provider = MockProvider()
        resp = await provider.chat([Message(Role.USER, "Hello world")])
        assert "prompt_tokens" in resp.usage
        assert "completion_tokens" in resp.usage


# ===========================================================================
# 13. MockProvider tool call simulation
# ===========================================================================


class TestMockProviderToolCalls:
    @pytest.mark.asyncio
    async def test_tool_call_mode(self):
        provider = MockProvider()
        provider.set_tool_call_mode(True)
        tools = [
            ToolDefinition(name="search", description="Search", parameters={})
        ]
        resp = await provider.chat([Message(Role.USER, "find X")], tools=tools)
        assert resp.has_tool_calls
        assert resp.tool_calls[0].name == "search"
        assert resp.finish_reason == "tool_calls"

    @pytest.mark.asyncio
    async def test_tool_call_with_tool_result(self):
        provider = MockProvider()
        provider.set_tool_call_mode(True)
        tools = [
            ToolDefinition(name="calc", description="Calculate", parameters={})
        ]
        messages = [
            Message(Role.USER, "compute"),
            Message(Role.TOOL, "42", tool_call_id="tc_1"),
        ]
        resp = await provider.chat(messages, tools=tools)
        # When a tool result is present, return text response
        assert not resp.has_tool_calls
        assert resp.content  # non-empty


# ===========================================================================
# 14. MockProvider streaming
# ===========================================================================


class TestMockProviderStreaming:
    @pytest.mark.asyncio
    async def test_stream_basic(self):
        provider = MockProvider()
        provider.set_responses(["Hello World"])
        provider.set_stream_delay(0.001)

        chunks = []
        async for chunk in provider.stream([Message(Role.USER, "hi")]):
            chunks.append(chunk)

        # Last chunk should have finish_reason
        assert chunks[-1].finish_reason == "stop"
        # Reconstruct text
        text = "".join(c.delta for c in chunks)
        assert "Hello" in text
        assert "World" in text

    @pytest.mark.asyncio
    async def test_stream_records_call(self):
        provider = MockProvider()
        provider.set_stream_delay(0.001)
        async for _ in provider.stream([Message(Role.USER, "test")]):
            pass
        assert provider.call_count == 1


# ===========================================================================
# 15. MockProvider error mode
# ===========================================================================


class TestMockProviderErrorMode:
    @pytest.mark.asyncio
    async def test_error_mode_chat(self):
        provider = MockProvider()
        provider.set_error_mode(True)
        with pytest.raises(RuntimeError, match="Mock error"):
            await provider.chat([Message(Role.USER, "x")])

    @pytest.mark.asyncio
    async def test_error_mode_stream(self):
        provider = MockProvider()
        provider.set_error_mode(True)
        with pytest.raises(RuntimeError, match="Mock error"):
            async for _ in provider.stream([Message(Role.USER, "x")]):
                pass

    @pytest.mark.asyncio
    async def test_error_mode_toggle(self):
        provider = MockProvider()
        provider.set_error_mode(True)
        with pytest.raises(RuntimeError):
            await provider.chat([Message(Role.USER, "x")])

        provider.set_error_mode(False)
        resp = await provider.chat([Message(Role.USER, "x")])
        assert resp.content  # should succeed


# ===========================================================================
# 16. OllamaProvider initialization
# ===========================================================================


class TestOllamaProviderInit:
    def test_default_init(self):
        # OllamaProvider delegates to OpenAIProvider, which may fail
        # if openai is not installed. We test the import path.
        try:
            from jarvis.llm.ollama_provider import OllamaProvider

            provider = OllamaProvider(model="llama3")
            assert provider.model == "llama3"
            assert provider._delegate is not None
        except ImportError:
            pytest.skip("openai not installed")

    def test_custom_base_url(self):
        try:
            from jarvis.llm.ollama_provider import OllamaProvider

            provider = OllamaProvider(
                model="mistral",
                base_url="http://custom:11434/v1",
            )
            assert provider.model == "mistral"
        except ImportError:
            pytest.skip("openai not installed")


# ===========================================================================
# 17. LLMResponse model
# ===========================================================================


class TestLLMResponse:
    def test_has_tool_calls_true(self):
        resp = LLMResponse(
            content="",
            tool_calls=[ToolCall(id="1", name="t", arguments={})],
        )
        assert resp.has_tool_calls is True

    def test_has_tool_calls_false(self):
        resp = LLMResponse(content="hello")
        assert resp.has_tool_calls is False

    def test_defaults(self):
        resp = LLMResponse()
        assert resp.content == ""
        assert resp.finish_reason == "stop"
        assert resp.tool_calls == []
