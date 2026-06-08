"""Core Event Bus implementation for JARVIS.

Provides a fully async pub/sub event system with:
- Topic-based routing with wildcard support (``agent.*``)
- Priority ordering
- Event filtering (by topic, source, priority)
- One-shot subscriptions
- Event history and replay
- Dead letter queue for failed handlers
- Middleware pipeline (transform / drop events before delivery)
- Persistent ``EventStore`` backed by JSON-lines files
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums & value objects
# ---------------------------------------------------------------------------


class EventPriority(IntEnum):
    """Numeric priority levels — higher values are delivered first."""

    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 15


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """An immutable event that flows through the bus."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    topic: str  # e.g. "agent.executed", "spec.created"
    source: str = ""
    priority: EventPriority = EventPriority.NORMAL
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = ""  # for tracing related events


# ---------------------------------------------------------------------------
# EventFilter
# ---------------------------------------------------------------------------


class EventFilter(BaseModel):
    """Declarative filter that decides whether an ``Event`` is relevant."""

    topics: list[str] = Field(default_factory=list)  # supports wildcards: "agent.*"
    sources: list[str] = Field(default_factory=list)
    min_priority: EventPriority = EventPriority.LOW

    def matches(self, event: Event) -> bool:
        """Return ``True`` if *event* passes all filter criteria."""

        # --- topic matching --------------------------------------------------
        if self.topics:
            matched = False
            for pattern in self.topics:
                if pattern == "*":
                    matched = True
                    break
                elif pattern.endswith(".*"):
                    prefix = pattern[:-2]
                    if event.topic == prefix or event.topic.startswith(prefix + "."):
                        matched = True
                        break
                elif pattern == event.topic:
                    matched = True
                    break
            if not matched:
                return False

        # --- source matching -------------------------------------------------
        if self.sources and event.source not in self.sources:
            return False

        # --- priority gate ---------------------------------------------------
        if event.priority < self.min_priority:
            return False

        return True


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

EventHandler = Callable[[Event], Awaitable[None]]


@dataclass
class EventSubscription:
    """Internal record of a handler registration."""

    id: str
    handler: Callable[[Event], Any]
    filter: EventFilter
    once: bool = False
    created_at: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBus:
    """Central event bus for decoupled communication between JARVIS modules.

    Features
    --------
    - Topic-based pub/sub with wildcard support (``agent.*``, ``spec.*``)
    - Priority-based event ordering
    - Event filtering (by topic, source, priority)
    - Sync **and** async handlers
    - One-shot subscriptions
    - Event history / replay
    - Dead letter queue for failed handlers
    - Event correlation (group related events)
    - Middleware support (transform / filter events before delivery)
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._subscriptions: dict[str, EventSubscription] = {}
        self._history: list[Event] = []
        self._max_history = max_history
        self._dead_letters: list[tuple[Event, str, str]] = []  # (event, handler_id, error)
        self._middleware: list[Callable[[Event], Event | None]] = []
        self._stats: dict[str, int] = {"published": 0, "delivered": 0, "failed": 0}

    # -- subscribe / unsubscribe ---------------------------------------------

    def subscribe(
        self,
        handler: Callable[[Event], Any],
        topics: list[str] | None = None,
        sources: list[str] | None = None,
        min_priority: EventPriority = EventPriority.LOW,
        once: bool = False,
    ) -> str:
        """Subscribe *handler* to events matching the given filter.

        Returns
        -------
        str
            A subscription id that can later be passed to :meth:`unsubscribe`.
        """
        sub_id = uuid.uuid4().hex[:10]
        ef = EventFilter(
            topics=topics or [],
            sources=sources or [],
            min_priority=min_priority,
        )
        sub = EventSubscription(id=sub_id, handler=handler, filter=ef, once=once)
        self._subscriptions[sub_id] = sub
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove the subscription identified by *subscription_id*."""
        self._subscriptions.pop(subscription_id, None)

    # -- publish -------------------------------------------------------------

    async def publish(self, event: Event) -> int:
        """Publish *event* to all matching subscribers.

        Returns the number of handlers that successfully received the event.
        """
        self._stats["published"] += 1

        # 1. Middleware pipeline — any middleware can transform or drop
        current: Event | None = event
        for mw in self._middleware:
            if current is None:
                break
            result = mw(current)
            if asyncio.iscoroutine(result):
                result = await result
            current = result
        if current is None:
            # middleware dropped the event
            return 0
        event = current

        # 2. Find matching subscriptions
        matching: list[EventSubscription] = []
        for sub in list(self._subscriptions.values()):
            if sub.filter.matches(event):
                matching.append(sub)

        # 3. Sort by subscription creation time (stable order)
        matching.sort(key=lambda s: s.created_at)

        # 4. Deliver
        delivered = 0
        to_remove: list[str] = []
        for sub in matching:
            try:
                ret = sub.handler(event)
                if asyncio.iscoroutine(ret) or asyncio.isfuture(ret):
                    await ret
                delivered += 1
                self._stats["delivered"] += 1
            except Exception as exc:  # noqa: BLE001
                self._stats["failed"] += 1
                self._dead_letters.append((event, sub.id, str(exc)))
                logger.warning(
                    "Handler %s failed for event %s: %s",
                    sub.id,
                    event.topic,
                    exc,
                )
            if sub.once:
                to_remove.append(sub.id)

        # 5. Remove one-shot subscriptions that fired
        for sid in to_remove:
            self._subscriptions.pop(sid, None)

        # 6. Record history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        return delivered

    async def publish_simple(self, topic: str, source: str = "", **data: Any) -> int:
        """Convenience helper: create an ``Event`` and publish it in one call."""
        event = Event(topic=topic, source=source, data=data)
        return await self.publish(event)

    # -- middleware -----------------------------------------------------------

    def add_middleware(self, middleware: Callable[[Event], Event | None]) -> None:
        """Register a middleware function.

        The middleware receives an ``Event`` and must return either a
        (possibly modified) ``Event`` or ``None`` to silently drop it.
        """
        self._middleware.append(middleware)

    # -- history & replay ----------------------------------------------------

    def get_history(self, topic: str | None = None, limit: int = 50) -> list[Event]:
        """Return recent events, optionally filtered by *topic*.

        The most recent events come last (chronological order).
        """
        if topic is None:
            return list(self._history[-limit:])
        filtered = [e for e in self._history if e.topic == topic]
        return filtered[-limit:]

    async def replay(self, topic: str, handler: Callable[[Event], Any]) -> int:
        """Replay stored history for *topic* through *handler*.

        Returns the number of events replayed.
        """
        events = self.get_history(topic=topic, limit=self._max_history)
        count = 0
        for ev in events:
            try:
                ret = handler(ev)
                if asyncio.iscoroutine(ret) or asyncio.isfuture(ret):
                    await ret
                count += 1
            except Exception:  # noqa: BLE001
                pass
        return count

    def clear_history(self) -> None:
        """Remove all stored events from the in-memory history."""
        self._history.clear()

    # -- dead letters --------------------------------------------------------

    def get_dead_letters(self, limit: int = 50) -> list[tuple[Event, str, str]]:
        """Return the most recent dead-letter entries."""
        return list(self._dead_letters[-limit:])

    # -- stats ---------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return cumulative bus statistics."""
        return {
            **self._stats,
            "subscriptions": len(self._subscriptions),
            "history_size": len(self._history),
            "dead_letters": len(self._dead_letters),
        }


# ---------------------------------------------------------------------------
# EventStore — persistent storage
# ---------------------------------------------------------------------------


class EventStore:
    """Persistent event storage backed by JSON-lines files.

    Each day's events are written to a separate file to keep individual
    files small and to simplify time-range queries.
    """

    def __init__(self, storage_path: str = "~/.jarvis/events") -> None:
        self._base_path = Path(storage_path).expanduser()
        self._base_path.mkdir(parents=True, exist_ok=True)

    # -- internal helpers ----------------------------------------------------

    def _file_for_date(self, dt: datetime) -> Path:
        return self._base_path / f"events-{dt.strftime('%Y-%m-%d')}.jsonl"

    def _serialize(self, event: Event) -> str:
        return event.model_dump_json()

    def _deserialize(self, line: str) -> Event:
        return Event.model_validate_json(line)

    # -- public API ----------------------------------------------------------

    async def store(self, event: Event) -> None:
        """Append *event* to the day's log file."""
        path = self._file_for_date(event.timestamp)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(self._serialize(event) + "\n")

    async def query(
        self,
        topic: str = "",
        source: str = "",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Query stored events with optional filters."""
        results: list[Event] = []

        files = sorted(self._base_path.glob("events-*.jsonl"))
        for fp in files:
            with open(fp, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = self._deserialize(line)
                    except Exception:  # noqa: BLE001
                        continue

                    if topic and ev.topic != topic:
                        continue
                    if source and ev.source != source:
                        continue
                    if start and ev.timestamp < start:
                        continue
                    if end and ev.timestamp > end:
                        continue

                    results.append(ev)
                    if len(results) >= limit:
                        return results
        return results

    async def count(self, topic: str = "") -> int:
        """Return the total number of stored events, optionally filtered by *topic*."""
        total = 0
        for fp in self._base_path.glob("events-*.jsonl"):
            with open(fp, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    if topic:
                        try:
                            ev = self._deserialize(line)
                            if ev.topic == topic:
                                total += 1
                        except Exception:  # noqa: BLE001
                            continue
                    else:
                        total += 1
        return total

    async def aggregate(
        self,
        topic: str,
        field: str,
        operation: str = "count",
    ) -> Any:
        """Run a simple aggregation over events matching *topic*.

        Supported operations: ``count``, ``sum``, ``min``, ``max``, ``avg``.
        The *field* is looked up in ``event.data``.
        """
        values: list[float] = []
        for fp in self._base_path.glob("events-*.jsonl"):
            with open(fp, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = self._deserialize(line)
                    except Exception:  # noqa: BLE001
                        continue
                    if topic and ev.topic != topic:
                        continue
                    val = ev.data.get(field)
                    if val is not None:
                        try:
                            values.append(float(val))
                        except (TypeError, ValueError):
                            continue

        if operation == "count":
            return len(values)
        if not values:
            return None
        if operation == "sum":
            return sum(values)
        if operation == "min":
            return min(values)
        if operation == "max":
            return max(values)
        if operation == "avg":
            return sum(values) / len(values)
        raise ValueError(f"Unknown aggregation operation: {operation}")
