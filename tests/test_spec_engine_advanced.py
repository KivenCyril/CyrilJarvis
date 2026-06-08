"""Advanced Streaming Spec engine tests.

Tests spec lifecycle, step management, constraint handling,
progress tracking, changelog generation, and spec serialization.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Spec Models (simplified)
# ---------------------------------------------------------------------------

@dataclass
class SpecConstraint:
    id: str
    content: str
    active: bool = True
    added_by: str = "human"  # human, agent, system
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "active": self.active,
            "added_by": self.added_by,
        }


@dataclass
class SpecStep:
    id: str
    name: str
    description: str = ""
    status: str = "pending"  # pending, planning, executing, completed, skipped, failed
    output: str | None = None
    agent: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float = 0

    def start(self) -> None:
        self.status = "executing"
        self.started_at = datetime.datetime.utcnow().isoformat()

    def complete(self, output: str = "") -> None:
        self.status = "completed"
        self.output = output
        self.completed_at = datetime.datetime.utcnow().isoformat()

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.output = error
        self.completed_at = datetime.datetime.utcnow().isoformat()

    def skip(self, reason: str = "") -> None:
        self.status = "skipped"
        self.output = reason

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "output": self.output,
            "agent": self.agent,
        }


@dataclass
class ChangelogEntry:
    action: str
    details: str
    source: str = "human"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.utcnow().isoformat()


@dataclass
class StreamingSpec:
    id: str
    name: str
    intent: str
    status: str = "planning"  # planning, executing, paused, completed, redirected, failed
    steps: list[SpecStep] = field(default_factory=list)
    constraints: list[SpecConstraint] = field(default_factory=list)
    changelog: list[ChangelogEntry] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    @property
    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.status in ("completed", "skipped"))
        return f"{done}/{len(self.steps)}"

    @property
    def completion_percentage(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status in ("completed", "skipped"))
        return round(done / len(self.steps) * 100, 1)

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps) and len(self.steps) > 0

    @property
    def has_failures(self) -> bool:
        return any(s.status == "failed" for s in self.steps)

    @property
    def active_constraints(self) -> list[SpecConstraint]:
        return [c for c in self.constraints if c.active]

    def add_step(self, step_id: str, name: str, **kwargs) -> SpecStep:
        step = SpecStep(id=step_id, name=name, **kwargs)
        self.steps.append(step)
        self._log("step_added", f"Added step: {name}")
        return step

    def get_step(self, step_id: str) -> SpecStep | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def add_constraint(self, constraint_id: str, content: str,
                       source: str = "human") -> SpecConstraint:
        constraint = SpecConstraint(id=constraint_id, content=content, added_by=source)
        self.constraints.append(constraint)
        self._log("constraint_added", f"Added constraint: {content}", source)
        return constraint

    def remove_constraint(self, constraint_id: str) -> bool:
        constraint = next((c for c in self.constraints if c.id == constraint_id), None)
        if constraint:
            constraint.active = False
            self._log("constraint_removed", f"Removed constraint: {constraint.content}")
            return True
        return False

    def redirect(self, new_intent: str) -> None:
        old_intent = self.intent
        self.intent = new_intent
        self.status = "redirected"
        self._log("redirected", f"Redirected from '{old_intent}' to '{new_intent}'")

    def pause(self) -> None:
        self.status = "paused"
        self._log("paused", "Spec paused")

    def resume(self) -> None:
        self.status = "executing"
        self._log("resumed", "Spec resumed")

    def execute(self) -> None:
        self.status = "executing"
        for step in self.steps:
            if step.status == "pending":
                step.start()
                step.complete(f"Step '{step.name}' completed")
        if self.is_complete:
            self.status = "completed"
        self._log("executed", "Spec executed")

    def _log(self, action: str, details: str, source: str = "system") -> None:
        self.changelog.append(ChangelogEntry(action=action, details=details, source=source))
        self.updated_at = datetime.datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "intent": self.intent,
            "status": self.status,
            "progress": self.progress,
            "steps": [s.to_dict() for s in self.steps],
            "constraints": [c.to_dict() for c in self.constraints],
            "changelog_count": len(self.changelog),
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Tests: SpecStep
# ---------------------------------------------------------------------------

class TestSpecStep:
    def test_create_step(self):
        step = SpecStep(id="s1", name="Init")
        assert step.status == "pending"
        assert step.output is None

    def test_start_step(self):
        step = SpecStep(id="s1", name="Init")
        step.start()
        assert step.status == "executing"
        assert step.started_at is not None

    def test_complete_step(self):
        step = SpecStep(id="s1", name="Init")
        step.start()
        step.complete("done")
        assert step.status == "completed"
        assert step.output == "done"
        assert step.completed_at is not None

    def test_fail_step(self):
        step = SpecStep(id="s1", name="Init")
        step.fail("error")
        assert step.status == "failed"
        assert step.output == "error"

    def test_skip_step(self):
        step = SpecStep(id="s1", name="Optional")
        step.skip("not needed")
        assert step.status == "skipped"

    def test_step_with_agent(self):
        step = SpecStep(id="s1", name="Review", agent="code-agent")
        assert step.agent == "code-agent"

    def test_step_to_dict(self):
        step = SpecStep(id="s1", name="Test", description="A test step")
        d = step.to_dict()
        assert d["id"] == "s1"
        assert d["name"] == "Test"
        assert d["description"] == "A test step"


# ---------------------------------------------------------------------------
# Tests: SpecConstraint
# ---------------------------------------------------------------------------

class TestSpecConstraint:
    def test_create_constraint(self):
        c = SpecConstraint(id="c1", content="Be fast")
        assert c.active is True
        assert c.added_by == "human"

    def test_deactivate_constraint(self):
        c = SpecConstraint(id="c1", content="Be fast")
        c.active = False
        assert c.active is False

    def test_constraint_to_dict(self):
        c = SpecConstraint(id="c1", content="Be safe", added_by="agent")
        d = c.to_dict()
        assert d["content"] == "Be safe"
        assert d["added_by"] == "agent"


# ---------------------------------------------------------------------------
# Tests: StreamingSpec - Basic
# ---------------------------------------------------------------------------

class TestStreamingSpecBasic:
    def test_create_spec(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do something")
        assert spec.status == "planning"
        assert spec.progress == "0/0"

    def test_add_steps(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do something")
        spec.add_step("s1", "First step")
        spec.add_step("s2", "Second step")
        assert len(spec.steps) == 2
        assert spec.progress == "0/2"

    def test_get_step(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        step = spec.get_step("s1")
        assert step is not None
        assert step.name == "Step 1"

    def test_get_nonexistent_step(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        assert spec.get_step("missing") is None


# ---------------------------------------------------------------------------
# Tests: StreamingSpec - Constraints
# ---------------------------------------------------------------------------

class TestStreamingSpecConstraints:
    def test_add_constraint(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        c = spec.add_constraint("c1", "Be thorough")
        assert len(spec.constraints) == 1
        assert c.content == "Be thorough"

    def test_add_multiple_constraints(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_constraint("c1", "Be fast")
        spec.add_constraint("c2", "Be accurate")
        spec.add_constraint("c3", "Be safe")
        assert len(spec.constraints) == 3

    def test_remove_constraint(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_constraint("c1", "Remove me")
        assert spec.remove_constraint("c1") is True
        assert spec.constraints[0].active is False

    def test_remove_nonexistent_constraint(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        assert spec.remove_constraint("missing") is False

    def test_active_constraints(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_constraint("c1", "Active")
        spec.add_constraint("c2", "Inactive")
        spec.remove_constraint("c2")
        assert len(spec.active_constraints) == 1

    def test_constraint_sources(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_constraint("c1", "Human constraint", source="human")
        spec.add_constraint("c2", "Agent constraint", source="agent")
        assert spec.constraints[0].added_by == "human"
        assert spec.constraints[1].added_by == "agent"


# ---------------------------------------------------------------------------
# Tests: StreamingSpec - Execution
# ---------------------------------------------------------------------------

class TestStreamingSpecExecution:
    def test_execute_spec(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        spec.add_step("s2", "Step 2")
        spec.execute()
        assert spec.status == "completed"
        assert spec.is_complete is True

    def test_progress_tracking(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        spec.add_step("s2", "Step 2")
        spec.add_step("s3", "Step 3")
        assert spec.completion_percentage == 0.0

        spec.steps[0].complete("done")
        assert spec.completion_percentage == pytest.approx(33.3, abs=0.1)

        spec.steps[1].complete("done")
        assert spec.completion_percentage == pytest.approx(66.7, abs=0.1)

        spec.steps[2].complete("done")
        assert spec.completion_percentage == 100.0

    def test_pause_resume(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.pause()
        assert spec.status == "paused"
        spec.resume()
        assert spec.status == "executing"

    def test_redirect(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Original")
        spec.redirect("New direction")
        assert spec.intent == "New direction"
        assert spec.status == "redirected"

    def test_has_failures(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        spec.add_step("s2", "Step 2")
        spec.steps[0].complete("ok")
        assert spec.has_failures is False
        spec.steps[1].fail("error")
        assert spec.has_failures is True

    def test_empty_spec_not_complete(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        assert spec.is_complete is False


# ---------------------------------------------------------------------------
# Tests: StreamingSpec - Changelog
# ---------------------------------------------------------------------------

class TestStreamingSpecChangelog:
    def test_changelog_on_add_step(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        assert len(spec.changelog) == 1
        assert "step_added" in spec.changelog[0].action

    def test_changelog_on_add_constraint(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_constraint("c1", "Be fast")
        assert any("constraint_added" in c.action for c in spec.changelog)

    def test_changelog_on_remove_constraint(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_constraint("c1", "Remove")
        spec.remove_constraint("c1")
        assert any("constraint_removed" in c.action for c in spec.changelog)

    def test_changelog_on_redirect(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Original")
        spec.redirect("New")
        assert any("redirected" in c.action for c in spec.changelog)

    def test_changelog_on_pause_resume(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.pause()
        spec.resume()
        assert any("paused" in c.action for c in spec.changelog)
        assert any("resumed" in c.action for c in spec.changelog)

    def test_changelog_accumulates(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        spec.add_constraint("c1", "Fast")
        spec.redirect("New")
        assert len(spec.changelog) >= 3


# ---------------------------------------------------------------------------
# Tests: StreamingSpec - Serialization
# ---------------------------------------------------------------------------

class TestStreamingSpecSerialization:
    def test_to_dict(self):
        spec = StreamingSpec(id="spec-1", name="Test Spec", intent="Do task")
        spec.add_step("s1", "Step 1")
        spec.add_constraint("c1", "Be fast")
        d = spec.to_dict()
        assert d["id"] == "spec-1"
        assert d["name"] == "Test Spec"
        assert len(d["steps"]) == 1
        assert len(d["constraints"]) == 1
        assert d["changelog_count"] >= 2

    def test_json_serializable(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        d = spec.to_dict()
        j = json.dumps(d)
        restored = json.loads(j)
        assert restored["id"] == "spec-1"

    def test_progress_in_dict(self):
        spec = StreamingSpec(id="spec-1", name="Test", intent="Do")
        spec.add_step("s1", "Step 1")
        spec.steps[0].complete("done")
        d = spec.to_dict()
        assert d["progress"] == "1/1"
