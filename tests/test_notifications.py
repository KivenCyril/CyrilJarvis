"""Tests for the JARVIS notification system."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from jarvis.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
)
from jarvis.notifications.manager import NotificationManager


# ======================================================================
# Model tests
# ======================================================================


class TestNotificationModel:
    def test_create_minimal(self):
        n = Notification(title="hello")
        assert n.title == "hello"
        assert n.body == ""
        assert n.priority == NotificationPriority.NORMAL
        assert n.status == NotificationStatus.PENDING
        assert n.channel == NotificationChannel.CONSOLE
        assert isinstance(n.id, str) and len(n.id) == 12

    def test_create_full(self):
        n = Notification(
            title="Deploy failed",
            body="Service X could not start",
            priority=NotificationPriority.URGENT,
            channel=NotificationChannel.WEBHOOK,
            source="deployer",
            category="deploy_error",
            metadata={"webhook_url": "https://hooks.example.com"},
            actions=[{"label": "View Logs", "url": "/logs/123"}],
        )
        assert n.priority == NotificationPriority.URGENT
        assert n.channel == NotificationChannel.WEBHOOK
        assert n.source == "deployer"
        assert n.metadata["webhook_url"] == "https://hooks.example.com"
        assert len(n.actions) == 1

    def test_mark_sent(self):
        n = Notification(title="test")
        assert n.sent_at is None
        n.mark_sent()
        assert n.status == NotificationStatus.SENT
        assert n.sent_at is not None

    def test_mark_read(self):
        n = Notification(title="test")
        n.mark_read()
        assert n.is_read
        assert n.read_at is not None

    def test_mark_failed(self):
        n = Notification(title="test")
        n.mark_failed("connection timeout")
        assert n.status == NotificationStatus.FAILED
        assert n.metadata["error"] == "connection timeout"

    def test_is_sent_property(self):
        n = Notification(title="t")
        assert not n.is_sent
        n.status = NotificationStatus.SENT
        assert n.is_sent
        n.status = NotificationStatus.DELIVERED
        assert n.is_sent
        n.status = NotificationStatus.READ
        assert n.is_sent

    def test_age_seconds(self):
        n = Notification(title="t")
        # Should be very small (< 1 s)
        assert n.age_seconds < 1.0

    def test_unique_ids(self):
        ids = {Notification(title="t").id for _ in range(100)}
        assert len(ids) == 100

    def test_created_at_utc(self):
        n = Notification(title="t")
        assert n.created_at.tzinfo is not None


# ======================================================================
# Manager tests
# ======================================================================


class TestNotificationManager:
    @pytest.fixture()
    def manager(self) -> NotificationManager:
        return NotificationManager()

    @pytest.mark.asyncio
    async def test_notify_console(self, manager: NotificationManager):
        n = await manager.notify("Hello", body="World", source="test")
        assert n.status == NotificationStatus.SENT
        assert n.sent_at is not None

    @pytest.mark.asyncio
    async def test_notify_log_channel(self, manager: NotificationManager):
        n = await manager.notify(
            "Log message",
            channel=NotificationChannel.LOG,
            priority=NotificationPriority.HIGH,
        )
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_get_unread(self, manager: NotificationManager):
        await manager.notify("a")
        await manager.notify("b")
        assert len(manager.get_unread()) == 2

    @pytest.mark.asyncio
    async def test_mark_read(self, manager: NotificationManager):
        n = await manager.notify("read me")
        assert manager.mark_read(n.id)
        assert len(manager.get_unread()) == 0
        assert n.status == NotificationStatus.READ

    @pytest.mark.asyncio
    async def test_mark_read_unknown_id(self, manager: NotificationManager):
        assert not manager.mark_read("nonexistent")

    @pytest.mark.asyncio
    async def test_mark_all_read(self, manager: NotificationManager):
        await manager.notify("a")
        await manager.notify("b")
        count = manager.mark_all_read()
        assert count == 2
        assert len(manager.get_unread()) == 0

    @pytest.mark.asyncio
    async def test_get_unread_by_priority(self, manager: NotificationManager):
        await manager.notify("low", priority=NotificationPriority.LOW)
        await manager.notify("high", priority=NotificationPriority.HIGH)
        high = manager.get_unread(priority=NotificationPriority.HIGH)
        assert len(high) == 1
        assert high[0].title == "high"

    @pytest.mark.asyncio
    async def test_history_default_order(self, manager: NotificationManager):
        await manager.notify("first")
        await manager.notify("second")
        history = manager.get_history()
        # Newest first
        assert history[0].title == "second"

    @pytest.mark.asyncio
    async def test_history_filter_category(self, manager: NotificationManager):
        await manager.notify("a", category="deploy")
        await manager.notify("b", category="error")
        deploy = manager.get_history(category="deploy")
        assert len(deploy) == 1

    @pytest.mark.asyncio
    async def test_history_limit(self, manager: NotificationManager):
        for i in range(10):
            await manager.notify(f"n{i}")
        assert len(manager.get_history(limit=3)) == 3

    @pytest.mark.asyncio
    async def test_get_by_id(self, manager: NotificationManager):
        n = await manager.notify("findme")
        found = manager.get_by_id(n.id)
        assert found is not None
        assert found.title == "findme"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, manager: NotificationManager):
        assert manager.get_by_id("nope") is None

    @pytest.mark.asyncio
    async def test_stats(self, manager: NotificationManager):
        await manager.notify("a", priority=NotificationPriority.LOW)
        await manager.notify("b", priority=NotificationPriority.HIGH)
        manager.mark_read(manager.get_history()[0].id)
        stats = manager.get_stats()
        assert stats["total"] == 2
        assert stats["unread"] == 1
        assert stats["by_priority"]["low"] == 1
        assert stats["by_priority"]["high"] == 1

    @pytest.mark.asyncio
    async def test_rate_limit(self):
        mgr = NotificationManager(rate_limit=3)
        results = []
        for i in range(5):
            n = await mgr.notify(f"msg{i}")
            results.append(n)
        sent = [r for r in results if r.status == NotificationStatus.SENT]
        pending = [r for r in results if r.status == NotificationStatus.PENDING]
        assert len(sent) == 3
        assert len(pending) == 2

    @pytest.mark.asyncio
    async def test_quiet_hours_suppress_normal(self):
        # Set quiet hours to current hour so it's always quiet
        current_hour = datetime.now().hour
        mgr = NotificationManager(quiet_hours=(current_hour, (current_hour + 1) % 24))
        n = await mgr.notify("normal msg", priority=NotificationPriority.NORMAL)
        assert n.status == NotificationStatus.PENDING

    @pytest.mark.asyncio
    async def test_quiet_hours_allow_urgent(self):
        current_hour = datetime.now().hour
        mgr = NotificationManager(quiet_hours=(current_hour, (current_hour + 1) % 24))
        n = await mgr.notify("urgent!", priority=NotificationPriority.URGENT)
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_quiet_hours_allow_high(self):
        current_hour = datetime.now().hour
        mgr = NotificationManager(quiet_hours=(current_hour, (current_hour + 1) % 24))
        n = await mgr.notify("high!", priority=NotificationPriority.HIGH)
        assert n.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_custom_handler(self, manager: NotificationManager):
        received: list[Notification] = []

        async def custom(n: Notification) -> None:
            received.append(n)

        manager.set_handler(NotificationChannel.EMAIL, custom)
        await manager.notify("email test", channel=NotificationChannel.EMAIL)
        assert len(received) == 1
        assert received[0].title == "email test"

    @pytest.mark.asyncio
    async def test_handler_failure(self, manager: NotificationManager):
        async def broken(n: Notification) -> None:
            raise RuntimeError("boom")

        manager.set_handler(NotificationChannel.EMAIL, broken)
        n = await manager.notify("fail", channel=NotificationChannel.EMAIL)
        assert n.status == NotificationStatus.FAILED
        assert "boom" in n.metadata.get("error", "")

    @pytest.mark.asyncio
    async def test_flush_pending(self):
        current_hour = datetime.now().hour
        mgr = NotificationManager(quiet_hours=(current_hour, (current_hour + 1) % 24))
        await mgr.notify("suppressed", priority=NotificationPriority.LOW)
        assert len(mgr.get_unread()) == 1
        # Clear quiet hours and flush
        mgr.clear_quiet_hours()
        delivered = await mgr.flush_pending()
        assert len(delivered) == 1
        assert delivered[0].status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_clear_history(self, manager: NotificationManager):
        await manager.notify("a")
        await manager.notify("b")
        count = manager.clear_history()
        assert count == 2
        assert len(manager.get_history()) == 0

    @pytest.mark.asyncio
    async def test_set_rate_limit(self, manager: NotificationManager):
        manager.set_rate_limit(1)
        await manager.notify("first")
        n2 = await manager.notify("second")
        assert n2.status == NotificationStatus.PENDING

    @pytest.mark.asyncio
    async def test_webhook_no_url_fails(self, manager: NotificationManager):
        n = await manager.notify("no url", channel=NotificationChannel.WEBHOOK)
        assert n.status == NotificationStatus.FAILED
        assert "webhook_url" in n.metadata.get("error", "")
