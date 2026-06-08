"""Notification data models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationPriority(str, Enum):
    """Priority levels for notifications."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(str, Enum):
    """Lifecycle status of a notification."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class NotificationChannel(str, Enum):
    """Delivery channels for notifications."""

    CONSOLE = "console"
    WEBHOOK = "webhook"
    EMAIL = "email"
    DESKTOP = "desktop"  # macOS notification
    LOG = "log"


class Notification(BaseModel):
    """A single notification with metadata and delivery tracking."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    body: str = ""
    priority: NotificationPriority = NotificationPriority.NORMAL
    status: NotificationStatus = NotificationStatus.PENDING
    channel: NotificationChannel = NotificationChannel.CONSOLE
    source: str = ""  # which module/agent generated this
    category: str = ""  # spec_completed, agent_error, skill_evolved, etc.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None
    read_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, str]] = Field(default_factory=list)
    # e.g. [{"label": "View", "url": "/specs/123"}]

    def mark_sent(self) -> None:
        """Mark the notification as sent."""
        self.status = NotificationStatus.SENT
        self.sent_at = datetime.now(timezone.utc)

    def mark_read(self) -> None:
        """Mark the notification as read."""
        self.status = NotificationStatus.READ
        self.read_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str = "") -> None:
        """Mark the notification as failed."""
        self.status = NotificationStatus.FAILED
        if error:
            self.metadata["error"] = error

    @property
    def is_read(self) -> bool:
        return self.status == NotificationStatus.READ

    @property
    def is_sent(self) -> bool:
        return self.status in (
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
            NotificationStatus.READ,
        )

    @property
    def age_seconds(self) -> float:
        """Seconds since this notification was created."""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()
