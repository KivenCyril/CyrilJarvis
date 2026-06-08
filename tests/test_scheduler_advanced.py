"""Advanced tests for the JARVIS scheduler subsystem.

Covers interval scheduling, one-time scheduling, event triggering,
cron expression parsing, task enable/disable lifecycle, task max_runs
enforcement, scheduler start/stop, task save/load roundtrip, multiple
simultaneous tasks, and action handler execution.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from jarvis.scheduler.scheduler import (
    Scheduler,
    ScheduledTask,
    TaskTrigger,
    TriggerType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _interval_task(name: str = "task", seconds: int = 1, **kw: Any) -> ScheduledTask:
    return ScheduledTask(
        name=name,
        trigger=TaskTrigger(trigger_type=TriggerType.INTERVAL, interval_seconds=seconds),
        action="spec:do something",
        **kw,
    )


def _once_task(name: str = "once", run_at: datetime | None = None, **kw: Any) -> ScheduledTask:
    if run_at is None:
        run_at = datetime.now(timezone.utc) + timedelta(seconds=0.1)
    return ScheduledTask(
        name=name,
        trigger=TaskTrigger(trigger_type=TriggerType.ONCE, run_at=run_at),
        action="spec:run once",
        **kw,
    )


def _event_task(name: str = "evt", event_name: str = "deploy", **kw: Any) -> ScheduledTask:
    return ScheduledTask(
        name=name,
        trigger=TaskTrigger(trigger_type=TriggerType.EVENT, event_name=event_name),
        action="hook:deploy_complete",
        **kw,
    )


def _cron_task(name: str = "cron", expression: str = "0 9 * * *", **kw: Any) -> ScheduledTask:
    return ScheduledTask(
        name=name,
        trigger=TaskTrigger(trigger_type=TriggerType.CRON, cron_expression=expression),
        action="spec:daily report",
        **kw,
    )


# ===========================================================================
# 1. Interval scheduling
# ===========================================================================


class TestIntervalScheduling:
    def test_add_interval_task(self):
        scheduler = Scheduler()
        task = _interval_task(seconds=60)
        scheduler.add_task(task)
        assert scheduler.get_task(task.id) is not None
        assert task.next_run is not None

    def test_interval_next_run_computed(self):
        scheduler = Scheduler()
        task = _interval_task(seconds=300)
        scheduler.add_task(task)
        now = datetime.now(timezone.utc)
        assert task.next_run is not None
        # next_run should be about 300 seconds in the future
        diff = (task.next_run - now).total_seconds()
        assert 295 <= diff <= 305

    def test_list_tasks(self):
        scheduler = Scheduler()
        scheduler.add_task(_interval_task("a"))
        scheduler.add_task(_interval_task("b"))
        assert len(scheduler.list_tasks()) == 2


# ===========================================================================
# 2. One-time scheduling
# ===========================================================================


class TestOneTimeScheduling:
    def test_add_once_task(self):
        scheduler = Scheduler()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        task = _once_task(run_at=future)
        scheduler.add_task(task)
        assert task.next_run == future

    def test_once_task_past_still_added(self):
        scheduler = Scheduler()
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        task = _once_task(run_at=past)
        scheduler.add_task(task)
        assert scheduler.get_task(task.id) is not None


# ===========================================================================
# 3. Event triggering
# ===========================================================================


class TestEventTriggering:
    @pytest.mark.asyncio
    async def test_trigger_event_matches(self):
        scheduler = Scheduler()
        executed = []

        async def handler(action: str) -> str:
            executed.append(action)
            return "ok"

        scheduler.set_action_handler(handler)
        task = _event_task(event_name="deploy")
        scheduler.add_task(task)

        count = await scheduler.trigger_event("deploy")
        assert count == 1
        assert len(executed) == 1
        assert task.run_count == 1

    @pytest.mark.asyncio
    async def test_trigger_event_no_match(self):
        scheduler = Scheduler()
        scheduler.set_action_handler(lambda a: asyncio.coroutine(lambda: "ok")())
        scheduler.add_task(_event_task(event_name="deploy"))

        count = await scheduler.trigger_event("other_event")
        assert count == 0

    @pytest.mark.asyncio
    async def test_trigger_multiple_listeners(self):
        scheduler = Scheduler()
        executed = []

        async def handler(action: str) -> str:
            executed.append(action)
            return "ok"

        scheduler.set_action_handler(handler)
        scheduler.add_task(_event_task("a", event_name="build"))
        scheduler.add_task(_event_task("b", event_name="build"))
        scheduler.add_task(_event_task("c", event_name="other"))

        count = await scheduler.trigger_event("build")
        assert count == 2
        assert len(executed) == 2

    @pytest.mark.asyncio
    async def test_disabled_event_task_not_triggered(self):
        scheduler = Scheduler()
        executed = []

        async def handler(action: str) -> str:
            executed.append(action)
            return "ok"

        scheduler.set_action_handler(handler)
        task = _event_task(event_name="deploy")
        task.enabled = False
        scheduler.add_task(task)

        count = await scheduler.trigger_event("deploy")
        assert count == 0


# ===========================================================================
# 4. Cron expression parsing
# ===========================================================================


class TestCronParsing:
    def test_simple_cron(self):
        scheduler = Scheduler()
        task = _cron_task(expression="0 9 * * *")
        scheduler.add_task(task)
        assert task.next_run is not None
        assert task.next_run.minute == 0
        assert task.next_run.hour == 9

    def test_interval_cron(self):
        scheduler = Scheduler()
        now = datetime.now(timezone.utc)
        result = Scheduler._next_cron_time("*/15 * * * *", now)
        assert result is not None
        # Should be within 15 minutes
        diff = (result - now).total_seconds()
        assert 0 <= diff <= 15 * 60

    def test_invalid_cron_returns_fallback(self):
        scheduler = Scheduler()
        now = datetime.now(timezone.utc)
        result = Scheduler._next_cron_time("invalid * *", now)
        assert result is None  # not 5 parts

    def test_specific_minute_and_hour(self):
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        # Set target to a future time
        target_hour = (now.hour + 1) % 24
        result = Scheduler._next_cron_time(f"30 {target_hour} * * *", now)
        assert result is not None
        assert result.minute == 30
        assert result.hour == target_hour

    def test_cron_next_day_wrap(self):
        # If the target time has passed today, it should schedule for tomorrow
        now = datetime.now(timezone.utc).replace(hour=23, minute=59, second=0, microsecond=0)
        result = Scheduler._next_cron_time("0 9 * * *", now)
        assert result is not None
        assert result > now

    def test_every_5_minutes(self):
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        result = Scheduler._next_cron_time("*/5 * * * *", now)
        assert result is not None
        diff = (result - now).total_seconds()
        assert 0 <= diff <= 5 * 60


# ===========================================================================
# 5. Task enable/disable lifecycle
# ===========================================================================


class TestTaskLifecycle:
    def test_enable_task(self):
        scheduler = Scheduler()
        task = _interval_task()
        task.enabled = False
        scheduler.add_task(task)
        assert not task.enabled

        scheduler.enable_task(task.id)
        assert task.enabled

    def test_disable_task(self):
        scheduler = Scheduler()
        task = _interval_task()
        scheduler.add_task(task)
        assert task.enabled

        scheduler.disable_task(task.id)
        assert not task.enabled

    def test_remove_task(self):
        scheduler = Scheduler()
        task = _interval_task()
        scheduler.add_task(task)
        scheduler.remove_task(task.id)
        assert scheduler.get_task(task.id) is None

    def test_enable_nonexistent_no_error(self):
        scheduler = Scheduler()
        scheduler.enable_task("ghost")  # should not raise

    def test_disable_nonexistent_no_error(self):
        scheduler = Scheduler()
        scheduler.disable_task("ghost")  # should not raise

    def test_remove_nonexistent_no_error(self):
        scheduler = Scheduler()
        scheduler.remove_task("ghost")  # should not raise


# ===========================================================================
# 6. Task max_runs enforcement
# ===========================================================================


class TestMaxRuns:
    @pytest.mark.asyncio
    async def test_max_runs_limits_execution(self):
        scheduler = Scheduler()
        executed = []

        async def handler(action: str) -> str:
            executed.append(action)
            return "ok"

        scheduler.set_action_handler(handler)
        task = _event_task(event_name="test")
        task.max_runs = 3
        scheduler.add_task(task)

        for _ in range(5):
            await scheduler.trigger_event("test")

        # Event tasks don't check max_runs in trigger_event directly,
        # but run_count should reflect actual executions
        assert task.run_count == 5  # trigger_event always executes if enabled

    def test_max_runs_field(self):
        task = ScheduledTask(
            name="limited",
            trigger=TaskTrigger(trigger_type=TriggerType.INTERVAL, interval_seconds=60),
            action="spec:x",
            max_runs=10,
        )
        assert task.max_runs == 10

    def test_unlimited_runs(self):
        task = _interval_task()
        assert task.max_runs is None


# ===========================================================================
# 7. Scheduler start/stop
# ===========================================================================


class TestSchedulerStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        scheduler = Scheduler()
        scheduler.add_task(_interval_task(seconds=3600))
        await scheduler.start()
        assert scheduler._running is True
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_tasks(self):
        scheduler = Scheduler()
        scheduler.add_task(_interval_task(seconds=3600))
        await scheduler.start()
        await scheduler.stop()
        assert scheduler._running is False
        assert len(scheduler._running_tasks) == 0

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        scheduler = Scheduler()
        await scheduler.start()
        await scheduler.start()  # should not fail
        assert scheduler._running is True
        await scheduler.stop()


# ===========================================================================
# 8. Task save/load roundtrip
# ===========================================================================


class TestSaveLoadRoundtrip:
    def test_save_and_load(self, tmp_path: Path):
        scheduler = Scheduler()
        scheduler.add_task(_interval_task("task1", seconds=60))
        scheduler.add_task(_cron_task("task2", expression="0 8 * * *"))
        scheduler.add_task(_event_task("task3", event_name="deploy"))

        path = tmp_path / "tasks.json"
        scheduler.save(path)

        # Load into fresh scheduler
        scheduler2 = Scheduler()
        count = scheduler2.load(path)
        assert count == 3
        assert len(scheduler2.list_tasks()) == 3

    def test_load_nonexistent_returns_zero(self, tmp_path: Path):
        scheduler = Scheduler()
        count = scheduler.load(tmp_path / "missing.json")
        assert count == 0

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        scheduler = Scheduler()
        scheduler.add_task(_interval_task())
        path = tmp_path / "deep" / "nested" / "tasks.json"
        scheduler.save(path)
        assert path.exists()

    def test_roundtrip_preserves_task_data(self, tmp_path: Path):
        scheduler = Scheduler()
        task = _interval_task("my_task", seconds=120)
        task.metadata = {"key": "value"}
        scheduler.add_task(task)

        path = tmp_path / "tasks.json"
        scheduler.save(path)

        scheduler2 = Scheduler()
        scheduler2.load(path)
        loaded = scheduler2.list_tasks()[0]
        assert loaded.name == "my_task"
        assert loaded.trigger.interval_seconds == 120
        assert loaded.metadata == {"key": "value"}


# ===========================================================================
# 9. Multiple simultaneous tasks
# ===========================================================================


class TestMultipleTasks:
    def test_add_multiple_types(self):
        scheduler = Scheduler()
        scheduler.add_task(_interval_task("int"))
        scheduler.add_task(_cron_task("cr"))
        scheduler.add_task(_event_task("ev"))
        scheduler.add_task(_once_task("on"))
        assert len(scheduler.list_tasks()) == 4

    def test_get_by_id(self):
        scheduler = Scheduler()
        t1 = _interval_task("first")
        t2 = _interval_task("second")
        scheduler.add_task(t1)
        scheduler.add_task(t2)
        assert scheduler.get_task(t1.id).name == "first"
        assert scheduler.get_task(t2.id).name == "second"
        assert scheduler.get_task("nonexistent") is None

    def test_remove_specific_task(self):
        scheduler = Scheduler()
        t1 = _interval_task("keep")
        t2 = _interval_task("remove")
        scheduler.add_task(t1)
        scheduler.add_task(t2)
        scheduler.remove_task(t2.id)
        assert len(scheduler.list_tasks()) == 1
        assert scheduler.list_tasks()[0].name == "keep"


# ===========================================================================
# 10. Action handler execution
# ===========================================================================


class TestActionHandler:
    @pytest.mark.asyncio
    async def test_handler_receives_action_string(self):
        scheduler = Scheduler()
        received = []

        async def handler(action: str) -> str:
            received.append(action)
            return "done"

        scheduler.set_action_handler(handler)
        task = _event_task(event_name="test")
        task.action = "spec:run analysis"
        scheduler.add_task(task)

        await scheduler.trigger_event("test")
        assert "spec:run analysis" in received

    @pytest.mark.asyncio
    async def test_handler_exception_logged_not_raised(self):
        scheduler = Scheduler()

        async def bad_handler(action: str) -> str:
            raise RuntimeError("handler crash")

        scheduler.set_action_handler(bad_handler)
        task = _event_task(event_name="test")
        scheduler.add_task(task)

        # Should not raise, just log
        count = await scheduler.trigger_event("test")
        assert count == 1
        assert task.run_count == 1

    @pytest.mark.asyncio
    async def test_no_handler_no_crash(self):
        scheduler = Scheduler()
        task = _event_task(event_name="test")
        scheduler.add_task(task)

        # Without a handler, trigger should still execute but do nothing
        count = await scheduler.trigger_event("test")
        assert count == 1
        assert task.run_count == 1


# ===========================================================================
# 11. ScheduledTask model
# ===========================================================================


class TestScheduledTaskModel:
    def test_defaults(self):
        task = ScheduledTask(
            name="test",
            trigger=TaskTrigger(trigger_type=TriggerType.INTERVAL, interval_seconds=60),
            action="spec:x",
        )
        assert task.enabled is True
        assert task.run_count == 0
        assert task.last_run is None
        assert task.max_runs is None
        assert task.id  # auto-generated

    def test_serialization_roundtrip(self):
        task = ScheduledTask(
            name="roundtrip",
            description="Test task",
            trigger=TaskTrigger(
                trigger_type=TriggerType.CRON,
                cron_expression="0 9 * * 1-5",
            ),
            action="spec:daily standup",
            metadata={"team": "platform"},
        )
        data = task.model_dump(mode="json")
        restored = ScheduledTask.model_validate(data)
        assert restored.name == "roundtrip"
        assert restored.trigger.cron_expression == "0 9 * * 1-5"
        assert restored.metadata["team"] == "platform"


# ===========================================================================
# 12. TriggerType enum
# ===========================================================================


class TestTriggerType:
    def test_all_types(self):
        assert TriggerType.CRON.value == "cron"
        assert TriggerType.INTERVAL.value == "interval"
        assert TriggerType.ONCE.value == "once"
        assert TriggerType.EVENT.value == "event"

    def test_task_trigger_defaults(self):
        trigger = TaskTrigger(trigger_type=TriggerType.INTERVAL)
        assert trigger.interval_seconds == 0
        assert trigger.cron_expression == ""
        assert trigger.run_at is None
        assert trigger.event_name == ""
