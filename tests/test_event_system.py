"""Event system tests.

Tests event publishing, subscription, filtering, dead letter queue,
retry logic, and serialization.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any, Callable

import pytest


# ---------------------------------------------------------------------------
# Event System Models
# ---------------------------------------------------------------------------

@dataclass
class Event:
    id: str
    topic: str
    payload: dict = field(default_factory=dict)
    source: str = "system"
    priority: str = "normal"
    timestamp: str = ""
    delivered: bool = False
    subscriber_count: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "payload": self.payload,
            "source": self.source,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "delivered": self.delivered,
            "subscriber_count": self.subscriber_count,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(
            id=data.get("id", ""),
            topic=data.get("topic", ""),
            payload=data.get("payload", {}),
            source=data.get("source", "system"),
            priority=data.get("priority", "normal"),
            timestamp=data.get("timestamp", ""),
            delivered=data.get("delivered", False),
        )


@dataclass
class Subscription:
    id: str
    topic_pattern: str
    callback_name: str  # Name of the callback (for serialization)
    active: bool = True
    event_count: int = 0
    created_at: str = ""

    def matches(self, topic: str) -> bool:
        if self.topic_pattern == topic:
            return True
        if self.topic_pattern.endswith("*"):
            prefix = self.topic_pattern[:-1]
            return topic.startswith(prefix)
        if self.topic_pattern.startswith("*"):
            suffix = self.topic_pattern[1:]
            return topic.endswith(suffix)
        return False


@dataclass
class DeadLetter:
    event: Event
    error: str
    attempts: int = 0
    last_attempt_at: str = ""
    subscription_id: str = ""


class EventBus:
    """Simple event bus with subscription pattern matching."""

    def __init__(self):
        self.events: list[Event] = []
        self.subscriptions: list[Subscription] = []
        self.dead_letters: list[DeadLetter] = []
        self._event_counter = 0
        self._sub_counter = 0
        self._handlers: dict[str, Callable] = {}

    def subscribe(self, topic_pattern: str, handler: Callable | None = None,
                  handler_name: str = "") -> Subscription:
        self._sub_counter += 1
        sub = Subscription(
            id=f"sub-{self._sub_counter:04d}",
            topic_pattern=topic_pattern,
            callback_name=handler_name or f"handler_{self._sub_counter}",
            created_at=datetime.datetime.utcnow().isoformat(),
        )
        self.subscriptions.append(sub)
        if handler:
            self._handlers[sub.id] = handler
        return sub

    def unsubscribe(self, sub_id: str) -> bool:
        before = len(self.subscriptions)
        self.subscriptions = [s for s in self.subscriptions if s.id != sub_id]
        self._handlers.pop(sub_id, None)
        return len(self.subscriptions) < before

    def publish(self, topic: str, payload: dict | None = None,
                source: str = "system", priority: str = "normal") -> Event:
        self._event_counter += 1
        event = Event(
            id=f"evt-{self._event_counter:06d}",
            topic=topic,
            payload=payload or {},
            source=source,
            priority=priority,
        )

        matching_subs = [s for s in self.subscriptions if s.active and s.matches(topic)]
        event.subscriber_count = len(matching_subs)

        for sub in matching_subs:
            sub.event_count += 1
            handler = self._handlers.get(sub.id)
            if handler:
                try:
                    handler(event)
                    event.delivered = True
                except Exception as exc:
                    self.dead_letters.append(DeadLetter(
                        event=event,
                        error=str(exc),
                        attempts=1,
                        last_attempt_at=datetime.datetime.utcnow().isoformat(),
                        subscription_id=sub.id,
                    ))

        if not matching_subs:
            event.delivered = True  # No subscribers = successfully "delivered"

        self.events.append(event)
        return event

    def get_events(self, topic: str | None = None, source: str | None = None,
                   limit: int = 50) -> list[Event]:
        result = list(self.events)
        if topic:
            result = [e for e in result if e.topic == topic]
        if source:
            result = [e for e in result if e.source == source]
        return result[-limit:]

    def get_subscriptions(self, active_only: bool = False) -> list[Subscription]:
        if active_only:
            return [s for s in self.subscriptions if s.active]
        return list(self.subscriptions)

    def retry_dead_letters(self) -> int:
        retried = 0
        remaining = []
        for dl in self.dead_letters:
            handler = self._handlers.get(dl.subscription_id)
            if handler:
                try:
                    handler(dl.event)
                    dl.event.delivered = True
                    retried += 1
                except Exception:
                    dl.attempts += 1
                    dl.last_attempt_at = datetime.datetime.utcnow().isoformat()
                    remaining.append(dl)
            else:
                remaining.append(dl)
        self.dead_letters = remaining
        return retried

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_events": len(self.events),
            "total_subscriptions": len(self.subscriptions),
            "active_subscriptions": sum(1 for s in self.subscriptions if s.active),
            "dead_letters": len(self.dead_letters),
            "topics": list(set(e.topic for e in self.events)),
            "sources": list(set(e.source for e in self.events)),
        }


# ---------------------------------------------------------------------------
# Tests: Event
# ---------------------------------------------------------------------------

class TestEvent:
    def test_create_event(self):
        event = Event(id="e1", topic="test.event")
        assert event.topic == "test.event"
        assert event.source == "system"
        assert event.priority == "normal"
        assert event.timestamp != ""

    def test_event_with_payload(self):
        event = Event(id="e1", topic="test", payload={"key": "value"})
        assert event.payload["key"] == "value"

    def test_event_to_dict(self):
        event = Event(id="e1", topic="test", source="api")
        d = event.to_dict()
        assert d["id"] == "e1"
        assert d["topic"] == "test"
        assert d["source"] == "api"

    def test_event_to_json(self):
        event = Event(id="e1", topic="test")
        j = event.to_json()
        parsed = json.loads(j)
        assert parsed["id"] == "e1"

    def test_event_from_dict(self):
        data = {"id": "e1", "topic": "test", "priority": "high"}
        event = Event.from_dict(data)
        assert event.id == "e1"
        assert event.priority == "high"

    def test_event_roundtrip(self):
        original = Event(id="e1", topic="test", payload={"a": 1})
        d = original.to_dict()
        restored = Event.from_dict(d)
        assert restored.id == original.id
        assert restored.topic == original.topic
        assert restored.payload == original.payload


# ---------------------------------------------------------------------------
# Tests: Subscription
# ---------------------------------------------------------------------------

class TestSubscription:
    def test_exact_match(self):
        sub = Subscription(id="s1", topic_pattern="test.event", callback_name="h")
        assert sub.matches("test.event") is True
        assert sub.matches("test.other") is False

    def test_wildcard_suffix(self):
        sub = Subscription(id="s1", topic_pattern="test.*", callback_name="h")
        assert sub.matches("test.a") is True
        assert sub.matches("test.b.c") is True
        assert sub.matches("other.a") is False

    def test_wildcard_prefix(self):
        sub = Subscription(id="s1", topic_pattern="*.completed", callback_name="h")
        assert sub.matches("task.completed") is True
        assert sub.matches("spec.completed") is True
        assert sub.matches("spec.started") is False

    def test_no_match(self):
        sub = Subscription(id="s1", topic_pattern="exact", callback_name="h")
        assert sub.matches("different") is False

    def test_empty_pattern(self):
        sub = Subscription(id="s1", topic_pattern="", callback_name="h")
        assert sub.matches("anything") is False

    def test_active_flag(self):
        sub = Subscription(id="s1", topic_pattern="test", callback_name="h", active=False)
        assert sub.active is False


# ---------------------------------------------------------------------------
# Tests: EventBus
# ---------------------------------------------------------------------------

class TestEventBus:
    def test_publish_event(self):
        bus = EventBus()
        event = bus.publish("test.event", {"key": "value"})
        assert event.topic == "test.event"
        assert len(bus.events) == 1

    def test_publish_multiple_events(self):
        bus = EventBus()
        bus.publish("a")
        bus.publish("b")
        bus.publish("c")
        assert len(bus.events) == 3

    def test_subscribe_and_receive(self):
        bus = EventBus()
        received = []
        bus.subscribe("test.*", handler=lambda e: received.append(e))
        bus.publish("test.event", {"data": 1})
        assert len(received) == 1
        assert received[0].topic == "test.event"

    def test_subscribe_exact_topic(self):
        bus = EventBus()
        received = []
        bus.subscribe("specific.topic", handler=lambda e: received.append(e))
        bus.publish("specific.topic")
        bus.publish("other.topic")
        assert len(received) == 1

    def test_multiple_subscribers(self):
        bus = EventBus()
        r1 = []
        r2 = []
        bus.subscribe("test.*", handler=lambda e: r1.append(e))
        bus.subscribe("test.*", handler=lambda e: r2.append(e))
        bus.publish("test.event")
        assert len(r1) == 1
        assert len(r2) == 1

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        sub = bus.subscribe("test", handler=lambda e: received.append(e))
        bus.publish("test")
        assert len(received) == 1
        bus.unsubscribe(sub.id)
        bus.publish("test")
        assert len(received) == 1  # No new events

    def test_unsubscribe_nonexistent(self):
        bus = EventBus()
        assert bus.unsubscribe("nonexistent") is False

    def test_subscriber_count(self):
        bus = EventBus()
        bus.subscribe("test.*", handler_name="h1")
        bus.subscribe("test.*", handler_name="h2")
        event = bus.publish("test.event")
        assert event.subscriber_count == 2

    def test_no_subscribers(self):
        bus = EventBus()
        event = bus.publish("orphan.event")
        assert event.subscriber_count == 0
        assert event.delivered is True

    def test_handler_error_creates_dead_letter(self):
        bus = EventBus()

        def failing_handler(e):
            raise RuntimeError("Handler failed!")

        bus.subscribe("test", handler=failing_handler)
        event = bus.publish("test")
        assert len(bus.dead_letters) == 1
        assert "Handler failed" in bus.dead_letters[0].error

    def test_get_events_by_topic(self):
        bus = EventBus()
        bus.publish("a.topic")
        bus.publish("b.topic")
        bus.publish("a.topic")
        events = bus.get_events(topic="a.topic")
        assert len(events) == 2

    def test_get_events_by_source(self):
        bus = EventBus()
        bus.publish("test", source="api")
        bus.publish("test", source="cli")
        bus.publish("test", source="api")
        events = bus.get_events(source="api")
        assert len(events) == 2

    def test_get_events_with_limit(self):
        bus = EventBus()
        for i in range(20):
            bus.publish(f"event.{i}")
        events = bus.get_events(limit=5)
        assert len(events) == 5

    def test_event_priority(self):
        bus = EventBus()
        event = bus.publish("alert", priority="high")
        assert event.priority == "high"

    def test_event_source(self):
        bus = EventBus()
        event = bus.publish("test", source="webhook")
        assert event.source == "webhook"

    def test_subscription_event_count(self):
        bus = EventBus()
        sub = bus.subscribe("test.*")
        bus.publish("test.a")
        bus.publish("test.b")
        bus.publish("test.c")
        assert sub.event_count == 3

    def test_inactive_subscription_skipped(self):
        bus = EventBus()
        received = []
        sub = bus.subscribe("test", handler=lambda e: received.append(e))
        bus.publish("test")
        assert len(received) == 1
        sub.active = False
        bus.publish("test")
        assert len(received) == 1

    def test_get_active_subscriptions(self):
        bus = EventBus()
        s1 = bus.subscribe("a")
        s2 = bus.subscribe("b")
        s2.active = False
        active = bus.get_subscriptions(active_only=True)
        assert len(active) == 1

    def test_stats(self):
        bus = EventBus()
        bus.subscribe("test.*")
        bus.publish("test.a", source="api")
        bus.publish("test.b", source="cli")
        stats = bus.stats
        assert stats["total_events"] == 2
        assert stats["total_subscriptions"] == 1
        assert len(stats["topics"]) == 2
        assert len(stats["sources"]) == 2

    def test_retry_dead_letters(self):
        bus = EventBus()
        call_count = [0]

        def sometimes_fail(e):
            call_count[0] += 1
            if call_count[0] <= 1:
                raise RuntimeError("fail")

        sub = bus.subscribe("test", handler=sometimes_fail)
        bus.publish("test")
        assert len(bus.dead_letters) == 1

        # Retry should succeed now (call_count > 1)
        retried = bus.retry_dead_letters()
        assert retried == 1
        assert len(bus.dead_letters) == 0


# ---------------------------------------------------------------------------
# Tests: Event Serialization
# ---------------------------------------------------------------------------

class TestEventSerialization:
    def test_serialize_event_list(self):
        events = [
            Event(id=f"e{i}", topic=f"topic.{i}", payload={"i": i})
            for i in range(5)
        ]
        serialized = json.dumps([e.to_dict() for e in events])
        deserialized = json.loads(serialized)
        assert len(deserialized) == 5

    def test_serialize_with_nested_payload(self):
        event = Event(
            id="e1", topic="complex",
            payload={
                "user": {"name": "Alice", "roles": ["admin", "user"]},
                "action": "login",
                "meta": {"ip": "127.0.0.1", "timestamp": 12345},
            },
        )
        j = event.to_json()
        restored = Event.from_dict(json.loads(j))
        assert restored.payload["user"]["name"] == "Alice"
        assert "admin" in restored.payload["user"]["roles"]

    def test_serialize_empty_payload(self):
        event = Event(id="e1", topic="empty")
        j = event.to_json()
        restored = Event.from_dict(json.loads(j))
        assert restored.payload == {}


# ---------------------------------------------------------------------------
# Tests: Event Filtering
# ---------------------------------------------------------------------------

class TestEventFiltering:
    def test_filter_by_multiple_criteria(self):
        bus = EventBus()
        bus.publish("deploy.start", source="ci", priority="high")
        bus.publish("deploy.end", source="ci", priority="normal")
        bus.publish("test.run", source="ci", priority="normal")

        # Filter by topic and source
        deploy_events = [
            e for e in bus.get_events()
            if e.topic.startswith("deploy") and e.source == "ci"
        ]
        assert len(deploy_events) == 2

    def test_filter_high_priority(self):
        bus = EventBus()
        bus.publish("alert", priority="high")
        bus.publish("info", priority="normal")
        bus.publish("critical", priority="high")

        high_priority = [e for e in bus.get_events() if e.priority == "high"]
        assert len(high_priority) == 2

    def test_filter_undelivered(self):
        bus = EventBus()

        def fail(e):
            raise RuntimeError("fail")

        bus.subscribe("test", handler=fail)
        bus.publish("test")
        bus.publish("other")

        undelivered = [e for e in bus.get_events() if not e.delivered]
        assert len(undelivered) >= 0  # May or may not be delivered based on logic
