"""Notification manager — creation, routing, delivery, and history."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from jarvis.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
)

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages notification creation, routing, and delivery.

    Features:
    - Multi-channel delivery (console, webhook, desktop, log)
    - Priority-based filtering
    - Notification history with read tracking
    - Webhook integration for external services
    - Desktop notifications on macOS
    - Notification templates
    - Rate limiting (max N notifications per minute)
    - Quiet hours (suppress non-urgent during specified hours)
    """

    def __init__(
        self,
        quiet_hours: tuple[int, int] | None = None,
        rate_limit: int = 30,
    ) -> None:
        self._notifications: list[Notification] = []
        self._handlers: dict[NotificationChannel, Callable[..., Any]] = {}
        self._quiet_hours = quiet_hours  # (start_hour, end_hour) in local time
        self._rate_limit = rate_limit  # max per minute
        self._sent_timestamps: list[float] = []

        # Register default handlers
        self._handlers[NotificationChannel.CONSOLE] = self._send_console
        self._handlers[NotificationChannel.LOG] = self._send_log
        self._handlers[NotificationChannel.DESKTOP] = self._send_desktop
        self._handlers[NotificationChannel.WEBHOOK] = self._send_webhook

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def notify(
        self,
        title: str,
        body: str = "",
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channel: NotificationChannel = NotificationChannel.CONSOLE,
        source: str = "",
        category: str = "",
        actions: list[dict[str, str]] | None = None,
        **metadata: Any,
    ) -> Notification:
        """Create and send a notification.

        Returns the ``Notification`` object regardless of delivery outcome.
        If rate-limited or during quiet hours the notification stays PENDING.
        """
        notification = Notification(
            title=title,
            body=body,
            priority=priority,
            channel=channel,
            source=source,
            category=category,
            metadata=metadata,
            actions=actions or [],
        )

        # Check quiet hours (high/urgent bypass quiet hours)
        if self._is_quiet_time() and priority not in (
            NotificationPriority.HIGH,
            NotificationPriority.URGENT,
        ):
            notification.status = NotificationStatus.PENDING
            self._notifications.append(notification)
            logger.debug("Notification suppressed during quiet hours: %s", title)
            return notification

        # Check rate limit
        if not self._check_rate_limit():
            notification.status = NotificationStatus.PENDING
            self._notifications.append(notification)
            logger.debug("Notification rate-limited: %s", title)
            return notification

        # Deliver
        await self._deliver(notification)
        self._notifications.append(notification)
        return notification

    def mark_read(self, notification_id: str) -> bool:
        """Mark a notification as read. Returns True if found."""
        for n in self._notifications:
            if n.id == notification_id:
                n.mark_read()
                return True
        return False

    def mark_all_read(self) -> int:
        """Mark every unread notification as read. Returns count."""
        count = 0
        for n in self._notifications:
            if n.status != NotificationStatus.READ:
                n.mark_read()
                count += 1
        return count

    def get_unread(
        self,
        priority: NotificationPriority | None = None,
    ) -> list[Notification]:
        """Return unread notifications, optionally filtered by priority."""
        unread = [n for n in self._notifications if n.status != NotificationStatus.READ]
        if priority:
            unread = [n for n in unread if n.priority == priority]
        return unread

    def get_history(
        self,
        limit: int = 50,
        category: str | None = None,
        channel: NotificationChannel | None = None,
    ) -> list[Notification]:
        """Return notification history, newest first."""
        filtered = self._notifications
        if category:
            filtered = [n for n in filtered if n.category == category]
        if channel:
            filtered = [n for n in filtered if n.channel == channel]
        return sorted(filtered, key=lambda n: n.created_at, reverse=True)[:limit]

    def get_by_id(self, notification_id: str) -> Notification | None:
        """Look up a notification by its id."""
        for n in self._notifications:
            if n.id == notification_id:
                return n
        return None

    def get_stats(self) -> dict[str, Any]:
        """Aggregate statistics across all notifications."""
        by_status: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        by_channel: dict[str, int] = {}
        for n in self._notifications:
            by_status[n.status.value] = by_status.get(n.status.value, 0) + 1
            by_priority[n.priority.value] = by_priority.get(n.priority.value, 0) + 1
            by_channel[n.channel.value] = by_channel.get(n.channel.value, 0) + 1
        return {
            "total": len(self._notifications),
            "unread": len(self.get_unread()),
            "by_status": by_status,
            "by_priority": by_priority,
            "by_channel": by_channel,
        }

    def set_handler(
        self,
        channel: NotificationChannel,
        handler: Callable[..., Any],
    ) -> None:
        """Override or add a handler for a notification channel."""
        self._handlers[channel] = handler

    def set_rate_limit(self, limit: int) -> None:
        """Update the per-minute rate limit."""
        self._rate_limit = limit

    def set_quiet_hours(self, start: int, end: int) -> None:
        """Set quiet hours (local time, 0-23). Set to None to disable."""
        self._quiet_hours = (start, end)

    def clear_quiet_hours(self) -> None:
        """Disable quiet hours."""
        self._quiet_hours = None

    async def flush_pending(self) -> list[Notification]:
        """Attempt to deliver all PENDING notifications (e.g. after quiet hours end)."""
        pending = [
            n for n in self._notifications if n.status == NotificationStatus.PENDING
        ]
        delivered: list[Notification] = []
        for n in pending:
            if self._check_rate_limit():
                await self._deliver(n)
                if n.status == NotificationStatus.SENT:
                    delivered.append(n)
        return delivered

    def clear_history(self) -> int:
        """Remove all notifications from history. Returns count removed."""
        count = len(self._notifications)
        self._notifications.clear()
        return count

    # ------------------------------------------------------------------
    # Internal delivery
    # ------------------------------------------------------------------

    async def _deliver(self, notification: Notification) -> None:
        """Route the notification to the appropriate channel handler."""
        handler = self._handlers.get(notification.channel)
        if handler is None:
            notification.mark_failed(
                f"No handler registered for channel {notification.channel.value}"
            )
            logger.warning(
                "No handler for channel %s", notification.channel.value
            )
            return

        try:
            result = handler(notification)
            # Support both sync and async handlers
            if asyncio.iscoroutine(result):
                await result
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            notification.mark_failed(str(exc))
            logger.warning("Notification delivery failed: %s", exc)

    # ------------------------------------------------------------------
    # Built-in channel handlers
    # ------------------------------------------------------------------

    async def _send_console(self, notification: Notification) -> None:
        """Print notification to stdout."""
        icons = {
            "low": "i",
            "normal": ">>",
            "high": "!!",
            "urgent": "!!!",
        }
        icon = icons.get(notification.priority.value, ">>")
        source = f"[{notification.source}] " if notification.source else ""
        print(f"{icon} {source}{notification.title}")
        if notification.body:
            print(f"   {notification.body[:200]}")

    async def _send_log(self, notification: Notification) -> None:
        """Write notification to the Python logger."""
        level_map = {
            "low": logging.DEBUG,
            "normal": logging.INFO,
            "high": logging.WARNING,
            "urgent": logging.ERROR,
        }
        level = level_map.get(notification.priority.value, logging.INFO)
        logger.log(
            level,
            "[%s] %s: %s",
            notification.source,
            notification.title,
            notification.body[:100],
        )

    async def _send_desktop(self, notification: Notification) -> None:
        """Send a macOS desktop notification via osascript."""
        escaped_title = notification.title.replace('"', '\\"')
        escaped_body = notification.body[:100].replace('"', '\\"')
        script = (
            f'display notification "{escaped_body}" '
            f'with title "JARVIS" subtitle "{escaped_title}"'
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript",
                "-e",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except Exception:
            # Desktop notifications are best-effort
            pass

    async def _send_webhook(self, notification: Notification) -> None:
        """Send notification as a JSON POST to a webhook URL."""
        url = notification.metadata.get("webhook_url", "")
        if not url:
            raise ValueError("No webhook_url in notification metadata")

        import httpx  # lazy import — only needed for webhooks

        payload = {
            "title": notification.title,
            "body": notification.body,
            "priority": notification.priority.value,
            "source": notification.source,
            "category": notification.category,
            "timestamp": notification.created_at.isoformat(),
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            resp.raise_for_status()

    # ------------------------------------------------------------------
    # Rate-limiting & quiet hours
    # ------------------------------------------------------------------

    def _is_quiet_time(self) -> bool:
        """Check whether the current local hour falls within quiet hours."""
        if not self._quiet_hours:
            return False
        start, end = self._quiet_hours
        hour = datetime.now().hour
        if start <= end:
            return start <= hour < end
        # Wraps midnight, e.g. (22, 7) means 22-23 and 0-6
        return hour >= start or hour < end

    def _check_rate_limit(self) -> bool:
        """Return True if we are within the rate limit (and record the send)."""
        now = time.time()
        # Prune timestamps older than 60 s
        self._sent_timestamps = [
            t for t in self._sent_timestamps if now - t < 60
        ]
        if len(self._sent_timestamps) >= self._rate_limit:
            return False
        self._sent_timestamps.append(now)
        return True
