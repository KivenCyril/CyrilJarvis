from __future__ import annotations

import asyncio
import logging
from typing import Any

from jarvis.gateway.channel import (
    Channel,
    ChannelConfig,
    ChannelMessage,
    ChannelType,
    MessageType,
)

logger = logging.getLogger(__name__)


class WebhookChannel(Channel):
    """Receives messages via webhook POST and sends responses back.

    Designed to work with a FastAPI endpoint that:
    1. Receives an HTTP POST with a JSON payload.
    2. Calls ``receive_webhook`` to create a ChannelMessage.
    3. Calls ``handle_incoming`` to route through the Gateway.
    4. Returns the response (or polls ``pending_responses``).
    """

    def __init__(self, config: ChannelConfig | None = None):
        if config is None:
            config = ChannelConfig(name="webhook", channel_type=ChannelType.WEBHOOK)
        super().__init__(config)
        self._pending: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    async def start(self) -> None:
        self._running = True
        logger.info("Webhook channel started")

    async def stop(self) -> None:
        self._running = False
        logger.info("Webhook channel stopped")

    async def send(self, channel_id: str, content: str, **kwargs: Any) -> bool:
        """Queue a response for pickup by the webhook caller."""
        await self._pending.put({"channel_id": channel_id, "content": content})
        return True

    async def receive_webhook(self, payload: dict[str, Any]) -> str:
        """Convert an incoming webhook payload into a ChannelMessage and handle it.

        Expected payload keys: sender_id, content (at minimum).
        """
        message = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            channel_id=payload.get("channel_id", "webhook"),
            sender_id=payload.get("sender_id", "anonymous"),
            sender_name=payload.get("sender_name", ""),
            content=payload.get("content", ""),
            message_type=MessageType(payload.get("message_type", "text")),
            metadata=payload.get("metadata", {}),
        )
        return await self.handle_incoming(message)

    async def get_pending(self, timeout: float = 5.0) -> dict[str, str] | None:
        """Retrieve a pending outbound response (for polling endpoints)."""
        try:
            return await asyncio.wait_for(self._pending.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
