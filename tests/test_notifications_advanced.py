"""Advanced tests for the JARVIS notification subsystem.

Covers multi-channel delivery, quiet hours enforcement, rate limiting
under load, priority filtering, mark-read workflow, stats accuracy,
custom handler registration, flush pending after quiet hours,
notification with actions, history filtering by category,
desktop notification mocking, and webhook notification mocking.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.notifications.manager import NotificationManager
from jarvis.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
)


# ===========================================================================
# 1. Multi-channel delivery
# ===========================================================================


class TestMultiChannelDelivery:
    @pytest.mark.asyncio
    async def test_console_delivery(self, capsys):
        mgr = NotificationManager()
        n = await mgr.notify("Test", "Body", channel=NotificationChannel.CONSOLE)
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_log_delivery(self):
        mgr = NotificationManager()
        n = await mgr.notify("LogTest", "Body", channel=NotificationChannel.LOG)
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_different_channels_independent(self, capsys):
        mgr = NotificationManager()
        n1 = await mgr.notify("C1", channel=NotificationChannel.CONSOLE)
        n2 = await mgr.notify("L1", channel=NotificationChannel.LOG)
        assert n1.status == NotificationStatus.SENT
        assert n2.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_unregistered_channel_fails(self):
        mgr = NotificationManager()
        # Remove the EMAIL handler (not registered by default)
        n = await mgr.notify("X", channel=NotificationChannel.EMAIL)
        assert n.status == NotificationStatus.FAILED


# ===========================================================================
# 2. Quiet hours enforcement
# ===========================================================================


class TestQuietHours:
    @pytest.mark.asyncio
    async def test_quiet_hours_suppress_normal(self):
        mgr = NotificationManager()
        current_hour = datetime.now().hour
        # Set quiet hours to include the current hour
        mgr.set_quiet_hours(current_hour, (current_hour + 2) % 24)
        n = await mgr.notify(
            "Suppressed",
            priority=NotificationPriority.NORMAL,
            channel=NotificationChannel.LOG,
        )
        assert n.status == NotificationStatus.PENDING

    @pytest.mark.asyncio
    async def test_quiet_hours_allow_urgent(self):
        mgr = NotificationManager()
        current_hour = datetime.now().hour
        mgr.set_quiet_hours(current_hour, (current_hour + 2) % 24)
        n = await mgr.notify(
            "Urgent",
            priority=NotificationPriority.URGENT,
            channel=NotificationChannel.LOG,
        )
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_quiet_hours_allow_high(self):
        mgr = NotificationManager()
        current_hour = datetime.now().hour
        mgr.set_quiet_hours(current_hour, (current_hour + 2) % 24)
        n = await mgr.notify(
            "High",
            priority=NotificationPriority.HIGH,
            channel=NotificationChannel.LOG,
        )
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_outside_quiet_hours_delivers(self):
        mgr = NotificationManager()
        current_hour = datetime.now().hour
        # Set quiet hours to a different time
        far_hour = (current_hour + 12) % 24
        mgr.set_quiet_hours(far_hour, (far_hour + 1) % 24)
        n = await mgr.notify(
            "Normal",
            priority=NotificationPriority.NORMAL,
            channel=NotificationChannel.LOG,
        )
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_clear_quiet_hours(self):
        mgr = NotificationManager()
        current_hour = datetime.now().hour
        mgr.set_quiet_hours(current_hour, (current_hour + 2) % 24)
        mgr.clear_quiet_hours()
        n = await mgr.notify(
            "After clear",
            priority=NotificationPriority.LOW,
            channel=NotificationChannel.LOG,
        )
        assert n.status == NotificationStatus.SENT

    def test_quiet_hours_wrapping_midnight(self):
        mgr = NotificationManager(quiet_hours=(22, 7))
        # Directly test the internal method
        with patch("jarvis.notifications.manager.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 23
            mock_dt.now.return_value = mock_now
            # manual check: hour 23 >= 22, so it's quiet
            assert mgr._is_quiet_time() is True


# ===========================================================================
# 3. Rate limiting under load
# ===========================================================================


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self):
        mgr = NotificationManager(rate_limit=5)
        results = []
        for i in range(10):
            n = await mgr.notify(
                f"N{i}",
                channel=NotificationChannel.LOG,
            )
            results.append(n.status)

        sent_count = results.count(NotificationStatus.SENT)
        pending_count = results.count(NotificationStatus.PENDING)
        assert sent_count == 5
        assert pending_count == 5

    @pytest.mark.asyncio
    async def test_rate_limit_update(self):
        mgr = NotificationManager(rate_limit=2)
        await mgr.notify("A", channel=NotificationChannel.LOG)
        await mgr.notify("B", channel=NotificationChannel.LOG)
        n = await mgr.notify("C", channel=NotificationChannel.LOG)
        assert n.status == NotificationStatus.PENDING

        # Increase limit
        mgr.set_rate_limit(100)
        n2 = await mgr.notify("D", channel=NotificationChannel.LOG)
        assert n2.status == NotificationStatus.SENT


# ===========================================================================
# 4. Notification priority filtering
# ===========================================================================


class TestPriorityFiltering:
    @pytest.mark.asyncio
    async def test_get_unread_by_priority(self):
        mgr = NotificationManager()
        await mgr.notify("Low", priority=NotificationPriority.LOW, channel=NotificationChannel.LOG)
        await mgr.notify("High", priority=NotificationPriority.HIGH, channel=NotificationChannel.LOG)
        await mgr.notify("Normal", priority=NotificationPriority.NORMAL, channel=NotificationChannel.LOG)

        high_only = mgr.get_unread(priority=NotificationPriority.HIGH)
        assert len(high_only) == 1
        assert high_only[0].title == "High"

    @pytest.mark.asyncio
    async def test_get_unread_all(self):
        mgr = NotificationManager()
        await mgr.notify("A", channel=NotificationChannel.LOG)
        await mgr.notify("B", channel=NotificationChannel.LOG)
        assert len(mgr.get_unread()) == 2


# ===========================================================================
# 5. Mark read workflow
# ===========================================================================


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_mark_single_read(self):
        mgr = NotificationManager()
        n = await mgr.notify("Test", channel=NotificationChannel.LOG)
        assert mgr.mark_read(n.id) is True
        assert n.status == NotificationStatus.READ
        assert n.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_nonexistent_read(self):
        mgr = NotificationManager()
        assert mgr.mark_read("ghost") is False

    @pytest.mark.asyncio
    async def test_mark_all_read(self):
        mgr = NotificationManager()
        await mgr.notify("A", channel=NotificationChannel.LOG)
        await mgr.notify("B", channel=NotificationChannel.LOG)
        count = mgr.mark_all_read()
        assert count == 2
        assert len(mgr.get_unread()) == 0

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        mgr = NotificationManager()
        n = await mgr.notify("Find me", channel=NotificationChannel.LOG)
        found = mgr.get_by_id(n.id)
        assert found is not None
        assert found.title == "Find me"
        assert mgr.get_by_id("nope") is None


# ===========================================================================
# 6. Stats accuracy
# ===========================================================================


class TestStats:
    @pytest.mark.asyncio
    async def test_stats_counts(self):
        mgr = NotificationManager()
        await mgr.notify("A", priority=NotificationPriority.LOW, channel=NotificationChannel.LOG)
        await mgr.notify("B", priority=NotificationPriority.HIGH, channel=NotificationChannel.CONSOLE)
        n = await mgr.notify("C", channel=NotificationChannel.LOG)
        mgr.mark_read(n.id)

        stats = mgr.get_stats()
        assert stats["total"] == 3
        assert stats["by_priority"]["low"] == 1
        assert stats["by_priority"]["high"] == 1
        assert stats["by_channel"]["log"] == 2
        assert stats["by_channel"]["console"] == 1
        assert stats["unread"] == 2

    @pytest.mark.asyncio
    async def test_clear_history(self):
        mgr = NotificationManager()
        await mgr.notify("A", channel=NotificationChannel.LOG)
        await mgr.notify("B", channel=NotificationChannel.LOG)
        removed = mgr.clear_history()
        assert removed == 2
        assert mgr.get_stats()["total"] == 0


# ===========================================================================
# 7. Custom handler registration
# ===========================================================================


class TestCustomHandler:
    @pytest.mark.asyncio
    async def test_custom_sync_handler(self):
        mgr = NotificationManager()
        received = []

        def my_handler(n: Notification) -> None:
            received.append(n.title)

        mgr.set_handler(NotificationChannel.CONSOLE, my_handler)
        await mgr.notify("Custom", channel=NotificationChannel.CONSOLE)
        assert "Custom" in received

    @pytest.mark.asyncio
    async def test_custom_async_handler(self):
        mgr = NotificationManager()
        received = []

        async def my_handler(n: Notification) -> None:
            received.append(n.title)

        mgr.set_handler(NotificationChannel.LOG, my_handler)
        await mgr.notify("AsyncCustom", channel=NotificationChannel.LOG)
        assert "AsyncCustom" in received

    @pytest.mark.asyncio
    async def test_handler_exception_marks_failed(self):
        mgr = NotificationManager()

        def bad_handler(n: Notification) -> None:
            raise RuntimeError("handler crash")

        mgr.set_handler(NotificationChannel.CONSOLE, bad_handler)
        n = await mgr.notify("Fail", channel=NotificationChannel.CONSOLE)
        assert n.status == NotificationStatus.FAILED
        assert "handler crash" in n.metadata.get("error", "")


# ===========================================================================
# 8. Flush pending after quiet hours
# ===========================================================================


class TestFlushPending:
    @pytest.mark.asyncio
    async def test_flush_delivers_pending(self):
        mgr = NotificationManager(rate_limit=2)
        # Send 3 -- third will be pending
        await mgr.notify("A", channel=NotificationChannel.LOG)
        await mgr.notify("B", channel=NotificationChannel.LOG)
        n3 = await mgr.notify("C", channel=NotificationChannel.LOG)
        assert n3.status == NotificationStatus.PENDING

        # Increase rate limit and flush
        mgr.set_rate_limit(100)
        delivered = await mgr.flush_pending()
        assert len(delivered) == 1
        assert delivered[0].title == "C"
        assert delivered[0].status == NotificationStatus.SENT


# ===========================================================================
# 9. Notification with actions
# ===========================================================================


class TestNotificationActions:
    @pytest.mark.asyncio
    async def test_notification_with_actions(self):
        mgr = NotificationManager()
        actions = [
            {"label": "View", "url": "/specs/123"},
            {"label": "Dismiss", "action": "dismiss"},
        ]
        n = await mgr.notify(
            "ActionTest",
            channel=NotificationChannel.LOG,
            actions=actions,
        )
        assert len(n.actions) == 2
        assert n.actions[0]["label"] == "View"


# ===========================================================================
# 10. History filtering by category
# ===========================================================================


class TestHistoryFiltering:
    @pytest.mark.asyncio
    async def test_filter_by_category(self):
        mgr = NotificationManager()
        await mgr.notify("A", category="alert", channel=NotificationChannel.LOG)
        await mgr.notify("B", category="info", channel=NotificationChannel.LOG)
        await mgr.notify("C", category="alert", channel=NotificationChannel.LOG)

        alerts = mgr.get_history(category="alert")
        assert len(alerts) == 2
        assert all(n.category == "alert" for n in alerts)

    @pytest.mark.asyncio
    async def test_filter_by_channel(self):
        mgr = NotificationManager()
        await mgr.notify("A", channel=NotificationChannel.LOG)
        await mgr.notify("B", channel=NotificationChannel.CONSOLE)

        log_only = mgr.get_history(channel=NotificationChannel.LOG)
        assert len(log_only) == 1

    @pytest.mark.asyncio
    async def test_history_limit(self):
        mgr = NotificationManager()
        for i in range(20):
            await mgr.notify(f"N{i}", channel=NotificationChannel.LOG)
        history = mgr.get_history(limit=5)
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_history_newest_first(self):
        mgr = NotificationManager()
        await mgr.notify("Old", channel=NotificationChannel.LOG)
        await mgr.notify("New", channel=NotificationChannel.LOG)
        history = mgr.get_history()
        assert history[0].created_at >= history[-1].created_at


# ===========================================================================
# 11. Desktop notification (mock osascript)
# ===========================================================================


class TestDesktopNotification:
    @pytest.mark.asyncio
    async def test_desktop_calls_osascript(self):
        mgr = NotificationManager()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            process = AsyncMock()
            process.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.return_value = process

            n = await mgr.notify(
                "Desktop Test",
                "Some body text",
                channel=NotificationChannel.DESKTOP,
            )
            assert n.status == NotificationStatus.SENT
            mock_proc.assert_awaited_once()
            args = mock_proc.call_args[0]
            assert args[0] == "osascript"


# ===========================================================================
# 12. Webhook notification (mock httpx)
# ===========================================================================


class TestWebhookNotification:
    @pytest.mark.asyncio
    async def test_webhook_sends_post(self):
        mgr = NotificationManager()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("sys.modules", {"httpx": MagicMock()}) as _, patch("httpx.AsyncClient", return_value=mock_client) as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            n = await mgr.notify(
                "Webhook Test",
                channel=NotificationChannel.WEBHOOK,
                webhook_url="https://example.com/hook",
            )
            assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_webhook_no_url_fails(self):
        mgr = NotificationManager()
        n = await mgr.notify(
            "No URL",
            channel=NotificationChannel.WEBHOOK,
        )
        assert n.status == NotificationStatus.FAILED


# ===========================================================================
# 13. Notification model
# ===========================================================================


class TestNotificationModel:
    def test_model_defaults(self):
        n = Notification(title="Test")
        assert n.status == NotificationStatus.PENDING
        assert n.priority == NotificationPriority.NORMAL
        assert n.channel == NotificationChannel.CONSOLE
        assert n.id

    def test_mark_sent(self):
        n = Notification(title="T")
        n.mark_sent()
        assert n.is_sent
        assert n.sent_at is not None

    def test_mark_read(self):
        n = Notification(title="T")
        n.mark_read()
        assert n.is_read
        assert n.read_at is not None

    def test_mark_failed(self):
        n = Notification(title="T")
        n.mark_failed("oops")
        assert n.status == NotificationStatus.FAILED
        assert n.metadata["error"] == "oops"

    def test_age_seconds(self):
        n = Notification(title="T")
        assert n.age_seconds >= 0

    def test_serialization_roundtrip(self):
        n = Notification(
            title="Test",
            body="Body",
            priority=NotificationPriority.HIGH,
            source="test-module",
            category="alert",
            actions=[{"label": "View"}],
        )
        data = n.model_dump(mode="json")
        n2 = Notification.model_validate(data)
        assert n2.title == "Test"
        assert n2.priority == NotificationPriority.HIGH
        assert n2.actions[0]["label"] == "View"
