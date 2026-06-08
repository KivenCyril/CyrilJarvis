from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from jarvis.gateway.channel import Channel
from jarvis.tools.base import BaseTool


class PluginMetadata(BaseModel):
    """Metadata describing a plugin."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = Field(default_factory=list)
    entry_point: str = ""
    enabled: bool = True


class PluginHook(str, Enum):
    ON_MESSAGE = "on_message"
    ON_RESPONSE = "on_response"
    ON_SPEC_CREATED = "on_spec_created"
    ON_SPEC_COMPLETED = "on_spec_completed"
    ON_AGENT_REGISTERED = "on_agent_registered"
    ON_TOOL_CALLED = "on_tool_called"
    ON_ERROR = "on_error"
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"


class Plugin(ABC):
    """Base class for JARVIS plugins.

    Plugins extend JARVIS with custom behavior by hooking into
    lifecycle events.
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return the plugin metadata."""
        ...

    async def on_load(self) -> None:
        """Called when the plugin is loaded."""

    async def on_unload(self) -> None:
        """Called when the plugin is unloaded."""

    def get_hooks(self) -> dict[PluginHook, Callable[..., Any]]:
        """Return a mapping of hooks this plugin listens to."""
        return {}

    def get_tools(self) -> list[BaseTool]:
        """Return any tools this plugin provides."""
        return []

    def get_channels(self) -> list[Channel]:
        """Return any channels this plugin provides."""
        return []
