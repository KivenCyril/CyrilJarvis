"""Generic webhook integration for JARVIS.

Provides a flexible webhook client that supports:
- Multiple HTTP methods (POST, PUT, PATCH)
- Authentication (Bearer, Basic)
- Automatic retries with exponential backoff
- Pre-built formatters for Discord, Microsoft Teams, DingTalk, and Feishu/Lark
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WebhookConfig(BaseModel):
    """Configuration for a webhook endpoint."""

    url: str = ""
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    auth_type: str = ""  # "bearer", "basic", or "" for none
    auth_token: str = ""  # token for bearer, or "user:pass" for basic
    retry_count: int = 3
    timeout_seconds: int = 10


class WebhookClient:
    """Generic webhook client with retry and authentication support."""

    def __init__(self, config: WebhookConfig | None = None):
        self.config = config or WebhookConfig()

    # --------------------------------------------------------------------- #
    # Internal
    # --------------------------------------------------------------------- #

    def _build_headers(self, config: WebhookConfig) -> dict[str, str]:
        """Build request headers including authentication."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        headers.update(config.headers)

        if config.auth_type == "bearer" and config.auth_token:
            headers["Authorization"] = f"Bearer {config.auth_token}"
        elif config.auth_type == "basic" and config.auth_token:
            encoded = base64.b64encode(config.auth_token.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        return headers

    # --------------------------------------------------------------------- #
    # Sending
    # --------------------------------------------------------------------- #

    async def send(
        self,
        payload: dict[str, Any],
        config: WebhookConfig | None = None,
    ) -> dict[str, Any]:
        """Send a payload to the configured webhook URL.

        Retries on transient failures with exponential backoff.
        Returns ``{"status": <int>, "body": <str>, "success": <bool>}``.
        """
        import httpx

        cfg = config or self.config
        if not cfg.url:
            raise ValueError("webhook URL is not configured")

        headers = self._build_headers(cfg)
        last_error: Exception | None = None

        for attempt in range(max(cfg.retry_count, 1)):
            try:
                async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                    resp = await client.request(
                        cfg.method, cfg.url, json=payload, headers=headers
                    )
                    return {
                        "status": resp.status_code,
                        "body": resp.text,
                        "success": 200 <= resp.status_code < 300,
                    }
            except Exception as exc:
                last_error = exc
                if attempt < cfg.retry_count - 1:
                    wait = 2**attempt * 0.5  # 0.5, 1, 2, 4 ...
                    logger.warning(
                        "Webhook attempt %d failed (%s), retrying in %.1fs",
                        attempt + 1,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)

        logger.error("Webhook failed after %d attempts: %s", cfg.retry_count, last_error)
        return {
            "status": 0,
            "body": str(last_error),
            "success": False,
        }

    async def send_batch(
        self,
        payloads: list[dict[str, Any]],
        config: WebhookConfig | None = None,
    ) -> list[dict[str, Any]]:
        """Send multiple payloads concurrently.

        Returns a list of result dicts in the same order as *payloads*.
        """
        tasks = [self.send(p, config) for p in payloads]
        return list(await asyncio.gather(*tasks))

    # --------------------------------------------------------------------- #
    # Pre-built formatters
    # --------------------------------------------------------------------- #

    @staticmethod
    def format_for_discord(
        title: str,
        description: str,
        color: int = 0x3B82F6,
    ) -> dict[str, Any]:
        """Format a payload as a Discord webhook embed.

        Discord expects ``{"embeds": [...]}``.
        """
        return {
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": color,
                }
            ]
        }

    @staticmethod
    def format_for_teams(title: str, text: str) -> dict[str, Any]:
        """Format a payload as a Microsoft Teams incoming webhook card.

        Uses the legacy ``MessageCard`` format for broad compatibility.
        """
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": title,
            "themeColor": "0076D7",
            "title": title,
            "sections": [
                {
                    "activityTitle": title,
                    "text": text,
                    "markdown": True,
                }
            ],
        }

    @staticmethod
    def format_for_dingtalk(title: str, text: str) -> dict[str, Any]:
        """Format a payload as a DingTalk webhook message.

        Uses the ``markdown`` message type.
        """
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{text}",
            },
        }

    @staticmethod
    def format_for_feishu(title: str, content: str) -> dict[str, Any]:
        """Format a payload as a Feishu/Lark webhook interactive card."""
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title,
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                    }
                ],
            },
        }
