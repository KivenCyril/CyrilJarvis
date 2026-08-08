from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    BLOCKED = "blocked"        # waiting for dependencies
    READY = "ready"            # dependencies met, queued for execution
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class SpecStatus(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    REDIRECTED = "redirected"


class ChangeSource(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


class ChangeType(str, Enum):
    CONSTRAINT_ADDED = "constraint_added"
    CONSTRAINT_REMOVED = "constraint_removed"
    CONSTRAINT_MODIFIED = "constraint_modified"
    STEP_ADDED = "step_added"
    STEP_REMOVED = "step_removed"
    STEP_STATUS_CHANGED = "step_status_changed"
    STEP_MODIFIED = "step_modified"
    INTENT_CHANGED = "intent_changed"
    STATUS_CHANGED = "status_changed"
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"


class Constraint(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    content: str
    added_by: ChangeSource = ChangeSource.HUMAN
    active: bool = True


class Step(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    status: StepStatus = StepStatus.PENDING
    description: str = ""
    output: str | None = None
    error: str | None = None
    substeps: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)  # step IDs this step waits for
    assigned_agent: str | None = None  # which agent is handling this
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 2
    metadata: dict[str, Any] = Field(default_factory=dict)
    progress_pct: int = 0  # 0-100 for fine-grained progress


class SpecChange(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: ChangeSource
    change_type: ChangeType
    path: str
    old_value: Any = None
    new_value: Any = None


class SpecEvent(BaseModel):
    """SSE event emitted by the Streaming Spec engine."""
    event_type: str
    spec_id: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StreamingSpec(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    intent: str
    status: SpecStatus = SpecStatus.PLANNING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    constraints: list[Constraint] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    changelog: list[SpecChange] = Field(default_factory=list)
    version: int = 1  # increments on every edit
    tags: list[str] = Field(default_factory=list)

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def progress(self) -> str:
        """Human-readable progress: '3/7 (42%)'."""
        if not self.steps:
            return "0/0"
        done = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        total = len(self.steps)
        pct = int(done / total * 100) if total else 0
        return f"{done}/{total} ({pct}%)"

    @property
    def elapsed_time(self) -> float:
        """Seconds elapsed since spec creation."""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    # ── Step lookup helpers ─────────────────────────────────────────────

    def get_step(self, step_id: str) -> Step | None:
        """Find a step by its ID. Returns None if not found."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_ready_steps(self) -> list[Step]:
        """Return steps whose dependencies are all completed (status == READY)."""
        return [s for s in self.steps if s.status == StepStatus.READY]

    def get_blocked_steps(self) -> list[Step]:
        """Return steps that are waiting for dependencies."""
        return [s for s in self.steps if s.status == StepStatus.BLOCKED]

    # ── DAG validation ──────────────────────────────────────────────────

    def validate_dag(self) -> bool:
        """Detect cycles using DFS. Returns True if the DAG is valid (no cycles)."""
        step_map = {s.id: s for s in self.steps}
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def _dfs(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)
            step = step_map.get(step_id)
            if step:
                for dep_id in step.depends_on:
                    if dep_id not in visited:
                        if not _dfs(dep_id):
                            return False
                    elif dep_id in rec_stack:
                        return False  # cycle detected
            rec_stack.discard(step_id)
            return True

        for step in self.steps:
            if step.id not in visited:
                if not _dfs(step.id):
                    return False
        return True

    def topological_sort(self) -> list[Step]:
        """Kahn's algorithm for topological ordering.

        Returns steps ordered so that every step appears after all of its
        dependencies.  If the graph contains a cycle, the returned list will
        be shorter than ``self.steps``.
        """
        step_map = {s.id: s for s in self.steps}

        # in_degree = number of dependencies that exist in the graph
        in_degree: dict[str, int] = {}
        for step in self.steps:
            count = sum(1 for d in step.depends_on if d in step_map)
            in_degree[step.id] = count

        queue: deque[str] = deque(
            sid for sid, deg in in_degree.items() if deg == 0
        )
        result: list[Step] = []

        while queue:
            current = queue.popleft()
            if current in step_map:
                result.append(step_map[current])
            # For each step that depends on `current`, reduce its in-degree
            for step in self.steps:
                if current in step.depends_on:
                    in_degree[step.id] -= 1
                    if in_degree[step.id] == 0:
                        queue.append(step.id)

        return result

    def critical_path(self) -> list[Step]:
        """Return the longest dependency chain (critical path).

        Uses dynamic-programming on the topologically-sorted order.
        The 'length' is measured in number of steps.
        """
        if not self.steps:
            return []

        sorted_steps = self.topological_sort()
        if not sorted_steps:
            return []

        step_map = {s.id: s for s in self.steps}

        # dist[step_id] = length of the longest path ending at step_id
        dist: dict[str, int] = {}
        # predecessor on the longest path
        pred: dict[str, str | None] = {}

        for step in sorted_steps:
            if not step.depends_on or all(d not in step_map for d in step.depends_on):
                dist[step.id] = 1
                pred[step.id] = None
            else:
                best_len = 0
                best_pred: str | None = None
                for dep_id in step.depends_on:
                    if dep_id in dist and dist[dep_id] > best_len:
                        best_len = dist[dep_id]
                        best_pred = dep_id
                dist[step.id] = best_len + 1
                pred[step.id] = best_pred

        # Find the step with the longest path
        if not dist:
            return []

        end_id = max(dist, key=lambda sid: dist[sid])

        # Trace back to build the path
        path: list[Step] = []
        current: str | None = end_id
        while current is not None:
            if current in step_map:
                path.append(step_map[current])
            current = pred.get(current)
        path.reverse()
        return path

    # ── Dependency management ───────────────────────────────────────────

    def add_dependency(
        self,
        step_id: str,
        depends_on_id: str,
        source: ChangeSource = ChangeSource.AGENT,
    ) -> bool:
        """Add a dependency edge: step_id depends on depends_on_id.

        Returns True if the dependency was added successfully, False if
        it would create a cycle or either step doesn't exist.
        """
        step = self.get_step(step_id)
        dep_step = self.get_step(depends_on_id)
        if not step or not dep_step:
            return False

        if depends_on_id in step.depends_on:
            return True  # already exists, idempotent

        # Tentatively add and check for cycles
        step.depends_on.append(depends_on_id)
        if not self.validate_dag():
            step.depends_on.remove(depends_on_id)
            return False

        self._record_change(
            source,
            ChangeType.DEPENDENCY_ADDED,
            f"steps.{step_id}.depends_on",
            new_value=depends_on_id,
        )
        return True

    def remove_dependency(
        self,
        step_id: str,
        depends_on_id: str,
        source: ChangeSource = ChangeSource.AGENT,
    ) -> bool:
        """Remove a dependency edge. Returns True if it existed and was removed."""
        step = self.get_step(step_id)
        if not step or depends_on_id not in step.depends_on:
            return False

        step.depends_on.remove(depends_on_id)
        self._record_change(
            source,
            ChangeType.DEPENDENCY_REMOVED,
            f"steps.{step_id}.depends_on",
            old_value=depends_on_id,
        )
        return True

    # ── Changelog / mutation helpers ────────────────────────────────────

    def _record_change(
        self,
        source: ChangeSource,
        change_type: ChangeType,
        path: str,
        old_value: Any = None,
        new_value: Any = None,
    ) -> SpecChange:
        change = SpecChange(
            source=source,
            change_type=change_type,
            path=path,
            old_value=old_value,
            new_value=new_value,
        )
        self.changelog.append(change)
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        return change

    def add_constraint(
        self,
        content: str,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> Constraint:
        constraint = Constraint(content=content, added_by=source)
        self.constraints.append(constraint)
        self._record_change(
            source,
            ChangeType.CONSTRAINT_ADDED,
            f"constraints.{constraint.id}",
            new_value=content,
        )
        return constraint

    def remove_constraint(
        self,
        constraint_id: str,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> Constraint | None:
        for i, c in enumerate(self.constraints):
            if c.id == constraint_id:
                removed = self.constraints.pop(i)
                self._record_change(
                    source,
                    ChangeType.CONSTRAINT_REMOVED,
                    f"constraints.{constraint_id}",
                    old_value=removed.content,
                )
                return removed
        return None

    def add_step(
        self,
        name: str,
        description: str = "",
        source: ChangeSource = ChangeSource.AGENT,
        depends_on: list[str] | None = None,
    ) -> Step:
        step = Step(
            name=name,
            description=description,
            depends_on=depends_on or [],
        )
        self.steps.append(step)
        self._record_change(
            source,
            ChangeType.STEP_ADDED,
            f"steps.{step.id}",
            new_value=name,
        )
        return step

    def update_step_status(
        self,
        step_id: str,
        new_status: StepStatus,
        source: ChangeSource = ChangeSource.AGENT,
    ) -> Step | None:
        for step in self.steps:
            if step.id == step_id:
                old = step.status
                step.status = new_status
                # Track timing
                if new_status == StepStatus.EXECUTING and not step.started_at:
                    step.started_at = datetime.now(timezone.utc)
                elif new_status in (
                    StepStatus.COMPLETED,
                    StepStatus.FAILED,
                    StepStatus.SKIPPED,
                    StepStatus.CANCELLED,
                ):
                    step.completed_at = datetime.now(timezone.utc)
                self._record_change(
                    source,
                    ChangeType.STEP_STATUS_CHANGED,
                    f"steps.{step_id}.status",
                    old_value=old.value,
                    new_value=new_status.value,
                )
                return step
        return None

    def set_step_output(self, step_id: str, output: str) -> Step | None:
        for step in self.steps:
            if step.id == step_id:
                step.output = output
                return step
        return None

    def set_step_error(self, step_id: str, error: str) -> Step | None:
        for step in self.steps:
            if step.id == step_id:
                step.error = error
                return step
        return None

    def change_intent(
        self,
        new_intent: str,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> None:
        old = self.intent
        self.intent = new_intent
        self.status = SpecStatus.REDIRECTED
        self._record_change(
            source,
            ChangeType.INTENT_CHANGED,
            "intent",
            old_value=old,
            new_value=new_intent,
        )

    def pending_steps(self) -> list[Step]:
        return [
            s
            for s in self.steps
            if s.status
            in (StepStatus.PENDING, StepStatus.PLANNING, StepStatus.READY, StepStatus.BLOCKED)
        ]

    # ── DAG-aware readiness update ──────────────────────────────────────

    def update_step_readiness(self) -> None:
        """Recompute BLOCKED/READY status for all pending steps based on
        their dependency resolution.
        """
        completed_ids = {
            s.id for s in self.steps if s.status == StepStatus.COMPLETED
        }
        failed_ids = {
            s.id for s in self.steps if s.status in (StepStatus.FAILED, StepStatus.CANCELLED)
        }
        step_ids = {s.id for s in self.steps}

        for step in self.steps:
            if step.status not in (
                StepStatus.PENDING,
                StepStatus.BLOCKED,
                StepStatus.READY,
            ):
                continue

            # Filter to deps that actually exist in the graph
            valid_deps = [d for d in step.depends_on if d in step_ids]

            if not valid_deps:
                # No dependencies -- ready to run
                step.status = StepStatus.READY
            elif any(d in failed_ids for d in valid_deps):
                # A dependency failed -- this step is blocked (could also be
                # cancelled, but BLOCKED is safer for retry scenarios)
                step.status = StepStatus.BLOCKED
            elif all(d in completed_ids for d in valid_deps):
                step.status = StepStatus.READY
            else:
                step.status = StepStatus.BLOCKED
