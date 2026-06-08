from __future__ import annotations

import asyncio

import pytest

from jarvis.models.streaming_spec import (
    ChangeSource,
    ChangeType,
    SpecStatus,
    StepStatus,
    Step,
    StreamingSpec,
)
from jarvis.engine.spec_engine import SpecEngine
from jarvis.models.agent_spec import AgentSpec
from jarvis.engine.spec_registry import SpecRegistry


class TestStreamingSpecModel:
    def test_create_spec(self):
        spec = StreamingSpec(name="test", intent="do something")
        assert spec.status == SpecStatus.PLANNING
        assert spec.progress == "0/0"
        assert spec.id
        assert spec.changelog == []
        assert spec.version == 1

    def test_add_step(self):
        spec = StreamingSpec(name="test", intent="do something")
        step = spec.add_step("step 1", "first step")
        assert len(spec.steps) == 1
        assert step.status == StepStatus.PENDING
        assert "0/1" in spec.progress
        assert len(spec.changelog) == 1
        assert spec.changelog[0].change_type == ChangeType.STEP_ADDED

    def test_update_step_status(self):
        spec = StreamingSpec(name="test", intent="do something")
        step = spec.add_step("step 1")
        spec.update_step_status(step.id, StepStatus.COMPLETED)
        assert spec.steps[0].status == StepStatus.COMPLETED
        assert "1/1" in spec.progress

    def test_add_constraint(self):
        spec = StreamingSpec(name="test", intent="do something")
        c = spec.add_constraint("no database changes")
        assert len(spec.constraints) == 1
        assert c.added_by == ChangeSource.HUMAN
        assert c.active is True
        assert spec.changelog[-1].change_type == ChangeType.CONSTRAINT_ADDED

    def test_remove_constraint(self):
        spec = StreamingSpec(name="test", intent="do something")
        c = spec.add_constraint("temp constraint")
        removed = spec.remove_constraint(c.id)
        assert removed is not None
        assert len(spec.constraints) == 0
        assert spec.changelog[-1].change_type == ChangeType.CONSTRAINT_REMOVED

    def test_remove_nonexistent_constraint(self):
        spec = StreamingSpec(name="test", intent="do something")
        removed = spec.remove_constraint("nonexistent")
        assert removed is None

    def test_change_intent(self):
        spec = StreamingSpec(name="test", intent="original intent")
        spec.change_intent("new intent")
        assert spec.intent == "new intent"
        assert spec.status == SpecStatus.REDIRECTED
        assert spec.changelog[-1].change_type == ChangeType.INTENT_CHANGED
        assert spec.changelog[-1].old_value == "original intent"

    def test_pending_steps(self):
        spec = StreamingSpec(name="test", intent="do something")
        s1 = spec.add_step("step 1")
        s2 = spec.add_step("step 2")
        spec.update_step_status(s1.id, StepStatus.COMPLETED)
        pending = spec.pending_steps()
        assert len(pending) == 1
        assert pending[0].id == s2.id

    def test_set_step_output(self):
        spec = StreamingSpec(name="test", intent="do something")
        step = spec.add_step("step 1")
        result = spec.set_step_output(step.id, "done!")
        assert result is not None
        assert spec.steps[0].output == "done!"

    def test_changelog_tracks_source(self):
        spec = StreamingSpec(name="test", intent="do something")
        spec.add_constraint("human constraint", source=ChangeSource.HUMAN)
        spec.add_step("agent step", source=ChangeSource.AGENT)
        assert spec.changelog[0].source == ChangeSource.HUMAN
        assert spec.changelog[1].source == ChangeSource.AGENT


class TestDAG:
    """Tests for DAG validation, topological sort, dependency management,
    readiness computation, and critical path."""

    def _make_spec_with_steps(self, names: list[str]) -> StreamingSpec:
        """Helper: create a spec with named steps (no dependencies)."""
        spec = StreamingSpec(name="dag-test", intent="test DAG")
        for n in names:
            spec.add_step(n)
        return spec

    # ── validate_dag ────────────────────────────────────────────────────

    def test_dag_validation_valid(self):
        """A linear chain A -> B -> C has no cycles."""
        spec = self._make_spec_with_steps(["A", "B", "C"])
        a, b, c = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [b.id]
        assert spec.validate_dag() is True

    def test_dag_validation_no_edges(self):
        """An empty graph (no dependencies) is trivially valid."""
        spec = self._make_spec_with_steps(["X", "Y"])
        assert spec.validate_dag() is True

    def test_dag_validation_cycle_detected(self):
        """A -> B -> C -> A is a cycle."""
        spec = self._make_spec_with_steps(["A", "B", "C"])
        a, b, c = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [b.id]
        a.depends_on = [c.id]
        assert spec.validate_dag() is False

    def test_dag_validation_self_loop(self):
        """A step depending on itself is a cycle."""
        spec = self._make_spec_with_steps(["A"])
        spec.steps[0].depends_on = [spec.steps[0].id]
        assert spec.validate_dag() is False

    # ── topological_sort ────────────────────────────────────────────────

    def test_topological_sort(self):
        """A -> B -> C must be sorted so that A comes before B before C."""
        spec = self._make_spec_with_steps(["A", "B", "C"])
        a, b, c = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [b.id]
        order = spec.topological_sort()
        names = [s.name for s in order]
        assert names.index("A") < names.index("B") < names.index("C")

    def test_topological_sort_diamond(self):
        """Diamond: A -> B, A -> C, B -> D, C -> D.
        Valid orderings: A before {B,C} before D."""
        spec = self._make_spec_with_steps(["A", "B", "C", "D"])
        a, b, c, d = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [a.id]
        d.depends_on = [b.id, c.id]
        order = spec.topological_sort()
        names = [s.name for s in order]
        assert len(order) == 4
        assert names.index("A") < names.index("B")
        assert names.index("A") < names.index("C")
        assert names.index("B") < names.index("D")
        assert names.index("C") < names.index("D")

    def test_topological_sort_independent(self):
        """Fully independent steps should all appear in the result."""
        spec = self._make_spec_with_steps(["X", "Y", "Z"])
        order = spec.topological_sort()
        assert len(order) == 3

    # ── get_ready_steps / get_blocked_steps ─────────────────────────────

    def test_get_ready_steps(self):
        """Steps with no dependencies should become READY after update."""
        spec = self._make_spec_with_steps(["A", "B", "C"])
        a, b, c = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [b.id]
        spec.update_step_readiness()

        ready = spec.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].name == "A"

    def test_get_blocked_steps(self):
        """Steps waiting for incomplete dependencies should be BLOCKED."""
        spec = self._make_spec_with_steps(["A", "B", "C"])
        a, b, c = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [b.id]
        spec.update_step_readiness()

        blocked = spec.get_blocked_steps()
        assert len(blocked) == 2
        blocked_names = {s.name for s in blocked}
        assert blocked_names == {"B", "C"}

    def test_ready_after_dependency_completed(self):
        """Completing A should make B ready (B depends on A)."""
        spec = self._make_spec_with_steps(["A", "B"])
        a, b = spec.steps
        b.depends_on = [a.id]
        spec.update_step_readiness()
        assert spec.get_ready_steps()[0].name == "A"

        # Complete A
        spec.update_step_status(a.id, StepStatus.COMPLETED)
        spec.update_step_readiness()

        ready = spec.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].name == "B"

    # ── add_dependency / remove_dependency ──────────────────────────────

    def test_add_dependency(self):
        spec = self._make_spec_with_steps(["A", "B"])
        a, b = spec.steps
        assert spec.add_dependency(b.id, a.id) is True
        assert a.id in b.depends_on
        # Changelog should contain the dependency addition
        dep_changes = [
            c for c in spec.changelog if c.change_type == ChangeType.DEPENDENCY_ADDED
        ]
        assert len(dep_changes) == 1

    def test_add_dependency_rejects_cycle(self):
        """Adding a dependency that creates a cycle should fail."""
        spec = self._make_spec_with_steps(["A", "B"])
        a, b = spec.steps
        b.depends_on = [a.id]
        # A depending on B would create a cycle
        assert spec.add_dependency(a.id, b.id) is False
        assert b.id not in a.depends_on

    def test_add_dependency_idempotent(self):
        spec = self._make_spec_with_steps(["A", "B"])
        a, b = spec.steps
        assert spec.add_dependency(b.id, a.id) is True
        assert spec.add_dependency(b.id, a.id) is True
        assert b.depends_on.count(a.id) == 1

    def test_add_dependency_nonexistent_step(self):
        spec = self._make_spec_with_steps(["A"])
        a = spec.steps[0]
        assert spec.add_dependency(a.id, "nonexistent") is False

    def test_remove_dependency(self):
        spec = self._make_spec_with_steps(["A", "B"])
        a, b = spec.steps
        spec.add_dependency(b.id, a.id)
        assert spec.remove_dependency(b.id, a.id) is True
        assert a.id not in b.depends_on

    def test_remove_dependency_nonexistent(self):
        spec = self._make_spec_with_steps(["A", "B"])
        a, b = spec.steps
        assert spec.remove_dependency(b.id, a.id) is False

    # ── critical_path ───────────────────────────────────────────────────

    def test_critical_path(self):
        """Diamond graph: critical path should be length 3 (A -> B or C -> D)."""
        spec = self._make_spec_with_steps(["A", "B", "C", "D"])
        a, b, c, d = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [a.id]
        d.depends_on = [b.id, c.id]
        cp = spec.critical_path()
        assert len(cp) == 3
        assert cp[0].name == "A"
        assert cp[-1].name == "D"

    def test_critical_path_linear(self):
        """Linear chain: critical path is the entire chain."""
        spec = self._make_spec_with_steps(["A", "B", "C"])
        a, b, c = spec.steps
        b.depends_on = [a.id]
        c.depends_on = [b.id]
        cp = spec.critical_path()
        assert [s.name for s in cp] == ["A", "B", "C"]

    def test_critical_path_single_step(self):
        spec = self._make_spec_with_steps(["A"])
        cp = spec.critical_path()
        assert len(cp) == 1
        assert cp[0].name == "A"

    def test_critical_path_empty(self):
        spec = StreamingSpec(name="empty", intent="nothing")
        assert spec.critical_path() == []

    # ── version tracking ────────────────────────────────────────────────

    def test_version_increments(self):
        spec = StreamingSpec(name="v", intent="versioning")
        assert spec.version == 1
        spec.add_step("s1")
        assert spec.version == 2
        spec.add_constraint("c1")
        assert spec.version == 3

    # ── elapsed_time ────────────────────────────────────────────────────

    def test_elapsed_time(self):
        spec = StreamingSpec(name="t", intent="timing")
        assert spec.elapsed_time >= 0

    # ── get_step ────────────────────────────────────────────────────────

    def test_get_step_found(self):
        spec = self._make_spec_with_steps(["A"])
        assert spec.get_step(spec.steps[0].id) is not None

    def test_get_step_not_found(self):
        spec = self._make_spec_with_steps(["A"])
        assert spec.get_step("nonexistent") is None

    # ── Step timing fields ──────────────────────────────────────────────

    def test_step_timing(self):
        spec = self._make_spec_with_steps(["A"])
        a = spec.steps[0]
        assert a.started_at is None
        assert a.completed_at is None

        spec.update_step_status(a.id, StepStatus.EXECUTING)
        assert a.started_at is not None

        spec.update_step_status(a.id, StepStatus.COMPLETED)
        assert a.completed_at is not None


class TestSpecEngine:
    @pytest.fixture
    def engine(self):
        return SpecEngine()

    @pytest.mark.asyncio
    async def test_create_fallback(self, engine: SpecEngine):
        spec = await engine.create("migrate CI to GitHub Actions")
        assert spec.status == SpecStatus.EXECUTING
        assert len(spec.steps) == 4
        assert engine.get(spec.id) is spec

    @pytest.mark.asyncio
    async def test_list_specs(self, engine: SpecEngine):
        await engine.create("task 1")
        await engine.create("task 2")
        assert len(engine.list_specs()) == 2

    @pytest.mark.asyncio
    async def test_update_step(self, engine: SpecEngine):
        spec = await engine.create("test task")
        step_id = spec.steps[0].id
        result = await engine.update_step(spec.id, step_id, status=StepStatus.COMPLETED, output="analyzed")
        assert result is not None
        assert result.steps[0].status == StepStatus.COMPLETED
        assert result.steps[0].output == "analyzed"

    @pytest.mark.asyncio
    async def test_add_constraint(self, engine: SpecEngine):
        spec = await engine.create("test task")
        result = await engine.add_constraint(spec.id, "no breaking changes")
        assert result is not None
        assert len(result.constraints) == 1

    @pytest.mark.asyncio
    async def test_redirect(self, engine: SpecEngine):
        spec = await engine.create("original task")
        result = await engine.redirect(spec.id, "completely different task")
        assert result is not None
        assert result.intent == "completely different task"
        assert result.id == spec.id

    @pytest.mark.asyncio
    async def test_auto_complete(self, engine: SpecEngine):
        spec = await engine.create("test task")
        for step in spec.steps:
            await engine.update_step(spec.id, step.id, status=StepStatus.COMPLETED)
        updated = engine.get(spec.id)
        assert updated is not None
        assert updated.status == SpecStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_nonexistent_spec(self, engine: SpecEngine):
        result = await engine.update_step("nonexistent", "step", status=StepStatus.COMPLETED)
        assert result is None

    @pytest.mark.asyncio
    async def test_event_callback(self, engine: SpecEngine):
        events = []

        async def on_event(spec_id, event_type, data):
            events.append((spec_id, event_type))

        engine.on_event(on_event)
        spec = await engine.create("test")
        import asyncio
        await asyncio.sleep(0.05)
        assert any(e[1] == "spec_created" for e in events)

    @pytest.mark.asyncio
    async def test_add_dependency_via_engine(self, engine: SpecEngine):
        spec = await engine.create("dep task")
        a_id = spec.steps[0].id
        b_id = spec.steps[1].id
        result = await engine.add_dependency(spec.id, b_id, a_id)
        assert result is not None
        updated = engine.get(spec.id)
        assert a_id in updated.steps[1].depends_on

    @pytest.mark.asyncio
    async def test_add_dependency_cycle_rejected_via_engine(self, engine: SpecEngine):
        spec = await engine.create("cycle task")
        a_id = spec.steps[0].id
        b_id = spec.steps[1].id
        # A -> B
        await engine.add_dependency(spec.id, b_id, a_id)
        # B -> A should fail (cycle)
        result = await engine.add_dependency(spec.id, a_id, b_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_dependency_via_engine(self, engine: SpecEngine):
        spec = await engine.create("rem-dep task")
        a_id = spec.steps[0].id
        b_id = spec.steps[1].id
        await engine.add_dependency(spec.id, b_id, a_id)
        result = await engine.remove_dependency(spec.id, b_id, a_id)
        assert result is not None
        updated = engine.get(spec.id)
        assert a_id not in updated.steps[1].depends_on

    @pytest.mark.asyncio
    async def test_remove_dependency_nonexistent_via_engine(self, engine: SpecEngine):
        spec = await engine.create("no-dep task")
        a_id = spec.steps[0].id
        b_id = spec.steps[1].id
        result = await engine.remove_dependency(spec.id, b_id, a_id)
        assert result is None


class TestAgentSpec:
    def test_load_from_yaml(self, tmp_path):
        yaml_content = """
kind: AgentSpec
metadata:
  name: test-agent
  version: v1.0
  domain: test

triggers:
  - event: manual.command
    filter: "intent == 'test'"

capabilities:
  skills:
    - testing
  input_modes: [text]
  output_modes: [text]

rules:
  - name: basic-rule
    severity: P1
    description: "A test rule"

context:
  knowledge_base: test-kb
  memory_scope: per-user

collaboration:
  can_delegate_to:
    - helper-agent
"""
        yaml_file = tmp_path / "test-agent.yaml"
        yaml_file.write_text(yaml_content)

        spec = AgentSpec.from_yaml(yaml_file)
        assert spec.metadata.name == "test-agent"
        assert len(spec.triggers) == 1
        assert len(spec.rules) == 1
        assert spec.capabilities.skills == ["testing"]

    def test_registry_load_dir(self, tmp_path):
        yaml_content = """
kind: AgentSpec
metadata:
  name: my-agent
  version: v1.0

rules:
  - name: rule-1
    description: "test"
"""
        (tmp_path / "agent.yaml").write_text(yaml_content)
        registry = SpecRegistry(tmp_path)
        assert len(registry.list_specs()) == 1
        assert registry.get("my-agent") is not None
