from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    CLI = "cli"
    WEB = "web"
    API = "api"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    DINGTALK = "dingtalk"
    WECHAT = "wechat"
    WEBHOOK = "webhook"
    EMAIL = "email"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    COMMAND = "command"
    SYSTEM = "system"


class ChannelMessage(BaseModel):
    """Platform-normalized message."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    channel_type: ChannelType
    channel_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    content: str = ""
    message_type: MessageType = MessageType.TEXT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    reply_to: str | None = None
    thread_id: str | None = None


class ChannelConfig(BaseModel):
    """Configuration for a channel."""

    name: str
    channel_type: ChannelType
    enabled: bool = True
    api_token: str = ""
    webhook_url: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)


class Channel(ABC):
    """Abstract base class for all messaging channels.

    Each channel adapter normalizes inbound messages into ChannelMessage
    and converts outbound responses back to platform-specific format.
    """

    def __init__(self, config: ChannelConfig):
        self.config = config
        self._running = False
        self._message_handler: Callable[[ChannelMessage], Awaitable[str]] | None = None

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def channel_type(self) -> ChannelType:
        return self.config.channel_type

    def set_handler(self, handler: Callable[[ChannelMessage], Awaitable[str]]) -> None:
        self._message_handler = handler

    @abstractmethod
    async def start(self) -> None:
        """Start listening for messages."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel."""
        ...

    @abstractmethod
    async def send(self, channel_id: str, content: str, **kwargs: Any) -> bool:
        """Send a message to a specific channel/user."""
        ...

    async def handle_incoming(self, message: ChannelMessage) -> str:
        """Process an incoming message through the handler."""
        if self._message_handler:
            return await self._message_handler(message)
        return "No message handler configured"

    @property
    def is_running(self) -> bool:
        return self._running
