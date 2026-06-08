from __future__ import annotations

import logging
from typing import Any

from jarvis.gateway.channel import Channel, ChannelConfig, ChannelType

logger = logging.getLogger(__name__)


class DingTalkChannel(Channel):
    """DingTalk (钉钉) Bot channel adapter.

    Supports both webhook push and outgoing-message modes.
    Uses the DingTalk Open Platform API for sending messages.
    """

    def __init__(self, config: ChannelConfig | None = None):
        if config is None:
            config = ChannelConfig(name="dingtalk", channel_type=ChannelType.DINGTALK)
        super().__init__(config)

    async def start(self) -> None:
        # TODO: Validate webhook_url / api_token from config
        self._running = True
        logger.info("DingTalk channel started")

    async def stop(self) -> None:
        self._running = False
        logger.info("DingTalk channel stopped")

    async def send(self, channel_id: str, content: str, **kwargs: Any) -> bool:
        """Send a message via DingTalk webhook or API.

        The default approach uses the webhook URL from config to POST
        a JSON body with ``msgtype: "text"`` and ``text: {content}``.
        """
        webhook_url = self.config.webhook_url
        if not webhook_url:
            logger.error("DingTalk webhook URL not configured")
            return False
        # TODO: POST to webhook_url with:
        # {
        #     "msgtype": "text",
        #     "text": {"content": content}
        # }
        logger.info("DingTalk send to %s: %s", channel_id, content[:50])
        return True
