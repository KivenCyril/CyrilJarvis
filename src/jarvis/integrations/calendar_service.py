"""Calendar service abstraction for JARVIS.

Provides a local in-memory calendar backend for event management:
- Create, read, update, delete events
- Conflict detection
- Free-slot finding
- Text-based event search
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CalendarEvent(BaseModel):
    """Represents a calendar event."""

    id: str = ""
    title: str = ""
    description: str = ""
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime = Field(default_factory=datetime.now)
    location: str = ""
    attendees: list[str] = Field(default_factory=list)
    recurrence: str = ""  # e.g. "daily", "weekly", "monthly"
    reminders: list[int] = Field(default_factory=list)  # minutes before event
    all_day: bool = False


class CalendarService:
    """Calendar service with a local in-memory backend.

    Provides CRUD operations, conflict detection, and free-slot discovery.
    Can be extended to integrate with Google Calendar, Outlook, etc.
    """

    def __init__(self, backend: str = "local"):
        self.backend = backend
        self._events: list[CalendarEvent] = []

    # --------------------------------------------------------------------- #
    # CRUD
    # --------------------------------------------------------------------- #

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        """Create a new calendar event.

        Assigns an ID if one is not already set.
        """
        if not event.id:
            event.id = uuid.uuid4().hex[:12]
        self._events.append(event)
        logger.info("Created event %s: %s", event.id, event.title)
        return event

    async def get_events(
        self, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Get events that overlap with the given time range.

        An event overlaps if its start is before *end* and its end is
        after *start*.
        """
        results: list[CalendarEvent] = []
        for ev in self._events:
            if ev.start_time < end and ev.end_time > start:
                results.append(ev)
        return sorted(results, key=lambda e: e.start_time)

    async def update_event(
        self, event_id: str, **fields: Any
    ) -> CalendarEvent:
        """Update an existing event by ID.

        Returns the updated event, or raises ``ValueError`` if not found.
        """
        for ev in self._events:
            if ev.id == event_id:
                for key, value in fields.items():
                    if hasattr(ev, key):
                        setattr(ev, key, value)
                logger.info("Updated event %s", event_id)
                return ev
        raise ValueError(f"Event {event_id} not found")

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event by ID.  Returns ``True`` if found and deleted."""
        for i, ev in enumerate(self._events):
            if ev.id == event_id:
                self._events.pop(i)
                logger.info("Deleted event %s", event_id)
                return True
        return False

    # --------------------------------------------------------------------- #
    # Conflict & Free-slot queries
    # --------------------------------------------------------------------- #

    async def find_conflicts(
        self, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Find events that conflict with the proposed time range.

        Same logic as ``get_events`` -- any event whose span overlaps
        ``[start, end)`` is a conflict.
        """
        return await self.get_events(start, end)

    async def find_free_slots(
        self,
        date: datetime,
        duration_minutes: int = 60,
        work_start_hour: int = 9,
        work_end_hour: int = 18,
    ) -> list[tuple[datetime, datetime]]:
        """Find free time slots on a given day.

        Scans the working window (default 09:00-18:00) for gaps at least
        ``duration_minutes`` long.  Returns a list of ``(start, end)``
        tuples.
        """
        day_start = date.replace(
            hour=work_start_hour, minute=0, second=0, microsecond=0
        )
        day_end = date.replace(
            hour=work_end_hour, minute=0, second=0, microsecond=0
        )
        duration = timedelta(minutes=duration_minutes)

        events = await self.get_events(day_start, day_end)
        # Sort events by start time
        events.sort(key=lambda e: e.start_time)

        free_slots: list[tuple[datetime, datetime]] = []
        current = day_start

        for ev in events:
            ev_start = max(ev.start_time, day_start)
            if current + duration <= ev_start:
                free_slots.append((current, ev_start))
            current = max(current, min(ev.end_time, day_end))

        # Check remaining time after last event
        if current + duration <= day_end:
            free_slots.append((current, day_end))

        return free_slots

    # --------------------------------------------------------------------- #
    # Search
    # --------------------------------------------------------------------- #

    async def search_events(self, query: str) -> list[CalendarEvent]:
        """Search events by title or description (case-insensitive)."""
        q = query.lower()
        results: list[CalendarEvent] = []
        for ev in self._events:
            if q in ev.title.lower() or q in ev.description.lower():
                results.append(ev)
        return results
