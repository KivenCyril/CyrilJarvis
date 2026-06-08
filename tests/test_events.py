"""Tests for jarvis.events — EventBus, Event, EventFilter, EventStore, Topics."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone

import pytest

from jarvis.events.bus import Event, EventBus, EventFilter, EventPriority, EventStore
from jarvis.events.topics import Topics


# ── helpers ──────────────────────────────────────────────────────────────────


def _collector() -> tuple[list[Event], "Callable"]:
    """Return (list, handler) where handler appends events to list."""
    events: list[Event] = []

    async def _handler(event: Event) -> None:
        events.append(event)

    return events, _handler


# ── Event model ──────────────────────────────────────────────────────────────


class TestEventModel:
    def test_event_defaults(self):
        ev = Event(topic="test.event")
        assert ev.topic == "test.event"
        assert ev.source == ""
        assert ev.priority == EventPriority.NORMAL
        assert ev.id  # non-empty
        assert ev.data == {}
        assert ev.metadata == {}

    def test_event_with_data(self):
        ev = Event(topic="x", data={"key": "value"}, source="src")
        assert ev.data["key"] == "value"
        assert ev.source == "src"

    def test_event_priority(self):
        ev = Event(topic="x", priority=EventPriority.CRITICAL)
        assert ev.priority == EventPriority.CRITICAL
        assert ev.priority > EventPriority.HIGH

    def test_event_correlation_id(self):
        ev = Event(topic="x", correlation_id="abc123")
        assert ev.correlation_id == "abc123"

    def test_event_timestamp_utc(self):
        ev = Event(topic="x")
        assert ev.timestamp.tzinfo is not None


# ── EventFilter ──────────────────────────────────────────────────────────────


class TestEventFilter:
    def test_empty_filter_matches_everything(self):
        f = EventFilter()
        ev = Event(topic="any.thing", source="anywhere")
        assert f.matches(ev)

    def test_exact_topic_match(self):
        f = EventFilter(topics=["agent.completed"])
        assert f.matches(Event(topic="agent.completed"))
        assert not f.matches(Event(topic="agent.failed"))

    def test_wildcard_topic(self):
        f = EventFilter(topics=["agent.*"])
        assert f.matches(Event(topic="agent.completed"))
        assert f.matches(Event(topic="agent.failed"))
        assert not f.matches(Event(topic="spec.created"))

    def test_wildcard_star(self):
        f = EventFilter(topics=["*"])
        assert f.matches(Event(topic="anything.at.all"))

    def test_source_filter(self):
        f = EventFilter(sources=["code-agent"])
        assert f.matches(Event(topic="x", source="code-agent"))
        assert not f.matches(Event(topic="x", source="other"))

    def test_priority_filter(self):
        f = EventFilter(min_priority=EventPriority.HIGH)
        assert f.matches(Event(topic="x", priority=EventPriority.HIGH))
        assert f.matches(Event(topic="x", priority=EventPriority.CRITICAL))
        assert not f.matches(Event(topic="x", priority=EventPriority.NORMAL))

    def test_combined_filter(self):
        f = EventFilter(
            topics=["agent.*"],
            sources=["code"],
            min_priority=EventPriority.HIGH,
        )
        assert f.matches(Event(topic="agent.x", source="code", priority=EventPriority.HIGH))
        assert not f.matches(Event(topic="agent.x", source="other", priority=EventPriority.HIGH))
        assert not f.matches(Event(topic="spec.x", source="code", priority=EventPriority.HIGH))
        assert not f.matches(Event(topic="agent.x", source="code", priority=EventPriority.LOW))

    def test_multiple_topic_patterns(self):
        f = EventFilter(topics=["agent.*", "spec.created"])
        assert f.matches(Event(topic="agent.failed"))
        assert f.matches(Event(topic="spec.created"))
        assert not f.matches(Event(topic="spec.failed"))

    def test_wildcard_matches_parent_topic(self):
        """``agent.*`` should match ``agent.something``."""
        f = EventFilter(topics=["agent.*"])
        assert f.matches(Event(topic="agent.executing"))
        # but not a bare unrelated prefix
        assert not f.matches(Event(topic="agentx"))


# ── EventBus ─────────────────────────────────────────────────────────────────


class TestEventBus:
    @pytest.mark.asyncio
    async def test_basic_pubsub(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["test.event"])
        count = await bus.publish(Event(topic="test.event"))
        assert count == 1
        assert len(collected) == 1

    @pytest.mark.asyncio
    async def test_no_match(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["other.event"])
        count = await bus.publish(Event(topic="test.event"))
        assert count == 0
        assert len(collected) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = EventBus()
        c1, h1 = _collector()
        c2, h2 = _collector()
        bus.subscribe(h1, topics=["x"])
        bus.subscribe(h2, topics=["x"])
        count = await bus.publish(Event(topic="x"))
        assert count == 2
        assert len(c1) == 1
        assert len(c2) == 1

    @pytest.mark.asyncio
    async def test_wildcard_subscribe(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["agent.*"])
        await bus.publish(Event(topic="agent.completed"))
        await bus.publish(Event(topic="agent.failed"))
        await bus.publish(Event(topic="spec.created"))
        assert len(collected) == 2

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = EventBus()
        collected, handler = _collector()
        sub_id = bus.subscribe(handler, topics=["x"])
        await bus.publish(Event(topic="x"))
        assert len(collected) == 1
        bus.unsubscribe(sub_id)
        await bus.publish(Event(topic="x"))
        assert len(collected) == 1  # no change

    @pytest.mark.asyncio
    async def test_once_subscription(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["x"], once=True)
        await bus.publish(Event(topic="x"))
        await bus.publish(Event(topic="x"))
        assert len(collected) == 1

    @pytest.mark.asyncio
    async def test_publish_simple(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["ping"])
        count = await bus.publish_simple("ping", source="test", msg="hello")
        assert count == 1
        assert collected[0].data["msg"] == "hello"
        assert collected[0].source == "test"

    @pytest.mark.asyncio
    async def test_handler_error_goes_to_dead_letters(self):
        bus = EventBus()

        async def bad_handler(ev: Event) -> None:
            raise RuntimeError("boom")

        bus.subscribe(bad_handler, topics=["x"])
        count = await bus.publish(Event(topic="x"))
        assert count == 0
        dl = bus.get_dead_letters()
        assert len(dl) == 1
        assert "boom" in dl[0][2]

    @pytest.mark.asyncio
    async def test_stats(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["x"])
        await bus.publish(Event(topic="x"))
        stats = bus.get_stats()
        assert stats["published"] == 1
        assert stats["delivered"] == 1
        assert stats["failed"] == 0
        assert stats["subscriptions"] == 1

    @pytest.mark.asyncio
    async def test_history(self):
        bus = EventBus()
        await bus.publish(Event(topic="a"))
        await bus.publish(Event(topic="b"))
        await bus.publish(Event(topic="a"))
        assert len(bus.get_history()) == 3
        assert len(bus.get_history(topic="a")) == 2

    @pytest.mark.asyncio
    async def test_history_limit(self):
        bus = EventBus(max_history=5)
        for i in range(10):
            await bus.publish(Event(topic="x", data={"i": i}))
        assert len(bus.get_history()) == 5

    @pytest.mark.asyncio
    async def test_clear_history(self):
        bus = EventBus()
        await bus.publish(Event(topic="x"))
        bus.clear_history()
        assert len(bus.get_history()) == 0

    @pytest.mark.asyncio
    async def test_replay(self):
        bus = EventBus()
        await bus.publish(Event(topic="x", data={"n": 1}))
        await bus.publish(Event(topic="x", data={"n": 2}))
        await bus.publish(Event(topic="y", data={"n": 3}))

        replayed, handler = _collector()
        count = await bus.replay("x", handler)
        assert count == 2
        assert len(replayed) == 2

    @pytest.mark.asyncio
    async def test_middleware_transform(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["x"])

        def add_tag(event: Event) -> Event:
            event.metadata["injected"] = True
            return event

        bus.add_middleware(add_tag)
        await bus.publish(Event(topic="x"))
        assert collected[0].metadata.get("injected") is True

    @pytest.mark.asyncio
    async def test_middleware_drop(self):
        bus = EventBus()
        collected, handler = _collector()
        bus.subscribe(handler, topics=["x"])

        def drop_all(event: Event) -> Event | None:
            return None

        bus.add_middleware(drop_all)
        count = await bus.publish(Event(topic="x"))
        assert count == 0
        assert len(collected) == 0

    @pytest.mark.asyncio
    async def test_sync_handler(self):
        """Bus should also work with plain sync handlers."""
        bus = EventBus()
        results: list[str] = []

        def sync_handler(ev: Event) -> None:
            results.append(ev.topic)

        bus.subscribe(sync_handler, topics=["x"])
        await bus.publish(Event(topic="x"))
        assert results == ["x"]

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_is_noop(self):
        bus = EventBus()
        bus.unsubscribe("does-not-exist")  # should not raise


# ── EventStore ───────────────────────────────────────────────────────────────


class TestEventStore:
    @pytest.mark.asyncio
    async def test_store_and_query(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        ev = Event(topic="agent.completed", source="test", data={"x": 1})
        await store.store(ev)
        results = await store.query(topic="agent.completed")
        assert len(results) == 1
        assert results[0].topic == "agent.completed"
        assert results[0].data["x"] == 1

    @pytest.mark.asyncio
    async def test_query_by_source(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        await store.store(Event(topic="x", source="a"))
        await store.store(Event(topic="x", source="b"))
        results = await store.query(source="a")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_count(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        await store.store(Event(topic="a"))
        await store.store(Event(topic="b"))
        await store.store(Event(topic="a"))
        assert await store.count() == 3
        assert await store.count(topic="a") == 2

    @pytest.mark.asyncio
    async def test_aggregate_sum(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        await store.store(Event(topic="metric", data={"value": 10}))
        await store.store(Event(topic="metric", data={"value": 20}))
        await store.store(Event(topic="metric", data={"value": 30}))
        assert await store.aggregate("metric", "value", "sum") == 60

    @pytest.mark.asyncio
    async def test_aggregate_avg(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        await store.store(Event(topic="metric", data={"value": 10}))
        await store.store(Event(topic="metric", data={"value": 30}))
        assert await store.aggregate("metric", "value", "avg") == 20.0

    @pytest.mark.asyncio
    async def test_aggregate_min_max(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        await store.store(Event(topic="m", data={"v": 5}))
        await store.store(Event(topic="m", data={"v": 15}))
        assert await store.aggregate("m", "v", "min") == 5
        assert await store.aggregate("m", "v", "max") == 15

    @pytest.mark.asyncio
    async def test_aggregate_count(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        await store.store(Event(topic="m", data={"v": 1}))
        await store.store(Event(topic="m", data={"v": 2}))
        assert await store.aggregate("m", "v", "count") == 2

    @pytest.mark.asyncio
    async def test_query_limit(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        for i in range(10):
            await store.store(Event(topic="x", data={"i": i}))
        results = await store.query(topic="x", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_aggregate_unknown_operation(self, tmp_path):
        store = EventStore(storage_path=str(tmp_path))
        await store.store(Event(topic="m", data={"v": 1}))
        with pytest.raises(ValueError, match="Unknown aggregation"):
            await store.aggregate("m", "v", "median")


# ── Topics ───────────────────────────────────────────────────────────────────


class TestTopics:
    def test_agent_topics_exist(self):
        assert Topics.AGENT_COMPLETED == "agent.completed"
        assert Topics.AGENT_FAILED == "agent.failed"

    def test_spec_topics_exist(self):
        assert Topics.SPEC_CREATED == "spec.created"
        assert Topics.SPEC_STEP_COMPLETED == "spec.step.completed"

    def test_system_topics_exist(self):
        assert Topics.SYSTEM_STARTUP == "system.startup"
        assert Topics.SYSTEM_SHUTDOWN == "system.shutdown"

    def test_security_topics_exist(self):
        assert Topics.SECURITY_PERMISSION_DENIED == "security.permission_denied"
        assert Topics.SECURITY_SECRET_DETECTED == "security.secret_detected"

    def test_all_topics_are_strings(self):
        for attr in dir(Topics):
            if attr.isupper():
                assert isinstance(getattr(Topics, attr), str)
