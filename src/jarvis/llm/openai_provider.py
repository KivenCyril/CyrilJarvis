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


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs (OpenAI, DeepSeek, local vLLM, etc.)."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("pip install openai") from e

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _to_api_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]
            result.append(entry)
        return result

    def _to_api_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _parse_tool_calls(self, api_tool_calls: Any) -> list[ToolCall]:
        if not api_tool_calls:
            return []
        result = []
        for tc in api_tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                args = {}
            result.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return result

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        api_messages = self._to_api_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._to_api_tools(tools)

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=self._parse_tool_calls(choice.message.tool_calls),
            finish_reason=choice.finish_reason or "stop",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        api_messages = self._to_api_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._to_api_tools(tools)

        stream = await self._client.chat.completions.create(**kwargs)
        accumulated_tool_calls: dict[int, dict[str, str]] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            text_delta = delta.content or ""

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in accumulated_tool_calls:
                        accumulated_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        accumulated_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            accumulated_tool_calls[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            accumulated_tool_calls[idx]["arguments"] += tc_delta.function.arguments

            finish = chunk.choices[0].finish_reason if chunk.choices else None

            tool_calls = []
            if finish == "tool_calls" and accumulated_tool_calls:
                for tc_data in accumulated_tool_calls.values():
                    try:
                        args = json.loads(tc_data["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(ToolCall(id=tc_data["id"], name=tc_data["name"], arguments=args))

            yield StreamChunk(delta=text_delta, tool_calls=tool_calls, finish_reason=finish)
