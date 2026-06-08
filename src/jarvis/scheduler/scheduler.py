from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"
    ONCE = "once"
    EVENT = "event"


class TaskTrigger(BaseModel):
    trigger_type: TriggerType
    cron_expression: str = ""  # for CRON type: "0 9 * * 1-5" (weekdays at 9am)
    interval_seconds: int = 0  # for INTERVAL type
    run_at: datetime | None = None  # for ONCE type
    event_name: str = ""  # for EVENT type


class ScheduledTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    description: str = ""
    trigger: TaskTrigger
    action: str  # "spec:intent text" or "agent:name:message" or "hook:event_name"
    enabled: bool = True
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    max_runs: int | None = None  # None = unlimited
    metadata: dict[str, Any] = Field(default_factory=dict)


class Scheduler:
    """Advanced task scheduler for JARVIS.

    Supports:
    - Interval-based scheduling (every N seconds)
    - One-time scheduled tasks (run at specific time)
    - Event-triggered tasks (run when an event fires)
    - Cron-like expressions (basic parsing)
    - Task lifecycle management (create, enable, disable, delete)
    - Persistence (save/load scheduled tasks)
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._action_handler: Callable[[str], Awaitable[str]] | None = None
        self._running = False

    def set_action_handler(
        self, handler: Callable[[str], Awaitable[str]]
    ) -> None:
        self._action_handler = handler

    def add_task(self, task: ScheduledTask) -> ScheduledTask:
        self._tasks[task.id] = task
        self._compute_next_run(task)
        if self._running and task.enabled:
            self._start_task(task)
        logger.info(
            "Scheduled task '%s' (%s)",
            task.name,
            task.trigger.trigger_type.value,
        )
        return task

    def remove_task(self, task_id: str) -> None:
        running = self._running_tasks.pop(task_id, None)
        if running:
            running.cancel()
        self._tasks.pop(task_id, None)

    def enable_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.enabled = True
            if self._running:
                self._start_task(task)

    def disable_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.enabled = False
            running = self._running_tasks.pop(task_id, None)
            if running:
                running.cancel()

    def list_tasks(self) -> list[ScheduledTask]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTask | None:
        return self._tasks.get(task_id)

    def _compute_next_run(self, task: ScheduledTask) -> None:
        now = datetime.now(timezone.utc)
        trigger = task.trigger

        if trigger.trigger_type == TriggerType.INTERVAL:
            task.next_run = now + timedelta(seconds=trigger.interval_seconds)
        elif trigger.trigger_type == TriggerType.ONCE:
            task.next_run = trigger.run_at
        elif trigger.trigger_type == TriggerType.CRON:
            task.next_run = self._next_cron_time(
                trigger.cron_expression, now
            )
        # EVENT type has no scheduled next_run

    @staticmethod
    def _next_cron_time(
        expression: str, after: datetime
    ) -> datetime | None:
        """Basic cron expression parser. Supports: minute hour day month weekday."""
        parts = expression.strip().split()
        if len(parts) != 5:
            return None

        minute, hour, _day, _month, _weekday = parts

        next_time = after.replace(second=0, microsecond=0)
        if minute.startswith("*/"):
            interval = int(minute[2:])
            mins_to_next = interval - (next_time.minute % interval)
            if mins_to_next == interval:
                mins_to_next = 0
            next_time += timedelta(minutes=mins_to_next)
            if next_time <= after:
                next_time += timedelta(minutes=interval)
            return next_time

        try:
            target_minute = int(minute)
            target_hour = int(hour) if hour != "*" else next_time.hour
            next_time = next_time.replace(
                hour=target_hour, minute=target_minute
            )
            if next_time <= after:
                next_time += timedelta(days=1)
            return next_time
        except ValueError:
            return after + timedelta(hours=1)

    def _start_task(self, task: ScheduledTask) -> None:
        if task.id in self._running_tasks:
            return

        async def _run_loop() -> None:
            while task.enabled and self._running:
                if task.trigger.trigger_type == TriggerType.INTERVAL:
                    await asyncio.sleep(task.trigger.interval_seconds)
                elif task.trigger.trigger_type == TriggerType.ONCE:
                    if task.next_run:
                        delay = (
                            task.next_run - datetime.now(timezone.utc)
                        ).total_seconds()
                        if delay > 0:
                            await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(60)  # fallback

                if not task.enabled or not self._running:
                    break

                await self._execute_task(task)

                if task.trigger.trigger_type == TriggerType.ONCE:
                    task.enabled = False
                    break

                if task.max_runs and task.run_count >= task.max_runs:
                    task.enabled = False
                    break

                self._compute_next_run(task)

        self._running_tasks[task.id] = asyncio.create_task(_run_loop())

    async def _execute_task(self, task: ScheduledTask) -> None:
        task.last_run = datetime.now(timezone.utc)
        task.run_count += 1

        if self._action_handler:
            try:
                result = await self._action_handler(task.action)
                logger.info(
                    "Task '%s' executed: %s",
                    task.name,
                    result[:100] if result else "ok",
                )
            except Exception:
                logger.exception("Task '%s' failed", task.name)

    async def trigger_event(self, event_name: str) -> int:
        """Trigger all tasks that listen for a specific event."""
        triggered = 0
        for task in self._tasks.values():
            if (
                task.enabled
                and task.trigger.trigger_type == TriggerType.EVENT
                and task.trigger.event_name == event_name
            ):
                await self._execute_task(task)
                triggered += 1
        return triggered

    async def start(self) -> None:
        self._running = True
        for task in self._tasks.values():
            if task.enabled:
                self._start_task(task)
        logger.info("Scheduler started with %d tasks", len(self._tasks))

    async def stop(self) -> None:
        self._running = False
        for task_async in self._running_tasks.values():
            task_async.cancel()
        self._running_tasks.clear()
        logger.info("Scheduler stopped")

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = [t.model_dump(mode="json") for t in self._tasks.values()]
        p.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load(self, path: str | Path) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        data = json.loads(p.read_text(encoding="utf-8"))
        count = 0
        for item in data:
            task = ScheduledTask.model_validate(item)
            self._tasks[task.id] = task
            count += 1
        return count
