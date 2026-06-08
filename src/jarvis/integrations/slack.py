"""Slack integration for JARVIS notifications and messaging.

Supports:
- Sending messages via Bot API and incoming webhooks
- File uploads
- Channel listing and history
- Rich Block Kit formatting for Spec updates, agent results, and notifications
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SlackConfig(BaseModel):
    """Configuration for Slack integration."""

    bot_token: str = ""
    webhook_url: str = ""
    default_channel: str = "#general"


class SlackMessage(BaseModel):
    """A Slack message payload."""

    channel: str
    text: str
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    thread_ts: str = ""
    username: str = "JARVIS"
    icon_emoji: str = ":robot_face:"


class SlackClient:
    """Slack API client for JARVIS integrations.

    Uses the Slack Web API (chat.postMessage, files.upload, etc.) when a
    ``bot_token`` is configured, and falls back to an incoming webhook URL
    for simpler notification-only setups.
    """

    SLACK_API_BASE = "https://slack.com/api"

    def __init__(self, config: SlackConfig | None = None):
        self.config = config or SlackConfig()

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _bot_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _api_post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Post to a Slack Web API method."""
        import httpx

        url = f"{self.SLACK_API_BASE}/{method}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=self._bot_headers())
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Slack API error: %s", data.get("error", "unknown"))
            return data

    # --------------------------------------------------------------------- #
    # Messaging
    # --------------------------------------------------------------------- #

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str = "",
    ) -> dict[str, Any]:
        """Send a message via the Slack Bot API.

        Returns the API response dict (contains ``ts``, ``channel``, etc.).
        """
        payload: dict[str, Any] = {
            "channel": channel or self.config.default_channel,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return await self._api_post("chat.postMessage", payload)

    async def send_webhook(
        self,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send a message via an incoming webhook URL.

        Returns ``True`` on success.
        """
        import httpx

        if not self.config.webhook_url:
            raise ValueError("webhook_url is not configured")
        payload: dict[str, Any] = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self.config.webhook_url, json=payload)
            resp.raise_for_status()
            return True

    async def upload_file(
        self,
        channel: str,
        content: str,
        filename: str,
        title: str = "",
    ) -> dict[str, Any]:
        """Upload a text file to a Slack channel.

        Returns the API response dict.
        """
        import httpx

        url = f"{self.SLACK_API_BASE}/files.upload"
        payload = {
            "channels": channel or self.config.default_channel,
            "content": content,
            "filename": filename,
            "title": title or filename,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                data=payload,
                headers={"Authorization": f"Bearer {self.config.bot_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    # --------------------------------------------------------------------- #
    # Channels
    # --------------------------------------------------------------------- #

    async def list_channels(self, limit: int = 100) -> list[dict[str, Any]]:
        """List public channels the bot has access to."""
        data = await self._api_post(
            "conversations.list",
            {"limit": limit, "types": "public_channel"},
        )
        channels = data.get("channels", [])
        return [
            {
                "id": ch.get("id", ""),
                "name": ch.get("name", ""),
                "topic": ch.get("topic", {}).get("value", ""),
                "num_members": ch.get("num_members", 0),
            }
            for ch in channels
        ]

    async def get_channel_history(
        self, channel: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Retrieve recent messages from a channel."""
        data = await self._api_post(
            "conversations.history",
            {"channel": channel, "limit": limit},
        )
        messages = data.get("messages", [])
        return [
            {
                "ts": msg.get("ts", ""),
                "user": msg.get("user", ""),
                "text": msg.get("text", ""),
                "type": msg.get("type", "message"),
            }
            for msg in messages
        ]

    # --------------------------------------------------------------------- #
    # Rich Block Formatting
    # --------------------------------------------------------------------- #

    @staticmethod
    def format_spec_update(spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Format a Streaming Spec update as Slack Block Kit blocks.

        Expects ``spec`` to have keys like ``id``, ``title``, ``status``,
        ``steps`` (list of dicts with ``name`` and ``status``).
        """
        title = spec.get("title", "Spec Update")
        status = spec.get("status", "unknown")
        spec_id = spec.get("id", "")

        status_emoji = {
            "running": ":arrow_forward:",
            "completed": ":white_check_mark:",
            "failed": ":x:",
            "pending": ":hourglass:",
        }.get(status, ":grey_question:")

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Spec: {title}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Status:* {status_emoji} {status}"},
                    {"type": "mrkdwn", "text": f"*ID:* `{spec_id}`"},
                ],
            },
        ]

        steps = spec.get("steps", [])
        if steps:
            step_lines: list[str] = []
            for step in steps:
                s_name = step.get("name", "unnamed")
                s_status = step.get("status", "pending")
                s_emoji = {
                    "running": ":arrow_forward:",
                    "completed": ":white_check_mark:",
                    "failed": ":x:",
                    "pending": ":hourglass:",
                }.get(s_status, ":grey_question:")
                step_lines.append(f"{s_emoji} {s_name}")
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Steps:*\n" + "\n".join(step_lines),
                    },
                }
            )

        return blocks

    @staticmethod
    def format_agent_result(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Format an agent execution result as Slack blocks.

        Expects ``result`` to have keys like ``agent``, ``status``,
        ``output``, ``duration_seconds``.
        """
        agent = result.get("agent", "unknown")
        status = result.get("status", "unknown")
        output = result.get("output", "")
        duration = result.get("duration_seconds", 0)

        status_emoji = ":white_check_mark:" if status == "success" else ":x:"

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Agent Result: {agent}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Status:* {status_emoji} {status}"},
                    {"type": "mrkdwn", "text": f"*Duration:* {duration:.1f}s"},
                ],
            },
        ]

        if output:
            # Truncate long output
            truncated = output[:2000] + ("..." if len(output) > 2000 else "")
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"```{truncated}```"},
                }
            )

        return blocks

    @staticmethod
    def format_notification(notification: dict[str, Any]) -> list[dict[str, Any]]:
        """Format a generic notification as Slack blocks.

        Expects ``notification`` to have keys like ``title``, ``message``,
        ``level`` (info/warning/error), and optionally ``url``.
        """
        title = notification.get("title", "Notification")
        message = notification.get("message", "")
        level = notification.get("level", "info")
        url = notification.get("url", "")

        level_emoji = {
            "info": ":information_source:",
            "warning": ":warning:",
            "error": ":rotating_light:",
            "success": ":tada:",
        }.get(level, ":bell:")

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{title}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{level_emoji} *[{level.upper()}]* {message}",
                },
            },
        ]

        if url:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"<{url}|View Details>"},
                }
            )

        return blocks
