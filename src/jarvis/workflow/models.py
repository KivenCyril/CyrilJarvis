"""Workflow data models for the JARVIS workflow engine.

Provides rich data structures for defining complex workflows with
conditional branching, loops, sub-workflows, approval gates, and
data transformation between steps.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Status of a workflow execution."""

    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepType(str, Enum):
    """Types of workflow steps."""

    ACTION = "action"  # Execute an agent task
    CONDITION = "condition"  # Branch based on condition
    LOOP = "loop"  # Repeat steps
    PARALLEL = "parallel"  # Execute steps in parallel
    SUB_WORKFLOW = "sub_workflow"  # Execute another workflow
    WAIT = "wait"  # Wait for event or time
    APPROVAL = "approval"  # Wait for human approval
    TRANSFORM = "transform"  # Transform data between steps


class WorkflowVariable(BaseModel):
    """Variable that flows through the workflow.

    Variables carry data between workflow steps and can be set from
    workflow input or produced by step outputs.
    """

    name: str
    value: Any = None
    var_type: str = "string"  # string, number, boolean, json, list
    description: str = ""
    required: bool = False
    default: Any = None

    def resolve(self) -> Any:
        """Return the effective value: explicit value, default, or None."""
        if self.value is not None:
            return self.value
        return self.default

    def validate_type(self) -> bool:
        """Check whether the current value matches the declared type."""
        val = self.resolve()
        if val is None:
            return not self.required
        type_checks: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "json": dict,
            "list": list,
        }
        expected = type_checks.get(self.var_type)
        if expected is None:
            return True  # unknown type -> accept anything
        return isinstance(val, expected)


class WorkflowStep(BaseModel):
    """A step in a workflow with rich execution semantics.

    Each step has a type that determines how it is executed by the engine.
    Steps form a DAG through ``depends_on`` references.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    step_type: StepType = StepType.ACTION
    description: str = ""

    # Execution
    agent: str = ""  # which agent handles this step
    action: str = ""  # what to do
    tool: str = ""  # specific tool to use
    tool_args: dict[str, Any] = Field(default_factory=dict)

    # DAG
    depends_on: list[str] = Field(default_factory=list)

    # Conditional branching
    condition: str = ""  # expression to evaluate
    on_true: str = ""  # step ID to go to if true
    on_false: str = ""  # step ID to go to if false

    # Loop
    loop_over: str = ""  # variable name containing list to iterate
    loop_variable: str = "item"  # variable name for current item
    loop_body: list[str] = Field(default_factory=list)  # step IDs in loop body
    max_iterations: int = 100

    # Sub-workflow
    sub_workflow_id: str = ""
    sub_workflow_input: dict[str, str] = Field(default_factory=dict)

    # Wait / Approval
    wait_seconds: int = 0
    wait_event: str = ""
    approval_message: str = ""

    # Transform
    transform_expression: str = ""  # how to transform input to output

    # State
    status: str = "pending"
    output: Any = None
    error: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 2

    # Metadata
    timeout_seconds: int = 300
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        return self.status in ("completed", "skipped")

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def duration_seconds(self) -> float | None:
        """Return elapsed seconds if the step has finished."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def mark_running(self) -> None:
        self.status = "running"
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self, output: Any = None) -> None:
        self.status = "completed"
        self.output = output
        self.completed_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.now(timezone.utc)

    def mark_skipped(self) -> None:
        self.status = "skipped"
        self.completed_at = datetime.now(timezone.utc)

    def reset(self) -> None:
        """Reset step to pending state for re-execution."""
        self.status = "pending"
        self.output = None
        self.error = ""
        self.started_at = None
        self.completed_at = None
        self.retry_count = 0


class ConditionalBranch(BaseModel):
    """A conditional branch in a workflow.

    Evaluates ``condition`` at runtime.  If true, the ``true_branch``
    step IDs are enqueued; otherwise ``false_branch`` step IDs.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    condition: str  # e.g. "steps.analyze.output.score > 0.8"
    true_branch: list[str] = Field(default_factory=list)
    false_branch: list[str] = Field(default_factory=list)


class LoopStep(BaseModel):
    """Configuration for a loop step.

    Iterates ``loop_over`` (a variable name holding a list) and
    executes ``body_steps`` for each element.
    """

    loop_over: str
    loop_variable: str = "item"
    body_steps: list[str] = Field(default_factory=list)
    max_iterations: int = 100


class SubWorkflow(BaseModel):
    """Reference to a sub-workflow to be launched from a parent workflow."""

    workflow_id: str
    input_mapping: dict[str, str] = Field(default_factory=dict)
    output_mapping: dict[str, str] = Field(default_factory=dict)


class WorkflowTrigger(BaseModel):
    """Defines when a workflow should be triggered.

    Supports cron schedules, event patterns, and webhook URLs.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    trigger_type: str = "manual"  # manual, cron, event, webhook
    cron: str = ""
    event_pattern: str = ""
    webhook_path: str = ""
    enabled: bool = True
    workflow_id: str = ""
    input_template: dict[str, Any] = Field(default_factory=dict)


# ======================================================================
# Workflow
# ======================================================================


class Workflow(BaseModel):
    """A complete workflow definition with rich execution semantics.

    Workflows extend Streaming Specs with:
    - Conditional branching (if/else)
    - Loops (for-each, while)
    - Sub-workflows (composition)
    - Data flow between steps (variables)
    - Wait/approval gates
    - Error handling and rollback
    - Templates for reuse
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    description: str = ""
    version: str = "1.0.0"
    status: WorkflowStatus = WorkflowStatus.DRAFT

    # Structure
    steps: list[WorkflowStep] = Field(default_factory=list)
    variables: list[WorkflowVariable] = Field(default_factory=list)
    branches: list[ConditionalBranch] = Field(default_factory=list)

    # Execution context
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)

    # Error handling
    on_error: str = "stop"  # stop, retry, skip, rollback
    rollback_steps: list[str] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = ""
    tags: list[str] = Field(default_factory=list)
    parent_workflow_id: str | None = None

    # ------------------------------------------------------------------
    # Step accessors
    # ------------------------------------------------------------------

    def get_step(self, step_id: str) -> WorkflowStep | None:
        """Return a step by its ID, or None if not found."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_step_by_name(self, name: str) -> WorkflowStep | None:
        """Return the first step whose name matches (case-insensitive)."""
        lower = name.lower()
        for step in self.steps:
            if step.name.lower() == lower:
                return step
        return None

    def get_ready_steps(self) -> list[WorkflowStep]:
        """Get steps whose dependencies are all met and that are pending.

        A step is *ready* when:
        - its status is ``pending``
        - every step ID in its ``depends_on`` list has status
          ``completed`` or ``skipped``
        """
        completed_ids: set[str] = set()
        for s in self.steps:
            if s.status in ("completed", "skipped"):
                completed_ids.add(s.id)

        ready: list[WorkflowStep] = []
        for s in self.steps:
            if s.status != "pending":
                continue
            if all(dep in completed_ids for dep in s.depends_on):
                ready.append(s)
        return ready

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def set_variable(self, name: str, value: Any) -> None:
        """Set a workflow variable, creating it if necessary."""
        for var in self.variables:
            if var.name == name:
                var.value = value
                self.updated_at = datetime.now(timezone.utc)
                return
        self.variables.append(WorkflowVariable(name=name, value=value))
        self.updated_at = datetime.now(timezone.utc)

    def get_variable(self, name: str) -> Any:
        """Get a workflow variable's effective value (value or default)."""
        for var in self.variables:
            if var.name == name:
                return var.resolve()
        return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Validate workflow structure. Return a list of error strings.

        Checks performed:
        - No duplicate step IDs
        - All ``depends_on`` references point to existing step IDs
        - No dependency cycles (topological sort check)
        - Required variables have values or defaults
        - Condition steps have a condition expression
        - Loop steps have loop_over set
        """
        errors: list[str] = []
        step_ids = {s.id for s in self.steps}

        # Duplicate IDs
        if len(step_ids) != len(self.steps):
            seen: set[str] = set()
            for s in self.steps:
                if s.id in seen:
                    errors.append(f"Duplicate step ID: {s.id}")
                seen.add(s.id)

        # Dangling dependency references
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in step_ids:
                    errors.append(
                        f"Step '{s.name}' ({s.id}) depends on "
                        f"unknown step ID '{dep}'"
                    )

        # Cycle detection via topological sort (Kahn's algorithm)
        in_degree: dict[str, int] = {sid: 0 for sid in step_ids}
        adj: dict[str, list[str]] = {sid: [] for sid in step_ids}
        for s in self.steps:
            for dep in s.depends_on:
                if dep in step_ids:
                    adj[dep].append(s.id)
                    in_degree[s.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        if visited != len(step_ids):
            errors.append("Workflow contains a dependency cycle")

        # Required variables
        for var in self.variables:
            if var.required and var.resolve() is None:
                errors.append(f"Required variable '{var.name}' has no value")

        # Type-specific checks
        for s in self.steps:
            if s.step_type == StepType.CONDITION and not s.condition:
                errors.append(
                    f"Condition step '{s.name}' ({s.id}) has no condition"
                )
            if s.step_type == StepType.LOOP and not s.loop_over:
                errors.append(
                    f"Loop step '{s.name}' ({s.id}) has no loop_over variable"
                )
            if s.step_type == StepType.SUB_WORKFLOW and not s.sub_workflow_id:
                errors.append(
                    f"Sub-workflow step '{s.name}' ({s.id}) has no "
                    "sub_workflow_id"
                )

        return errors

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    @property
    def progress(self) -> dict[str, Any]:
        """Get workflow progress statistics.

        Returns a dict with keys: total, completed, failed, running,
        pending, skipped, percent_complete.
        """
        total = len(self.steps)
        counts: dict[str, int] = {
            "completed": 0,
            "failed": 0,
            "running": 0,
            "pending": 0,
            "skipped": 0,
        }
        for s in self.steps:
            bucket = s.status if s.status in counts else "pending"
            counts[bucket] += 1

        pct = (
            round((counts["completed"] + counts["skipped"]) / total * 100, 1)
            if total
            else 0.0
        )
        return {
            "total": total,
            **counts,
            "percent_complete": pct,
        }

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def add_step(self, step: WorkflowStep) -> None:
        """Add a step to the workflow."""
        self.steps.append(step)
        self.updated_at = datetime.now(timezone.utc)

    def remove_step(self, step_id: str) -> bool:
        """Remove a step by ID. Returns True if found and removed."""
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                self.steps.pop(i)
                # Also remove from depends_on lists
                for other in self.steps:
                    if step_id in other.depends_on:
                        other.depends_on.remove(step_id)
                self.updated_at = datetime.now(timezone.utc)
                return True
        return False

    def reset_all_steps(self) -> None:
        """Reset all steps to pending (for re-execution)."""
        for s in self.steps:
            s.reset()
        self.status = WorkflowStatus.READY
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow to a plain dict (JSON-friendly)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        """Deserialize a workflow from a plain dict."""
        return cls.model_validate(data)
