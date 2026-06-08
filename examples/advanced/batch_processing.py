"""Batch Processing Demo.

Shows how to process multiple Streaming Specs in batch mode,
with concurrency control, progress tracking, error handling,
and result aggregation.

Usage:
    python examples/advanced/batch_processing.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class BatchItem:
    """A single item in a batch processing job."""
    id: str
    intent: str
    priority: int = 0  # Higher = more important
    status: str = "pending"  # pending, running, completed, failed, skipped
    output: str = ""
    error: str | None = None
    start_time: float = 0
    end_time: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return round((self.end_time - self.start_time) * 1000, 2)
        return 0


@dataclass
class BatchResult:
    """Aggregated results from a batch processing run."""
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_ms: float = 0
    avg_duration_ms: float = 0
    items: list[BatchItem] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def add_item(self, item: BatchItem) -> None:
        self.items.append(item)
        self.total += 1
        if item.status == "completed":
            self.completed += 1
        elif item.status == "failed":
            self.failed += 1
            self.errors.append({"id": item.id, "error": item.error})
        elif item.status == "skipped":
            self.skipped += 1

    def finalize(self) -> None:
        durations = [i.duration_ms for i in self.items if i.duration_ms > 0]
        self.total_duration_ms = sum(durations)
        self.avg_duration_ms = round(self.total_duration_ms / len(durations), 2) if durations else 0

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.completed / self.total * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "success_rate": self.success_rate,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": self.avg_duration_ms,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Batch processor
# ---------------------------------------------------------------------------

class BatchProcessor:
    """Process multiple specs in batch with concurrency control."""

    def __init__(
        self,
        max_concurrent: int = 5,
        stop_on_error: bool = False,
        timeout_seconds: float = 30.0,
        dry_run: bool = False,
    ):
        self.max_concurrent = max_concurrent
        self.stop_on_error = stop_on_error
        self.timeout_seconds = timeout_seconds
        self.dry_run = dry_run
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._should_stop = False
        self._progress_callback: Any = None

    def on_progress(self, callback) -> None:
        """Set a callback for progress updates."""
        self._progress_callback = callback

    async def process(self, items: list[BatchItem]) -> BatchResult:
        """Process all items in batch with concurrency control."""
        result = BatchResult()

        # Sort by priority (higher first)
        sorted_items = sorted(items, key=lambda x: x.priority, reverse=True)

        print(f"Starting batch processing: {len(sorted_items)} items")
        print(f"  Max concurrent: {self.max_concurrent}")
        print(f"  Timeout: {self.timeout_seconds}s")
        print(f"  Dry run: {self.dry_run}")
        print()

        start_time = time.time()

        # Process items concurrently with semaphore
        tasks = [
            self._process_item(item, i, len(sorted_items))
            for i, item in enumerate(sorted_items)
        ]

        completed_items = await asyncio.gather(*tasks, return_exceptions=True)

        for item_or_error in completed_items:
            if isinstance(item_or_error, BatchItem):
                result.add_item(item_or_error)
            elif isinstance(item_or_error, Exception):
                # Wrap exception in a failed item
                error_item = BatchItem(
                    id="unknown", intent="error",
                    status="failed", error=str(item_or_error),
                )
                result.add_item(error_item)

        result.finalize()

        total_time = round((time.time() - start_time) * 1000, 2)
        print(f"\nBatch processing complete in {total_time}ms")

        return result

    async def _process_item(self, item: BatchItem, index: int, total: int) -> BatchItem:
        """Process a single item with semaphore control."""
        if self._should_stop:
            item.status = "skipped"
            return item

        async with self._semaphore:
            if self._should_stop:
                item.status = "skipped"
                return item

            item.status = "running"
            item.start_time = time.time()

            # Report progress
            if self._progress_callback:
                self._progress_callback(index + 1, total, item.id, "running")

            try:
                if self.dry_run:
                    item.output = f"[DRY RUN] Would process: {item.intent}"
                    item.status = "completed"
                else:
                    # Simulate spec processing
                    result = await self._execute_spec(item)
                    item.output = result
                    item.status = "completed"

            except asyncio.TimeoutError:
                item.status = "failed"
                item.error = f"Timed out after {self.timeout_seconds}s"
                if self.stop_on_error:
                    self._should_stop = True

            except Exception as exc:
                item.status = "failed"
                item.error = str(exc)
                if self.stop_on_error:
                    self._should_stop = True

            item.end_time = time.time()

            # Report progress
            status_icon = "v" if item.status == "completed" else "x"
            print(f"  [{status_icon}] [{index+1}/{total}] {item.id}: {item.status} ({item.duration_ms}ms)")

            return item

    async def _execute_spec(self, item: BatchItem) -> str:
        """Simulate executing a spec (in real code, calls JarvisApp)."""
        # Simulate variable processing time
        import random
        delay = 0.1 + random.random() * 0.5
        await asyncio.sleep(delay)

        # Simulate occasional failures
        if random.random() < 0.1:
            raise RuntimeError(f"Simulated failure for {item.id}")

        return f"Completed: {item.intent} (processed in {delay:.2f}s)"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def progress_callback(current: int, total: int, item_id: str, status: str) -> None:
    """Print progress updates."""
    pct = round(current / total * 100)
    bar_len = 20
    filled = int(bar_len * current / total)
    bar = "X" * filled + "." * (bar_len - filled)
    print(f"  Progress: [{bar}] {pct}% ({current}/{total}) - {item_id}: {status}")


async def main():
    """Demonstrate batch processing."""
    # Create batch items
    intents = [
        ("code-review-1", "Review authentication module", 3),
        ("code-review-2", "Review database queries", 2),
        ("code-review-3", "Review API endpoints", 2),
        ("bug-fix-1", "Fix memory leak in session handler", 5),
        ("bug-fix-2", "Fix race condition in cache", 4),
        ("feature-1", "Implement user notifications", 1),
        ("feature-2", "Add export to CSV functionality", 1),
        ("docs-1", "Update API documentation", 0),
        ("docs-2", "Write migration guide", 0),
        ("test-1", "Add integration tests for auth", 3),
        ("test-2", "Add load tests for API", 2),
        ("refactor-1", "Refactor error handling", 1),
        ("deploy-1", "Prepare production deployment", 4),
        ("security-1", "Security audit for auth flow", 5),
        ("perf-1", "Optimize database queries", 3),
    ]

    items = [
        BatchItem(id=id, intent=intent, priority=priority)
        for id, intent, priority in intents
    ]

    # Process batch
    processor = BatchProcessor(
        max_concurrent=4,
        stop_on_error=False,
        timeout_seconds=30.0,
    )
    processor.on_progress(progress_callback)

    result = await processor.process(items)

    # Print summary
    print(f"\n{'='*50}")
    print("Batch Processing Summary:")
    print(f"{'='*50}")
    summary = result.to_dict()
    for key, value in summary.items():
        if key != "errors":
            print(f"  {key}: {value}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err['id']}: {err['error']}")

    # Print top-5 slowest items
    slowest = sorted(result.items, key=lambda x: x.duration_ms, reverse=True)[:5]
    print(f"\nSlowest items:")
    for item in slowest:
        print(f"  - {item.id}: {item.duration_ms}ms ({item.status})")


if __name__ == "__main__":
    asyncio.run(main())
