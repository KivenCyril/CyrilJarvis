from __future__ import annotations

import logging
from typing import Any

from jarvis.gateway.channel import Channel, ChannelConfig, ChannelType

logger = logging.getLogger(__name__)


class CLIChannel(Channel):
    """Terminal-based channel for interactive CLI use."""

    def __init__(self, config: ChannelConfig | None = None):
        if config is None:
            config = ChannelConfig(name="cli", channel_type=ChannelType.CLI)
        super().__init__(config)

    async def start(self) -> None:
        self._running = True
        logger.info("CLI channel started")

    async def stop(self) -> None:
        self._running = False
        logger.info("CLI channel stopped")

    async def send(self, channel_id: str, content: str, **kwargs: Any) -> bool:
        print(f"[JARVIS] {content}")
        return True
