"""Mock LLM provider for testing and development."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from jarvis.llm.provider import (
    LLMProvider,
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class MockProvider(LLMProvider):
    """Mock LLM provider for testing and development.

    Returns configurable responses, tracks all calls for verification,
    and can simulate tool calling, errors, and streaming.

    Usage::

        provider = MockProvider()
        provider.set_responses(["Hello!", "How can I help?"])
        response = await provider.chat([Message(Role.USER, "Hi")])
        assert response.content == "Hello!"
        assert provider.call_count == 1
    """

    def __init__(self, model: str = "mock-model", **kwargs: Any) -> None:
        super().__init__(model, **kwargs)
        self.calls: list[dict[str, Any]] = []
        self._responses: list[str] = []
        self._default_response: str = "Mock response from JARVIS"
        self._tool_call_mode: bool = False
        self._error_mode: bool = False
        self._stream_delay: float = 0.01

    # ---- Configuration helpers ----

    def set_responses(self, responses: list[str]) -> None:
        """Pre-configure responses to return in order."""
        self._responses = list(responses)

    def set_error_mode(self, enabled: bool) -> None:
        """When enabled, all calls raise a ``RuntimeError``."""
        self._error_mode = enabled

    def set_tool_call_mode(self, enabled: bool) -> None:
        """When enabled, the first chat call returns a tool call instead of text."""
        self._tool_call_mode = enabled

    def set_stream_delay(self, delay: float) -> None:
        """Set the delay between streamed words (seconds)."""
        self._stream_delay = delay

    # ---- LLMProvider interface ----

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Record the call for later inspection.
        self.calls.append(
            {
                "messages": [
                    {"role": m.role.value, "content": m.content[:100]}
                    for m in messages
                ],
                "tools": [t.name for t in tools] if tools else None,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        if self._error_mode:
            raise RuntimeError("Mock error: LLM service unavailable")

        # If tool calling mode, tools provided, and no tool result yet -> return a tool call.
        if (
            self._tool_call_mode
            and tools
            and not any(m.role == Role.TOOL for m in messages)
        ):
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id=f"tc_{len(self.calls)}",
                        name=tools[0].name,
                        arguments={"test": True},
                    )
                ],
                finish_reason="tool_calls",
                model=self.model,
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            )

        response_text = (
            self._responses.pop(0) if self._responses else self._default_response
        )
        return LLMResponse(
            content=response_text,
            finish_reason="stop",
            model=self.model,
            usage={
                "prompt_tokens": sum(len(m.content) // 4 for m in messages),
                "completion_tokens": len(response_text) // 4,
            },
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        # Record the call.
        self.calls.append(
            {
                "messages": [
                    {"role": m.role.value, "content": m.content[:100]}
                    for m in messages
                ],
                "tools": [t.name for t in tools] if tools else None,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        if self._error_mode:
            raise RuntimeError("Mock error: LLM service unavailable")

        response = (
            self._responses.pop(0) if self._responses else self._default_response
        )
        words = response.split()
        for i, word in enumerate(words):
            yield StreamChunk(delta=word + (" " if i < len(words) - 1 else ""))
            await asyncio.sleep(self._stream_delay)
        yield StreamChunk(finish_reason="stop")

    # ---- Inspection helpers ----

    def reset(self) -> None:
        """Clear all recorded calls and reset configuration."""
        self.calls.clear()
        self._responses.clear()
        self._tool_call_mode = False
        self._error_mode = False

    @property
    def call_count(self) -> int:
        """Number of chat/stream calls made so far."""
        return len(self.calls)

    @property
    def last_call(self) -> dict[str, Any] | None:
        """The most recent call record, or ``None``."""
        return self.calls[-1] if self.calls else None
