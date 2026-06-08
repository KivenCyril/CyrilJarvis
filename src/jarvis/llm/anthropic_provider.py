from __future__ import annotations

import json
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


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise ImportError("pip install anthropic") from e

        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**client_kwargs)

    def _to_api_messages(self, messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        system_parts = []
        api_messages = []

        for msg in messages:
            if msg.role == Role.SYSTEM:
                system_parts.append(msg.content)
            elif msg.role == Role.TOOL:
                api_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                })
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                content: list[dict[str, Any]] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                api_messages.append({"role": "assistant", "content": content})
            else:
                api_messages.append({"role": msg.role.value, "content": msg.content})

        return "\n\n".join(system_parts) if system_parts else "", api_messages

    def _to_api_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        system, api_messages = self._to_api_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._to_api_tools(tools)

        response = await self._client.messages.create(**kwargs)

        content_text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "end_turn",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        system, api_messages = self._to_api_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._to_api_tools(tools)

        current_tool: dict[str, Any] | None = None

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                        current_tool = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "arguments": "",
                        }
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield StreamChunk(delta=event.delta.text)
                    elif hasattr(event.delta, "partial_json") and current_tool:
                        current_tool["arguments"] += event.delta.partial_json
                elif event.type == "content_block_stop":
                    if current_tool:
                        try:
                            args = json.loads(current_tool["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamChunk(
                            tool_calls=[ToolCall(
                                id=current_tool["id"],
                                name=current_tool["name"],
                                arguments=args,
                            )]
                        )
                        current_tool = None
                elif event.type == "message_stop":
                    yield StreamChunk(finish_reason="end_turn")
