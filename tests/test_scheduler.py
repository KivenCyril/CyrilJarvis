"""Tests for the advanced scheduler system."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jarvis.scheduler.scheduler import (
    Scheduler,
    ScheduledTask,
    TaskTrigger,
    TriggerType,
)


# ---------------------------------------------------------------------------
# ScheduledTask creation
# ---------------------------------------------------------------------------

class TestScheduledTask:
    def test_creation(self):
        trigger = TaskTrigger(
            trigger_type=TriggerType.INTERVAL, interval_seconds=60
        )
        task = ScheduledTask(
            name="heartbeat",
            description="Periodic check",
            trigger=trigger,
            action="hook:heartbeat",
        )
        assert task.name == "heartbeat"
        assert len(task.id) == 12
        assert task.enabled is True
        assert task.run_count == 0
        assert task.max_runs is None

    def test_event_trigger(self):
        trigger = TaskTrigger(
            trigger_type=TriggerType.EVENT, event_name="user_login"
        )
        task = ScheduledTask(
            name="greet", trigger=trigger, action="agent:greeter:hello"
        )
        assert task.trigger.event_name == "user_login"

    def test_once_trigger(self):
        run_at = datetime.now(timezone.utc) + timedelta(hours=1)
        trigger = TaskTrigger(trigger_type=TriggerType.ONCE, run_at=run_at)
        task = ScheduledTask(
            name="reminder", trigger=trigger, action="spec:remind me"
        )
        assert task.trigger.run_at == run_at

    def test_serialization(self):
        trigger = TaskTrigger(
            trigger_type=TriggerType.INTERVAL, interval_seconds=30
        )
        task = ScheduledTask(
            name="test", trigger=trigger, action="hook:ping"
        )
        data = task.model_dump_json()
        restored = ScheduledTask.model_validate_json(data)
        assert restored.name == "test"
        assert restored.trigger.interval_seconds == 30


# ---------------------------------------------------------------------------
# Scheduler core
# ---------------------------------------------------------------------------

class TestScheduler:
    def _make_task(
        self,
        name: str = "t",
        trigger_type: TriggerType = TriggerType.INTERVAL,
        **kwargs,
    ) -> ScheduledTask:
        trigger_kwargs: dict = {"trigger_type": trigger_type}
        if trigger_type == TriggerType.INTERVAL:
            trigger_kwargs["interval_seconds"] = kwargs.pop(
                "interval_seconds", 60
            )
        elif trigger_type == TriggerType.EVENT:
            trigger_kwargs["event_name"] = kwargs.pop(
                "event_name", "test_event"
            )
        elif trigger_type == TriggerType.CRON:
            trigger_kwargs["cron_expression"] = kwargs.pop(
                "cron_expression", "*/5 * * * *"
            )
        trigger = TaskTrigger(**trigger_kwargs)
        return ScheduledTask(
            name=name, trigger=trigger, action="hook:noop", **kwargs
        )

    def test_add_task(self):
        sched = Scheduler()
        task = self._make_task("job1")
        returned = sched.add_task(task)
        assert returned.id == task.id
        assert task.next_run is not None

    def test_remove_task(self):
        sched = Scheduler()
        task = sched.add_task(self._make_task("job"))
        sched.remove_task(task.id)
        assert sched.get_task(task.id) is None

    def test_enable_disable(self):
        sched = Scheduler()
        task = sched.add_task(self._make_task("job"))
        sched.disable_task(task.id)
        assert not task.enabled
        sched.enable_task(task.id)
        assert task.enabled

    def test_list_tasks(self):
        sched = Scheduler()
        sched.add_task(self._make_task("a"))
        sched.add_task(self._make_task("b"))
        sched.add_task(self._make_task("c"))
        assert len(sched.list_tasks()) == 3

    def test_get_task(self):
        sched = Scheduler()
        task = sched.add_task(self._make_task("findme"))
        assert sched.get_task(task.id) is task
        assert sched.get_task("nonexistent") is None

    @pytest.mark.asyncio
    async def test_trigger_event(self):
        sched = Scheduler()
        results: list[str] = []

        async def handler(action: str) -> str:
            results.append(action)
            return "ok"

        sched.set_action_handler(handler)
        sched.add_task(
            self._make_task(
                "evt1",
                trigger_type=TriggerType.EVENT,
                event_name="deploy",
            )
        )
        sched.add_task(
            self._make_task(
                "evt2",
                trigger_type=TriggerType.EVENT,
                event_name="deploy",
            )
        )
        sched.add_task(
            self._make_task(
                "evt3",
                trigger_type=TriggerType.EVENT,
                event_name="other",
            )
        )

        count = await sched.trigger_event("deploy")
        assert count == 2
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_trigger_event_disabled(self):
        sched = Scheduler()
        results: list[str] = []

        async def handler(action: str) -> str:
            results.append(action)
            return "ok"

        sched.set_action_handler(handler)
        task = sched.add_task(
            self._make_task(
                "disabled_evt",
                trigger_type=TriggerType.EVENT,
                event_name="fire",
            )
        )
        sched.disable_task(task.id)
        count = await sched.trigger_event("fire")
        assert count == 0

    def test_save_load_roundtrip(self, tmp_path: Path):
        sched = Scheduler()
        sched.add_task(self._make_task("persist1"))
        sched.add_task(
            self._make_task(
                "persist2",
                trigger_type=TriggerType.EVENT,
                event_name="x",
            )
        )
        file_path = tmp_path / "tasks.json"
        sched.save(file_path)

        sched2 = Scheduler()
        loaded = sched2.load(file_path)
        assert loaded == 2
        names = {t.name for t in sched2.list_tasks()}
        assert names == {"persist1", "persist2"}

    def test_load_missing_file(self, tmp_path: Path):
        sched = Scheduler()
        count = sched.load(tmp_path / "nope.json")
        assert count == 0


# ---------------------------------------------------------------------------
# Cron parsing
# ---------------------------------------------------------------------------

class TestCronParsing:
    def test_interval_cron(self):
        now = datetime(2025, 1, 1, 10, 3, 30, tzinfo=timezone.utc)
        result = Scheduler._next_cron_time("*/5 * * * *", now)
        assert result is not None
        assert result.minute == 5
        assert result > now

    def test_interval_cron_aligned(self):
        now = datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc)
        result = Scheduler._next_cron_time("*/10 * * * *", now)
        assert result is not None
        assert result > now
        assert result.minute == 20

    def test_fixed_time_cron(self):
        now = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        result = Scheduler._next_cron_time("30 9 * * *", now)
        assert result is not None
        assert result.hour == 9
        assert result.minute == 30

    def test_fixed_time_past(self):
        now = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = Scheduler._next_cron_time("30 9 * * *", now)
        assert result is not None
        assert result.day == 2  # next day

    def test_invalid_cron(self):
        now = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = Scheduler._next_cron_time("bad expression", now)
        assert result is None
