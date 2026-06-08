"""Notification system tests.

Tests notification creation, delivery, filtering, read/unread tracking,
channel routing, and batch operations.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Notification Models
# ---------------------------------------------------------------------------

@dataclass
class Notification:
    id: str
    title: str
    body: str = ""
    level: str = "info"  # info, warning, error, critical
    target: str = "all"  # all, user:{id}, role:{role}
    channel: str = "in_app"  # in_app, email, slack, webhook
    action_url: str | None = None
    read: bool = False
    created_at: str = ""
    read_at: str | None = None
    expires_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()

    def mark_read(self) -> None:
        self.read = True
        self.read_at = datetime.datetime.utcnow().isoformat()

    def mark_unread(self) -> None:
        self.read = False
        self.read_at = None

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.datetime.fromisoformat(self.expires_at) < datetime.datetime.utcnow()

    @property
    def age_seconds(self) -> float:
        created = datetime.datetime.fromisoformat(self.created_at)
        return (datetime.datetime.utcnow() - created).total_seconds()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "level": self.level,
            "target": self.target,
            "channel": self.channel,
            "action_url": self.action_url,
            "read": self.read,
            "created_at": self.created_at,
            "read_at": self.read_at,
        }


class NotificationManager:
    """Manage notifications lifecycle."""

    def __init__(self):
        self.notifications: list[Notification] = []
        self._counter = 0

    def create(self, title: str, body: str = "", level: str = "info",
               target: str = "all", channel: str = "in_app",
               action_url: str | None = None) -> Notification:
        self._counter += 1
        notif = Notification(
            id=f"notif-{self._counter:04d}",
            title=title,
            body=body,
            level=level,
            target=target,
            channel=channel,
            action_url=action_url,
        )
        self.notifications.append(notif)
        return notif

    def get(self, notif_id: str) -> Notification | None:
        return next((n for n in self.notifications if n.id == notif_id), None)

    def list(self, level: str | None = None, read: bool | None = None,
             channel: str | None = None, limit: int = 50) -> list[Notification]:
        result = list(self.notifications)
        if level:
            result = [n for n in result if n.level == level]
        if read is not None:
            result = [n for n in result if n.read == read]
        if channel:
            result = [n for n in result if n.channel == channel]
        return result[-limit:]

    def mark_read(self, notif_id: str) -> bool:
        notif = self.get(notif_id)
        if notif:
            notif.mark_read()
            return True
        return False

    def mark_all_read(self) -> int:
        count = 0
        for notif in self.notifications:
            if not notif.read:
                notif.mark_read()
                count += 1
        return count

    def delete(self, notif_id: str) -> bool:
        before = len(self.notifications)
        self.notifications = [n for n in self.notifications if n.id != notif_id]
        return len(self.notifications) < before

    def clear_read(self) -> int:
        before = len(self.notifications)
        self.notifications = [n for n in self.notifications if not n.read]
        return before - len(self.notifications)

    @property
    def unread_count(self) -> int:
        return sum(1 for n in self.notifications if not n.read)

    @property
    def stats(self) -> dict[str, Any]:
        levels = {}
        for n in self.notifications:
            levels[n.level] = levels.get(n.level, 0) + 1
        return {
            "total": len(self.notifications),
            "unread": self.unread_count,
            "by_level": levels,
            "channels": list(set(n.channel for n in self.notifications)),
        }


# ---------------------------------------------------------------------------
# Tests: Notification
# ---------------------------------------------------------------------------

class TestNotification:
    def test_create(self):
        n = Notification(id="n1", title="Test")
        assert n.title == "Test"
        assert n.level == "info"
        assert n.read is False
        assert n.created_at != ""

    def test_mark_read(self):
        n = Notification(id="n1", title="Test")
        n.mark_read()
        assert n.read is True
        assert n.read_at is not None

    def test_mark_unread(self):
        n = Notification(id="n1", title="Test")
        n.mark_read()
        n.mark_unread()
        assert n.read is False
        assert n.read_at is None

    def test_with_body(self):
        n = Notification(id="n1", title="Alert", body="Something happened")
        assert n.body == "Something happened"

    def test_with_action_url(self):
        n = Notification(id="n1", title="Click", action_url="http://example.com")
        assert n.action_url == "http://example.com"

    def test_levels(self):
        for level in ["info", "warning", "error", "critical"]:
            n = Notification(id="n1", title="Test", level=level)
            assert n.level == level

    def test_channels(self):
        for ch in ["in_app", "email", "slack", "webhook"]:
            n = Notification(id="n1", title="Test", channel=ch)
            assert n.channel == ch

    def test_to_dict(self):
        n = Notification(id="n1", title="Test", body="Body")
        d = n.to_dict()
        assert d["id"] == "n1"
        assert d["title"] == "Test"
        assert d["body"] == "Body"
        assert d["read"] is False

    def test_age(self):
        n = Notification(id="n1", title="Test")
        assert n.age_seconds >= 0

    def test_not_expired(self):
        future = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat()
        n = Notification(id="n1", title="Test", expires_at=future)
        assert n.is_expired is False

    def test_expired(self):
        past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
        n = Notification(id="n1", title="Test", expires_at=past)
        assert n.is_expired is True

    def test_no_expiry(self):
        n = Notification(id="n1", title="Test")
        assert n.is_expired is False

    def test_target_all(self):
        n = Notification(id="n1", title="Test", target="all")
        assert n.target == "all"

    def test_target_user(self):
        n = Notification(id="n1", title="Test", target="user:admin")
        assert n.target == "user:admin"

    def test_metadata(self):
        n = Notification(id="n1", title="Test", metadata={"source": "ci"})
        assert n.metadata["source"] == "ci"


# ---------------------------------------------------------------------------
# Tests: NotificationManager
# ---------------------------------------------------------------------------

class TestNotificationManager:
    def test_create_notification(self):
        mgr = NotificationManager()
        n = mgr.create("Hello")
        assert n.id == "notif-0001"
        assert n.title == "Hello"
        assert len(mgr.notifications) == 1

    def test_create_multiple(self):
        mgr = NotificationManager()
        mgr.create("First")
        mgr.create("Second")
        mgr.create("Third")
        assert len(mgr.notifications) == 3

    def test_create_with_options(self):
        mgr = NotificationManager()
        n = mgr.create("Alert", body="Details", level="error", channel="email")
        assert n.body == "Details"
        assert n.level == "error"
        assert n.channel == "email"

    def test_get_notification(self):
        mgr = NotificationManager()
        n = mgr.create("Test")
        found = mgr.get(n.id)
        assert found is not None
        assert found.title == "Test"

    def test_get_nonexistent(self):
        mgr = NotificationManager()
        assert mgr.get("fake-id") is None

    def test_list_all(self):
        mgr = NotificationManager()
        mgr.create("A")
        mgr.create("B")
        assert len(mgr.list()) == 2

    def test_list_by_level(self):
        mgr = NotificationManager()
        mgr.create("Info", level="info")
        mgr.create("Error", level="error")
        mgr.create("Warning", level="warning")
        errors = mgr.list(level="error")
        assert len(errors) == 1
        assert errors[0].title == "Error"

    def test_list_by_read_status(self):
        mgr = NotificationManager()
        n1 = mgr.create("Read")
        n2 = mgr.create("Unread")
        n1.mark_read()
        unread = mgr.list(read=False)
        assert len(unread) == 1
        assert unread[0].title == "Unread"

    def test_list_by_channel(self):
        mgr = NotificationManager()
        mgr.create("App", channel="in_app")
        mgr.create("Email", channel="email")
        app_notifs = mgr.list(channel="in_app")
        assert len(app_notifs) == 1

    def test_list_with_limit(self):
        mgr = NotificationManager()
        for i in range(20):
            mgr.create(f"Notification {i}")
        limited = mgr.list(limit=5)
        assert len(limited) == 5

    def test_mark_read(self):
        mgr = NotificationManager()
        n = mgr.create("Test")
        assert mgr.mark_read(n.id) is True
        assert n.read is True

    def test_mark_read_nonexistent(self):
        mgr = NotificationManager()
        assert mgr.mark_read("fake") is False

    def test_mark_all_read(self):
        mgr = NotificationManager()
        mgr.create("A")
        mgr.create("B")
        mgr.create("C")
        count = mgr.mark_all_read()
        assert count == 3
        assert mgr.unread_count == 0

    def test_mark_all_read_idempotent(self):
        mgr = NotificationManager()
        mgr.create("A")
        mgr.mark_all_read()
        count = mgr.mark_all_read()
        assert count == 0

    def test_delete(self):
        mgr = NotificationManager()
        n = mgr.create("Delete me")
        assert mgr.delete(n.id) is True
        assert len(mgr.notifications) == 0

    def test_delete_nonexistent(self):
        mgr = NotificationManager()
        assert mgr.delete("fake") is False

    def test_clear_read(self):
        mgr = NotificationManager()
        n1 = mgr.create("Read")
        n2 = mgr.create("Unread")
        n1.mark_read()
        cleared = mgr.clear_read()
        assert cleared == 1
        assert len(mgr.notifications) == 1
        assert mgr.notifications[0].title == "Unread"

    def test_unread_count(self):
        mgr = NotificationManager()
        mgr.create("A")
        mgr.create("B")
        mgr.create("C")
        assert mgr.unread_count == 3
        mgr.notifications[0].mark_read()
        assert mgr.unread_count == 2

    def test_stats(self):
        mgr = NotificationManager()
        mgr.create("Info 1", level="info")
        mgr.create("Info 2", level="info")
        mgr.create("Error", level="error")
        mgr.create("Email", level="info", channel="email")
        stats = mgr.stats
        assert stats["total"] == 4
        assert stats["unread"] == 4
        assert stats["by_level"]["info"] == 3
        assert stats["by_level"]["error"] == 1
        assert "in_app" in stats["channels"]
        assert "email" in stats["channels"]


# ---------------------------------------------------------------------------
# Tests: Batch Operations
# ---------------------------------------------------------------------------

class TestNotificationBatchOps:
    def test_batch_create(self):
        mgr = NotificationManager()
        titles = [f"Notification {i}" for i in range(50)]
        for title in titles:
            mgr.create(title)
        assert len(mgr.notifications) == 50

    def test_batch_read(self):
        mgr = NotificationManager()
        for i in range(10):
            mgr.create(f"N{i}")
        mgr.mark_all_read()
        assert mgr.unread_count == 0
        assert all(n.read for n in mgr.notifications)

    def test_batch_filter_and_delete(self):
        mgr = NotificationManager()
        for i in range(5):
            mgr.create(f"Info {i}", level="info")
        for i in range(3):
            mgr.create(f"Error {i}", level="error")

        # Mark info as read and clear
        for n in mgr.list(level="info"):
            n.mark_read()
        cleared = mgr.clear_read()
        assert cleared == 5
        assert len(mgr.notifications) == 3
        assert all(n.level == "error" for n in mgr.notifications)

    def test_notification_ordering(self):
        mgr = NotificationManager()
        mgr.create("First")
        mgr.create("Second")
        mgr.create("Third")
        notifs = mgr.list()
        assert notifs[-1].title == "Third"
        assert notifs[0].title == "First"


# ---------------------------------------------------------------------------
# Tests: Serialization
# ---------------------------------------------------------------------------

class TestNotificationSerialization:
    def test_serialize_list(self):
        mgr = NotificationManager()
        mgr.create("A", body="Body A")
        mgr.create("B", level="error")
        serialized = json.dumps([n.to_dict() for n in mgr.notifications])
        restored = json.loads(serialized)
        assert len(restored) == 2
        assert restored[0]["title"] == "A"
        assert restored[1]["level"] == "error"

    def test_serialize_with_read_status(self):
        n = Notification(id="n1", title="Test")
        n.mark_read()
        d = n.to_dict()
        assert d["read"] is True
        assert d["read_at"] is not None
