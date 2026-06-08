"""Base types for the migration system."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MigrationStatus(str, Enum):
    """Lifecycle status of a migration run."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class MigrationStep(BaseModel):
    """A single step within a migration (e.g. 'memories', 'skills')."""

    name: str
    status: MigrationStatus = MigrationStatus.PENDING
    items_processed: int = 0
    items_total: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_ms: int = 0

    @property
    def success_rate(self) -> float:
        """Fraction of items successfully processed."""
        if self.items_total == 0:
            return 1.0
        return self.items_processed / self.items_total


class MigrationReport(BaseModel):
    """Aggregated report produced after a migration run."""

    source: str  # "hermes" or "openclaw"
    status: MigrationStatus = MigrationStatus.PENDING
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None
    steps: list[MigrationStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def success_rate(self) -> float:
        """Overall fraction of items processed across all steps."""
        total = sum(s.items_total for s in self.steps)
        processed = sum(s.items_processed for s in self.steps)
        return processed / total if total > 0 else 1.0

    @property
    def total_errors(self) -> int:
        return sum(len(s.errors) for s in self.steps)

    @property
    def total_items(self) -> int:
        return sum(s.items_total for s in self.steps)

    @property
    def total_processed(self) -> int:
        return sum(s.items_processed for s in self.steps)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Human-readable summary of the migration."""
        lines = [f"Migration from {self.source}: {self.status.value}"]
        for step in self.steps:
            lines.append(
                f"  {step.name}: {step.items_processed}/{step.items_total}"
                f" ({step.status.value})"
            )
            for err in step.errors[:3]:
                lines.append(f"    Error: {err}")
            if len(step.errors) > 3:
                lines.append(f"    ... and {len(step.errors) - 3} more errors")
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
            for w in self.warnings[:5]:
                lines.append(f"    - {w}")
        rate = self.success_rate
        lines.append(f"  Overall success rate: {rate:.0%}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for JSON export."""
        return self.model_dump(mode="json")
