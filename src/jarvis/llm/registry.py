from __future__ import annotations

import logging
import os
from typing import Any

from jarvis.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_PROVIDER_MAP = {
    "openai": ("jarvis.llm.openai_provider", "OpenAIProvider"),
    "anthropic": ("jarvis.llm.anthropic_provider", "AnthropicProvider"),
    "deepseek": ("jarvis.llm.openai_provider", "OpenAIProvider"),
    "mock": ("jarvis.llm.mock_provider", "MockProvider"),
    "ollama": ("jarvis.llm.ollama_provider", "OllamaProvider"),
}

_MODEL_PROVIDER_HINTS = {
    "gpt-": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "LongCat-": "openai",
    "claude-": "anthropic",
    "qwen": "anthropic",
    "Qwen": "anthropic",
    "deepseek": "deepseek",
    "mock-": "mock",
    "llama": "ollama",
    "mistral": "ollama",
    "codellama": "ollama",
    "phi": "ollama",
}

_DEEPSEEK_DEFAULTS = {
    "base_url": "https://api.deepseek.com",
}


class LLMRegistry:
    """Factory and cache for LLM provider instances."""

    def __init__(self) -> None:
        self._instances: dict[str, LLMProvider] = {}

    def _detect_provider(self, model: str) -> str:
        for prefix, provider in _MODEL_PROVIDER_HINTS.items():
            if model.startswith(prefix):
                return provider
        return "openai"

    def get(self, model: str | None = None, **kwargs: Any) -> LLMProvider:
        model = model or os.getenv("JARVIS_DEFAULT_MODEL", "gpt-4o-mini")

        if model in self._instances:
            return self._instances[model]

        provider_name = kwargs.pop("provider", None) or self._detect_provider(model)
        module_path, class_name = _PROVIDER_MAP[provider_name]

        import importlib
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        if provider_name == "deepseek":
            for k, v in _DEEPSEEK_DEFAULTS.items():
                kwargs.setdefault(k, v)
            kwargs.setdefault("api_key", os.getenv("DEEPSEEK_API_KEY"))

        if provider_name == "openai":
            base_url = os.getenv("OPENAI_BASE_URL")
            if base_url:
                kwargs.setdefault("base_url", base_url)
            kwargs.setdefault("api_key", os.getenv("OPENAI_API_KEY"))

        if provider_name == "anthropic":
            base_url = os.getenv("ANTHROPIC_BASE_URL")
            if base_url:
                kwargs.setdefault("base_url", base_url)
            kwargs.setdefault("api_key", os.getenv("ANTHROPIC_API_KEY"))

        instance = cls(model=model, **kwargs)
        self._instances[model] = instance
        logger.info("Created LLM provider: %s (model=%s)", provider_name, model)
        return instance


llm_registry = LLMRegistry()
