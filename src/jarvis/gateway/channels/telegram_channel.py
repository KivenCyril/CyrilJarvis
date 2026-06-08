from __future__ import annotations

import logging
from typing import Any

from jarvis.gateway.channel import Channel, ChannelConfig, ChannelType

logger = logging.getLogger(__name__)


class TelegramChannel(Channel):
    """Telegram Bot channel adapter.

    Requires: python-telegram-bot (optional dependency).
    Uses long polling for message receipt.
    """

    def __init__(self, config: ChannelConfig | None = None):
        if config is None:
            config = ChannelConfig(name="telegram", channel_type=ChannelType.TELEGRAM)
        super().__init__(config)
        self._bot: Any = None

    def _ensure_library(self) -> None:
        try:
            import telegram  # noqa: F401
        except ImportError:
            raise ImportError(
                "python-telegram-bot is required for TelegramChannel. "
                "Install it with: pip install python-telegram-bot"
            )

    async def start(self) -> None:
        self._ensure_library()
        # TODO: Initialize telegram.Bot with self.config.api_token
        # Set up long-polling handler
        self._running = True
        logger.info("Telegram channel started")

    async def stop(self) -> None:
        self._running = False
        self._bot = None
        logger.info("Telegram channel stopped")

    async def send(self, channel_id: str, content: str, **kwargs: Any) -> bool:
        self._ensure_library()
        if self._bot is None:
            logger.error("Telegram bot is not initialized")
            return False
        # TODO: await self._bot.send_message(chat_id=channel_id, text=content)
        logger.info("Telegram send to %s: %s", channel_id, content[:50])
        return True
