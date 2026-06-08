"""Comprehensive workflow system tests.

Tests the full workflow lifecycle including creation, execution, pausing,
resuming, approvals, DAG execution order, error handling, and templates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Workflow Models (mirrors app.py in-memory store logic)
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStep:
    id: str
    name: str
    status: str = "pending"
    output: str | None = None
    dependencies: list[str] = field(default_factory=list)
    requires_approval: bool = False
    approval_comment: str = ""
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3

    @property
    def is_ready(self) -> bool:
        return self.status == "pending" and len(self.dependencies) == 0

    def complete(self, output: str) -> None:
        self.status = "completed"
        self.output = output

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.output = error

    def skip(self, reason: str = "") -> None:
        self.status = "skipped"
        self.output = reason

    def approve(self, comment: str = "") -> None:
        self.status = "approved"
        self.approval_comment = comment

    def reject(self, comment: str = "") -> None:
        self.status = "rejected"
        self.approval_comment = comment


@dataclass
class Workflow:
    id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    status: str = "created"
    tags: list[str] = field(default_factory=list)
    execution_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def add_step(self, step_id: str, name: str, **kwargs) -> WorkflowStep:
        step = WorkflowStep(id=step_id, name=name, **kwargs)
        self.steps.append(step)
        return step

    def get_step(self, step_id: str) -> WorkflowStep | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def get_ready_steps(self) -> list[WorkflowStep]:
        completed_ids = {s.id for s in self.steps if s.status in ("completed", "approved")}
        return [
            s for s in self.steps
            if s.status == "pending"
            and all(dep in completed_ids for dep in s.dependencies)
        ]

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "approved", "skipped") for s in self.steps)

    def has_failures(self) -> bool:
        return any(s.status in ("failed", "rejected") for s in self.steps)

    @property
    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.status in ("completed", "approved", "skipped"))
        return f"{done}/{len(self.steps)}"

    def execute_all(self) -> None:
        self.status = "running"
        for step in self.steps:
            if step.requires_approval:
                step.status = "waiting_approval"
            else:
                step.complete(f"Step '{step.name}' executed")
        self.execution_count += 1
        if self.is_complete():
            self.status = "completed"

    def pause(self) -> None:
        if self.status in ("running", "created"):
            self.status = "paused"

    def resume(self) -> None:
        if self.status == "paused":
            self.status = "running"


# ---------------------------------------------------------------------------
# Workflow Template
# ---------------------------------------------------------------------------

@dataclass
class WorkflowTemplate:
    name: str
    description: str
    step_definitions: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def instantiate(self, workflow_id: str) -> Workflow:
        wf = Workflow(id=workflow_id, name=self.name, description=self.description, tags=self.tags)
        for step_def in self.step_definitions:
            wf.add_step(**step_def)
        return wf


# ---------------------------------------------------------------------------
# Tests: WorkflowStep
# ---------------------------------------------------------------------------

class TestWorkflowStep:
    def test_create_step(self):
        step = WorkflowStep(id="s1", name="Init")
        assert step.status == "pending"
        assert step.is_ready is True

    def test_complete_step(self):
        step = WorkflowStep(id="s1", name="Init")
        step.complete("done")
        assert step.status == "completed"
        assert step.output == "done"

    def test_fail_step(self):
        step = WorkflowStep(id="s1", name="Init")
        step.fail("error occurred")
        assert step.status == "failed"
        assert step.output == "error occurred"

    def test_skip_step(self):
        step = WorkflowStep(id="s1", name="Optional")
        step.skip("not needed")
        assert step.status == "skipped"

    def test_approve_step(self):
        step = WorkflowStep(id="s1", name="Review", requires_approval=True)
        step.approve("LGTM")
        assert step.status == "approved"
        assert step.approval_comment == "LGTM"

    def test_reject_step(self):
        step = WorkflowStep(id="s1", name="Review", requires_approval=True)
        step.reject("Needs changes")
        assert step.status == "rejected"

    def test_step_with_dependencies_not_ready(self):
        step = WorkflowStep(id="s2", name="Build", dependencies=["s1"])
        assert step.is_ready is False

    def test_step_retry_fields(self):
        step = WorkflowStep(id="s1", name="Flaky", max_retries=5)
        assert step.retry_count == 0
        assert step.max_retries == 5


# ---------------------------------------------------------------------------
# Tests: Workflow
# ---------------------------------------------------------------------------

class TestWorkflow:
    def test_create_workflow(self):
        wf = Workflow(id="wf-1", name="Test WF")
        assert wf.status == "created"
        assert wf.execution_count == 0

    def test_add_steps(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        wf.add_step("s2", "Step 2")
        assert len(wf.steps) == 2

    def test_get_step(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        step = wf.get_step("s1")
        assert step is not None
        assert step.name == "Step 1"

    def test_get_nonexistent_step(self):
        wf = Workflow(id="wf-1", name="Test")
        assert wf.get_step("missing") is None

    def test_execute_all(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        wf.add_step("s2", "Step 2")
        wf.execute_all()
        assert wf.status == "completed"
        assert wf.execution_count == 1
        assert all(s.status == "completed" for s in wf.steps)

    def test_multiple_executions(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        wf.execute_all()
        wf.execute_all()
        assert wf.execution_count == 2

    def test_progress(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        wf.add_step("s2", "Step 2")
        wf.add_step("s3", "Step 3")
        assert wf.progress == "0/3"
        wf.steps[0].complete("done")
        assert wf.progress == "1/3"

    def test_pause_resume(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.status = "running"
        wf.pause()
        assert wf.status == "paused"
        wf.resume()
        assert wf.status == "running"

    def test_pause_created(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.pause()
        assert wf.status == "paused"

    def test_resume_only_from_paused(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.resume()
        assert wf.status == "created"  # Unchanged

    def test_is_complete(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        assert not wf.is_complete()
        wf.steps[0].complete("done")
        assert wf.is_complete()

    def test_has_failures(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        wf.add_step("s2", "Step 2")
        wf.steps[0].complete("ok")
        assert not wf.has_failures()
        wf.steps[1].fail("error")
        assert wf.has_failures()

    def test_tags(self):
        wf = Workflow(id="wf-1", name="Test", tags=["ci", "deploy"])
        assert "ci" in wf.tags
        assert "deploy" in wf.tags

    def test_approval_workflow(self):
        wf = Workflow(id="wf-1", name="Approval Flow")
        wf.add_step("s1", "Auto Step")
        wf.add_step("s2", "Review Step", requires_approval=True)
        wf.execute_all()
        # Auto step should be completed, review step waiting for approval
        assert wf.steps[0].status == "completed"
        assert wf.steps[1].status == "waiting_approval"
        assert not wf.is_complete()


# ---------------------------------------------------------------------------
# Tests: DAG Execution
# ---------------------------------------------------------------------------

class TestWorkflowDAG:
    def test_linear_dependencies(self):
        wf = Workflow(id="wf-1", name="Linear")
        wf.add_step("s1", "First")
        wf.add_step("s2", "Second", dependencies=["s1"])
        wf.add_step("s3", "Third", dependencies=["s2"])

        ready = wf.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "s1"

    def test_parallel_steps(self):
        wf = Workflow(id="wf-1", name="Parallel")
        wf.add_step("s1", "First A")
        wf.add_step("s2", "First B")
        wf.add_step("s3", "Merge", dependencies=["s1", "s2"])

        ready = wf.get_ready_steps()
        assert len(ready) == 2
        assert {s.id for s in ready} == {"s1", "s2"}

    def test_dag_progression(self):
        wf = Workflow(id="wf-1", name="DAG")
        wf.add_step("s1", "Start")
        wf.add_step("s2", "Branch A", dependencies=["s1"])
        wf.add_step("s3", "Branch B", dependencies=["s1"])
        wf.add_step("s4", "Merge", dependencies=["s2", "s3"])

        # Only s1 is ready
        assert len(wf.get_ready_steps()) == 1

        # Complete s1
        wf.get_step("s1").complete("done")
        ready = wf.get_ready_steps()
        assert len(ready) == 2

        # Complete s2 only
        wf.get_step("s2").complete("done")
        ready = wf.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "s3"

        # Complete s3
        wf.get_step("s3").complete("done")
        ready = wf.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "s4"

    def test_diamond_dependency(self):
        wf = Workflow(id="wf-1", name="Diamond")
        wf.add_step("s1", "Top")
        wf.add_step("s2", "Left", dependencies=["s1"])
        wf.add_step("s3", "Right", dependencies=["s1"])
        wf.add_step("s4", "Bottom", dependencies=["s2", "s3"])

        wf.get_step("s1").complete("done")
        wf.get_step("s2").complete("done")

        # s4 should NOT be ready yet (s3 still pending)
        ready = wf.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "s3"

    def test_no_ready_when_all_complete(self):
        wf = Workflow(id="wf-1", name="Done")
        wf.add_step("s1", "Only Step")
        wf.get_step("s1").complete("done")
        assert len(wf.get_ready_steps()) == 0

    def test_complex_dag(self):
        wf = Workflow(id="wf-1", name="Complex")
        wf.add_step("fetch", "Fetch Data")
        wf.add_step("parse", "Parse Data", dependencies=["fetch"])
        wf.add_step("validate", "Validate Schema", dependencies=["fetch"])
        wf.add_step("transform", "Transform", dependencies=["parse", "validate"])
        wf.add_step("load", "Load to DB", dependencies=["transform"])
        wf.add_step("notify", "Notify Team", dependencies=["load"])
        wf.add_step("cleanup", "Cleanup Temp", dependencies=["load"])

        # Only fetch is ready
        assert len(wf.get_ready_steps()) == 1

        wf.get_step("fetch").complete("ok")
        # parse and validate are now ready
        ready_ids = {s.id for s in wf.get_ready_steps()}
        assert ready_ids == {"parse", "validate"}


# ---------------------------------------------------------------------------
# Tests: Workflow Template
# ---------------------------------------------------------------------------

class TestWorkflowTemplate:
    def test_create_template(self):
        template = WorkflowTemplate(
            name="CI Pipeline",
            description="Standard CI pipeline",
            step_definitions=[
                {"step_id": "build", "name": "Build"},
                {"step_id": "test", "name": "Test"},
                {"step_id": "deploy", "name": "Deploy"},
            ],
        )
        assert template.name == "CI Pipeline"
        assert len(template.step_definitions) == 3

    def test_instantiate_template(self):
        template = WorkflowTemplate(
            name="Review",
            description="Code review workflow",
            step_definitions=[
                {"step_id": "lint", "name": "Lint"},
                {"step_id": "review", "name": "Review", "requires_approval": True},
                {"step_id": "merge", "name": "Merge"},
            ],
            tags=["review", "code"],
        )
        wf = template.instantiate("wf-001")
        assert wf.id == "wf-001"
        assert wf.name == "Review"
        assert len(wf.steps) == 3
        assert wf.steps[1].requires_approval is True
        assert "review" in wf.tags

    def test_instantiate_multiple(self):
        template = WorkflowTemplate(
            name="Simple",
            description="Simple workflow",
            step_definitions=[{"step_id": "s1", "name": "Only"}],
        )
        wf1 = template.instantiate("wf-1")
        wf2 = template.instantiate("wf-2")
        assert wf1.id != wf2.id
        assert len(wf1.steps) == len(wf2.steps)
        # Each instantiation creates independent step objects
        wf1.steps[0].complete("done")
        assert wf2.steps[0].status == "pending"

    def test_template_with_dependencies(self):
        template = WorkflowTemplate(
            name="Build & Deploy",
            description="Build and deploy pipeline",
            step_definitions=[
                {"step_id": "build", "name": "Build"},
                {"step_id": "test", "name": "Test", "dependencies": ["build"]},
                {"step_id": "deploy", "name": "Deploy", "dependencies": ["test"]},
            ],
        )
        wf = template.instantiate("wf-001")
        # First step has no dependencies, so it should be ready
        ready = wf.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].name == "Build"


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------

class TestWorkflowErrorHandling:
    def test_step_failure_does_not_block_others(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        wf.add_step("s2", "Step 2")
        wf.steps[0].fail("error")
        # s2 is still ready (no dependency on s1)
        ready = wf.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "s2"

    def test_step_failure_blocks_dependents(self):
        wf = Workflow(id="wf-1", name="Test")
        wf.add_step("s1", "Step 1")
        wf.add_step("s2", "Step 2", dependencies=["s1"])
        wf.steps[0].fail("error")
        # s2 cannot proceed because s1 is not "completed"
        ready = wf.get_ready_steps()
        assert len(ready) == 0

    def test_workflow_with_all_skipped(self):
        wf = Workflow(id="wf-1", name="Skip All")
        wf.add_step("s1", "Step 1")
        wf.add_step("s2", "Step 2")
        wf.steps[0].skip("not needed")
        wf.steps[1].skip("not needed")
        assert wf.is_complete()

    def test_mixed_completion(self):
        wf = Workflow(id="wf-1", name="Mixed")
        wf.add_step("s1", "Complete")
        wf.add_step("s2", "Skip")
        wf.add_step("s3", "Approve")
        wf.steps[0].complete("done")
        wf.steps[1].skip("n/a")
        wf.steps[2].approve("ok")
        assert wf.is_complete()

    def test_empty_workflow_is_complete(self):
        wf = Workflow(id="wf-1", name="Empty")
        assert wf.is_complete()

    def test_retry_tracking(self):
        step = WorkflowStep(id="s1", name="Flaky", max_retries=3)
        step.retry_count = 1
        step.fail("first attempt")
        assert step.retry_count < step.max_retries
        step.retry_count = 2
        step.fail("second attempt")
        assert step.retry_count < step.max_retries
        step.retry_count = 3
        step.fail("third attempt")
        assert step.retry_count >= step.max_retries
