from __future__ import annotations

import logging
from typing import Any

from jarvis.gateway.channel import Channel, ChannelConfig, ChannelType

logger = logging.getLogger(__name__)


class DiscordChannel(Channel):
    """Discord Bot channel adapter.

    Requires: discord.py (optional dependency).
    """

    def __init__(self, config: ChannelConfig | None = None):
        if config is None:
            config = ChannelConfig(name="discord", channel_type=ChannelType.DISCORD)
        super().__init__(config)
        self._client: Any = None

    def _ensure_library(self) -> None:
        try:
            import discord  # noqa: F401
        except ImportError:
            raise ImportError(
                "discord.py is required for DiscordChannel. "
                "Install it with: pip install discord.py"
            )

    async def start(self) -> None:
        self._ensure_library()
        # TODO: Initialize discord.Client and connect
        self._running = True
        logger.info("Discord channel started")

    async def stop(self) -> None:
        self._running = False
        self._client = None
        logger.info("Discord channel stopped")

    async def send(self, channel_id: str, content: str, **kwargs: Any) -> bool:
        self._ensure_library()
        if self._client is None:
            logger.error("Discord client is not initialized")
            return False
        # TODO: channel = self._client.get_channel(int(channel_id))
        #       await channel.send(content)
        logger.info("Discord send to %s: %s", channel_id, content[:50])
        return True
