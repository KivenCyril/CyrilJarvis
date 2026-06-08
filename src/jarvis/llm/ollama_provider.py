"""Provider for Ollama local models.

Ollama runs models locally and exposes an OpenAI-compatible API.
Default endpoint: ``http://localhost:11434/v1``
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from jarvis.llm.provider import (
    LLMProvider,
    LLMResponse,
    Message,
    StreamChunk,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Provider for Ollama local models.

    Ollama runs models locally.  Uses the OpenAI-compatible API so we
    delegate to :class:`OpenAIProvider` with the appropriate *base_url*
    and a dummy API key (Ollama does not require one).

    Default base URL: ``http://localhost:11434/v1``
    """

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        from jarvis.llm.openai_provider import OpenAIProvider

        self._delegate = OpenAIProvider(
            model=model, base_url=base_url, api_key=api_key, **kwargs
        )
        logger.info(
            "OllamaProvider: delegating to OpenAIProvider (base_url=%s, model=%s)",
            base_url,
            model,
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return await self._delegate.chat(messages, tools, temperature, max_tokens)

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]:
        async for chunk in self._delegate.stream(
            messages, tools, temperature, max_tokens
        ):
            yield chunk
