from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

EventHandler = Callable[["HookEvent"], Awaitable[None]]


@dataclass
class HookEvent:
    source: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CronJob:
    name: str
    interval_seconds: int
    handler: EventHandler
    enabled: bool = True
    _task: asyncio.Task | None = field(default=None, repr=False)


class HookEngine:
    """Event capture and dispatch engine with cron support.

    Four hook layers:
    - L1: Timer/Cron hooks (built-in scheduler)
    - L2: Git/CI hooks (external webhook → emit)
    - L3: Communication hooks (email/messaging → emit)
    - L4: System hooks (alerts/file changes → emit)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._cron_jobs: dict[str, CronJob] = {}
        self._event_log: list[HookEvent] = []
        self._running = False

    def on(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: HookEvent) -> None:
        self._event_log.append(event)
        handlers = self._handlers.get(event.event_type, [])
        wildcard_handlers = self._handlers.get("*", [])

        all_handlers = handlers + wildcard_handlers
        if not all_handlers:
            logger.debug("No handlers for event: %s", event.event_type)
            return

        for handler in all_handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("Handler failed for event %s", event.event_type)

    def add_cron(self, name: str, interval_seconds: int, handler: EventHandler) -> CronJob:
        job = CronJob(name=name, interval_seconds=interval_seconds, handler=handler)
        self._cron_jobs[name] = job
        if self._running:
            self._start_cron_job(job)
        return job

    def remove_cron(self, name: str) -> None:
        job = self._cron_jobs.pop(name, None)
        if job and job._task:
            job._task.cancel()

    def _start_cron_job(self, job: CronJob) -> None:
        async def _loop():
            while job.enabled:
                await asyncio.sleep(job.interval_seconds)
                if not job.enabled:
                    break
                event = HookEvent(source=f"cron:{job.name}", event_type=f"cron.{job.name}")
                try:
                    await job.handler(event)
                except Exception:
                    logger.exception("Cron job '%s' failed", job.name)

        job._task = asyncio.create_task(_loop())

    async def start(self) -> None:
        self._running = True
        for job in self._cron_jobs.values():
            if job.enabled:
                self._start_cron_job(job)
        logger.info("HookEngine started with %d cron jobs", len(self._cron_jobs))

    async def stop(self) -> None:
        self._running = False
        for job in self._cron_jobs.values():
            job.enabled = False
            if job._task:
                job._task.cancel()
        logger.info("HookEngine stopped")

    def registered_events(self) -> list[str]:
        return list(self._handlers.keys())

    def list_cron_jobs(self) -> list[dict[str, Any]]:
        return [
            {"name": j.name, "interval": j.interval_seconds, "enabled": j.enabled}
            for j in self._cron_jobs.values()
        ]

    def event_log(self, limit: int = 50) -> list[HookEvent]:
        return self._event_log[-limit:]
