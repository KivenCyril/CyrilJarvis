from __future__ import annotations

import pytest

from jarvis.llm.provider import LLMProvider, LLMResponse, Message, Role, ToolCall, ToolDefinition, StreamChunk
from jarvis.llm.registry import LLMRegistry


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, model: str = "mock-model", **kwargs):
        super().__init__(model, **kwargs)
        self.calls: list[dict] = []

    async def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        self.calls.append({"messages": messages, "tools": tools})
        if tools:
            return LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc_1", name=tools[0].name, arguments={"test": True})],
                finish_reason="tool_calls",
                model=self.model,
            )
        return LLMResponse(
            content="Mock response",
            finish_reason="stop",
            model=self.model,
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

    async def stream(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        yield StreamChunk(delta="Mock ")
        yield StreamChunk(delta="stream")
        yield StreamChunk(finish_reason="stop")


class TestLLMProvider:
    @pytest.mark.asyncio
    async def test_mock_chat(self):
        provider = MockProvider()
        response = await provider.chat([Message(role=Role.USER, content="hello")])
        assert response.content == "Mock response"
        assert not response.has_tool_calls
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_mock_chat_with_tools(self):
        provider = MockProvider()
        tools = [ToolDefinition(name="test_tool", description="test", parameters={})]
        response = await provider.chat([Message(role=Role.USER, content="hello")], tools=tools)
        assert response.has_tool_calls
        assert response.tool_calls[0].name == "test_tool"

    @pytest.mark.asyncio
    async def test_mock_stream(self):
        provider = MockProvider()
        chunks = []
        async for chunk in provider.stream([Message(role=Role.USER, content="hello")]):
            chunks.append(chunk)
        assert len(chunks) == 3
        assert chunks[0].delta == "Mock "
        assert chunks[1].delta == "stream"
        assert chunks[2].finish_reason == "stop"


class TestLLMRegistry:
    def test_detect_provider(self):
        registry = LLMRegistry()
        assert registry._detect_provider("gpt-4o") == "openai"
        assert registry._detect_provider("claude-sonnet-4-6") == "anthropic"
        assert registry._detect_provider("deepseek-chat") == "deepseek"
        assert registry._detect_provider("unknown-model") == "openai"

    def test_message_roles(self):
        assert Role.SYSTEM.value == "system"
        assert Role.USER.value == "user"
        assert Role.ASSISTANT.value == "assistant"
        assert Role.TOOL.value == "tool"

    def test_tool_definition(self):
        td = ToolDefinition(name="test", description="desc", parameters={"type": "object"})
        assert td.name == "test"

    def test_llm_response_properties(self):
        r = LLMResponse(content="hello")
        assert not r.has_tool_calls

        r2 = LLMResponse(content="", tool_calls=[ToolCall(id="1", name="t", arguments={})])
        assert r2.has_tool_calls
