"""Batch processing system tests.

Tests batch job creation, concurrency control, progress tracking,
error handling, retry logic, and result aggregation.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Batch Processing Models
# ---------------------------------------------------------------------------

@dataclass
class BatchItem:
    id: str
    task: str
    priority: int = 0
    status: str = "pending"  # pending, running, completed, failed, skipped, cancelled
    result: str = ""
    error: str | None = None
    start_time: float = 0
    end_time: float = 0
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return round((self.end_time - self.start_time) * 1000, 2)
        return 0

    @property
    def can_retry(self) -> bool:
        return self.status == "failed" and self.retry_count < self.max_retries

    def start(self) -> None:
        self.status = "running"
        self.start_time = time.time()

    def complete(self, result: str) -> None:
        self.status = "completed"
        self.result = result
        self.end_time = time.time()

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.error = error
        self.end_time = time.time()

    def skip(self, reason: str = "") -> None:
        self.status = "skipped"
        self.result = reason

    def cancel(self) -> None:
        self.status = "cancelled"

    def retry(self) -> None:
        self.retry_count += 1
        self.status = "pending"
        self.error = None


@dataclass
class BatchJob:
    id: str
    name: str
    items: list[BatchItem] = field(default_factory=list)
    status: str = "created"  # created, running, completed, failed, cancelled
    max_concurrent: int = 5
    stop_on_error: bool = False
    created_at: float = 0
    completed_at: float = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def completed_count(self) -> int:
        return sum(1 for i in self.items if i.status == "completed")

    @property
    def failed_count(self) -> int:
        return sum(1 for i in self.items if i.status == "failed")

    @property
    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.status == "pending")

    @property
    def running_count(self) -> int:
        return sum(1 for i in self.items if i.status == "running")

    @property
    def progress(self) -> str:
        done = self.completed_count + sum(1 for i in self.items if i.status in ("skipped", "cancelled"))
        return f"{done}/{self.total}"

    @property
    def completion_percentage(self) -> float:
        if not self.items:
            return 0.0
        done = sum(1 for i in self.items if i.status in ("completed", "skipped", "cancelled", "failed"))
        return round(done / self.total * 100, 1)

    @property
    def success_rate(self) -> float:
        finished = self.completed_count + self.failed_count
        if finished == 0:
            return 0.0
        return round(self.completed_count / finished * 100, 1)

    @property
    def is_done(self) -> bool:
        return all(i.status in ("completed", "failed", "skipped", "cancelled") for i in self.items)

    @property
    def total_duration_ms(self) -> float:
        return sum(i.duration_ms for i in self.items)

    @property
    def avg_duration_ms(self) -> float:
        durations = [i.duration_ms for i in self.items if i.duration_ms > 0]
        return round(sum(durations) / len(durations), 2) if durations else 0

    def add_item(self, item_id: str, task: str, priority: int = 0, **kwargs) -> BatchItem:
        item = BatchItem(id=item_id, task=task, priority=priority, **kwargs)
        self.items.append(item)
        return item

    def get_item(self, item_id: str) -> BatchItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def get_next_items(self, count: int = 1) -> list[BatchItem]:
        pending = [i for i in self.items if i.status == "pending"]
        pending.sort(key=lambda i: i.priority, reverse=True)
        return pending[:count]

    def cancel_pending(self) -> int:
        cancelled = 0
        for item in self.items:
            if item.status == "pending":
                item.cancel()
                cancelled += 1
        return cancelled

    def retry_failed(self) -> int:
        retried = 0
        for item in self.items:
            if item.can_retry:
                item.retry()
                retried += 1
        return retried

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "total": self.total,
            "completed": self.completed_count,
            "failed": self.failed_count,
            "pending": self.pending_count,
            "running": self.running_count,
            "progress": self.progress,
            "completion_pct": self.completion_percentage,
            "success_rate": self.success_rate,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": self.avg_duration_ms,
        }


class BatchScheduler:
    """Schedule and manage batch jobs."""

    def __init__(self):
        self.jobs: dict[str, BatchJob] = {}
        self._counter = 0

    def create_job(self, name: str, max_concurrent: int = 5,
                   stop_on_error: bool = False) -> BatchJob:
        self._counter += 1
        job = BatchJob(
            id=f"batch-{self._counter:04d}",
            name=name,
            max_concurrent=max_concurrent,
            stop_on_error=stop_on_error,
        )
        self.jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> BatchJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self, status: str | None = None) -> list[BatchJob]:
        result = list(self.jobs.values())
        if status:
            result = [j for j in result if j.status == status]
        return result

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job:
            job.status = "cancelled"
            job.cancel_pending()
            return True
        return False

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_jobs": len(self.jobs),
            "running": sum(1 for j in self.jobs.values() if j.status == "running"),
            "completed": sum(1 for j in self.jobs.values() if j.status == "completed"),
            "total_items": sum(j.total for j in self.jobs.values()),
        }


# ---------------------------------------------------------------------------
# Tests: BatchItem
# ---------------------------------------------------------------------------

class TestBatchItem:
    def test_create_item(self):
        item = BatchItem(id="i1", task="test")
        assert item.status == "pending"
        assert item.duration_ms == 0

    def test_start_item(self):
        item = BatchItem(id="i1", task="test")
        item.start()
        assert item.status == "running"
        assert item.start_time > 0

    def test_complete_item(self):
        item = BatchItem(id="i1", task="test")
        item.start()
        item.complete("done")
        assert item.status == "completed"
        assert item.result == "done"
        assert item.duration_ms >= 0

    def test_fail_item(self):
        item = BatchItem(id="i1", task="test")
        item.start()
        item.fail("error")
        assert item.status == "failed"
        assert item.error == "error"

    def test_skip_item(self):
        item = BatchItem(id="i1", task="test")
        item.skip("not needed")
        assert item.status == "skipped"

    def test_cancel_item(self):
        item = BatchItem(id="i1", task="test")
        item.cancel()
        assert item.status == "cancelled"

    def test_can_retry(self):
        item = BatchItem(id="i1", task="test", max_retries=3)
        item.fail("error")
        assert item.can_retry is True
        item.retry_count = 3
        assert item.can_retry is False

    def test_retry(self):
        item = BatchItem(id="i1", task="test")
        item.fail("error")
        item.retry()
        assert item.status == "pending"
        assert item.retry_count == 1
        assert item.error is None

    def test_priority(self):
        items = [
            BatchItem(id="low", task="low", priority=1),
            BatchItem(id="high", task="high", priority=10),
            BatchItem(id="mid", task="mid", priority=5),
        ]
        sorted_items = sorted(items, key=lambda i: i.priority, reverse=True)
        assert sorted_items[0].id == "high"
        assert sorted_items[-1].id == "low"


# ---------------------------------------------------------------------------
# Tests: BatchJob
# ---------------------------------------------------------------------------

class TestBatchJob:
    def test_create_job(self):
        job = BatchJob(id="j1", name="test")
        assert job.total == 0
        assert job.status == "created"

    def test_add_items(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task 1")
        job.add_item("i2", "task 2")
        assert job.total == 2

    def test_get_item(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task 1")
        item = job.get_item("i1")
        assert item is not None
        assert item.task == "task 1"

    def test_get_nonexistent_item(self):
        job = BatchJob(id="j1", name="test")
        assert job.get_item("missing") is None

    def test_progress(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task 1")
        job.add_item("i2", "task 2")
        job.add_item("i3", "task 3")
        assert job.progress == "0/3"
        job.items[0].complete("done")
        assert job.progress == "1/3"

    def test_completion_percentage(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task 1")
        job.add_item("i2", "task 2")
        assert job.completion_percentage == 0.0
        job.items[0].complete("done")
        assert job.completion_percentage == 50.0

    def test_success_rate(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "ok")
        job.add_item("i2", "fail")
        job.items[0].complete("done")
        job.items[1].fail("error")
        assert job.success_rate == 50.0

    def test_is_done(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task")
        assert job.is_done is False
        job.items[0].complete("done")
        assert job.is_done is True

    def test_get_next_items_by_priority(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("low", "low priority", priority=1)
        job.add_item("high", "high priority", priority=10)
        job.add_item("mid", "mid priority", priority=5)
        next_items = job.get_next_items(2)
        assert next_items[0].id == "high"
        assert next_items[1].id == "mid"

    def test_cancel_pending(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task 1")
        job.add_item("i2", "task 2")
        job.items[0].complete("done")
        cancelled = job.cancel_pending()
        assert cancelled == 1
        assert job.items[1].status == "cancelled"

    def test_retry_failed(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task 1")
        job.add_item("i2", "task 2")
        job.items[0].fail("error")
        job.items[1].complete("ok")
        retried = job.retry_failed()
        assert retried == 1
        assert job.items[0].status == "pending"
        assert job.items[0].retry_count == 1

    def test_summary(self):
        job = BatchJob(id="j1", name="test")
        job.add_item("i1", "task 1")
        job.add_item("i2", "task 2")
        job.items[0].complete("done")
        s = job.summary()
        assert s["total"] == 2
        assert s["completed"] == 1
        assert s["pending"] == 1

    def test_empty_job(self):
        job = BatchJob(id="j1", name="empty")
        assert job.is_done is True  # No items = done
        assert job.success_rate == 0.0


# ---------------------------------------------------------------------------
# Tests: BatchScheduler
# ---------------------------------------------------------------------------

class TestBatchScheduler:
    def test_create_job(self):
        sched = BatchScheduler()
        job = sched.create_job("test")
        assert job.id == "batch-0001"
        assert job.name == "test"

    def test_get_job(self):
        sched = BatchScheduler()
        job = sched.create_job("test")
        found = sched.get_job(job.id)
        assert found is not None
        assert found.name == "test"

    def test_get_nonexistent(self):
        sched = BatchScheduler()
        assert sched.get_job("missing") is None

    def test_list_jobs(self):
        sched = BatchScheduler()
        sched.create_job("a")
        sched.create_job("b")
        assert len(sched.list_jobs()) == 2

    def test_list_by_status(self):
        sched = BatchScheduler()
        j1 = sched.create_job("a")
        j2 = sched.create_job("b")
        j1.status = "completed"
        assert len(sched.list_jobs(status="completed")) == 1

    def test_cancel_job(self):
        sched = BatchScheduler()
        job = sched.create_job("test")
        job.add_item("i1", "task")
        assert sched.cancel_job(job.id) is True
        assert job.status == "cancelled"
        assert job.items[0].status == "cancelled"

    def test_cancel_nonexistent(self):
        sched = BatchScheduler()
        assert sched.cancel_job("missing") is False

    def test_stats(self):
        sched = BatchScheduler()
        j1 = sched.create_job("a")
        j1.add_item("i1", "task")
        j1.add_item("i2", "task")
        j2 = sched.create_job("b")
        j2.add_item("i3", "task")
        stats = sched.stats
        assert stats["total_jobs"] == 2
        assert stats["total_items"] == 3

    def test_multiple_jobs_unique_ids(self):
        sched = BatchScheduler()
        j1 = sched.create_job("a")
        j2 = sched.create_job("b")
        assert j1.id != j2.id


# ---------------------------------------------------------------------------
# Tests: Batch Processing Flow
# ---------------------------------------------------------------------------

class TestBatchProcessingFlow:
    def test_full_successful_flow(self):
        job = BatchJob(id="j1", name="full flow")
        for i in range(5):
            job.add_item(f"i{i}", f"task {i}")

        job.status = "running"
        for item in job.items:
            item.start()
            item.complete(f"Result for {item.task}")

        assert job.is_done is True
        assert job.success_rate == 100.0
        assert job.completed_count == 5

    def test_partial_failure_flow(self):
        job = BatchJob(id="j1", name="partial fail")
        for i in range(4):
            job.add_item(f"i{i}", f"task {i}")

        job.items[0].complete("ok")
        job.items[1].complete("ok")
        job.items[2].fail("error")
        job.items[3].complete("ok")

        assert job.success_rate == 75.0
        assert job.failed_count == 1
        assert job.completed_count == 3

    def test_retry_and_succeed(self):
        job = BatchJob(id="j1", name="retry")
        job.add_item("i1", "flaky task", max_retries=3)

        # First attempt fails
        job.items[0].fail("timeout")
        assert job.items[0].can_retry is True

        # Retry
        job.items[0].retry()
        assert job.items[0].retry_count == 1
        assert job.items[0].status == "pending"

        # Second attempt succeeds
        job.items[0].complete("finally done")
        assert job.items[0].status == "completed"

    def test_stop_on_error(self):
        job = BatchJob(id="j1", name="stop on error", stop_on_error=True)
        job.add_item("i1", "task 1")
        job.add_item("i2", "task 2")
        job.add_item("i3", "task 3")

        job.items[0].fail("critical error")
        # Should cancel remaining
        if job.stop_on_error and job.failed_count > 0:
            job.cancel_pending()
        assert job.items[1].status == "cancelled"
        assert job.items[2].status == "cancelled"

    def test_mixed_statuses(self):
        job = BatchJob(id="j1", name="mixed")
        job.add_item("i1", "complete")
        job.add_item("i2", "fail")
        job.add_item("i3", "skip")
        job.add_item("i4", "cancel")
        job.items[0].complete("ok")
        job.items[1].fail("err")
        job.items[2].skip("n/a")
        job.items[3].cancel()
        assert job.is_done is True
        assert job.completion_percentage == 100.0
