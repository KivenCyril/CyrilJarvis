"""Tests for the JARVIS workflow engine.

Covers models, engine execution, templates, persistence, and error handling.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from jarvis.workflow import (
    ConditionalBranch,
    LoopStep,
    StepType,
    SubWorkflow,
    TemplateRegistry,
    Workflow,
    WorkflowEngine,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStore,
    WorkflowTemplate,
    WorkflowTrigger,
    WorkflowVariable,
)

pytestmark = pytest.mark.asyncio(loop_scope="function")


# ======================================================================
# Helpers
# ======================================================================

def _make_linear_workflow(n: int = 3) -> Workflow:
    """Create a simple linear workflow with *n* action steps."""
    steps = [
        WorkflowStep(id=f"s{i}", name=f"Step {i}", step_type=StepType.ACTION)
        for i in range(n)
    ]
    for i in range(1, n):
        steps[i].depends_on = [steps[i - 1].id]
    return Workflow(name="linear", steps=steps)


# ======================================================================
# 1. WorkflowStep creation and types
# ======================================================================

class TestWorkflowStep:
    def test_default_step(self):
        step = WorkflowStep(name="test")
        assert step.step_type == StepType.ACTION
        assert step.status == "pending"
        assert step.is_pending

    def test_step_types(self):
        for st in StepType:
            step = WorkflowStep(name=st.value, step_type=st)
            assert step.step_type == st

    def test_mark_running(self):
        step = WorkflowStep(name="x")
        step.mark_running()
        assert step.is_running
        assert step.started_at is not None

    def test_mark_completed(self):
        step = WorkflowStep(name="x")
        step.mark_running()
        step.mark_completed(output={"ok": True})
        assert step.is_complete
        assert step.output == {"ok": True}
        assert step.completed_at is not None

    def test_mark_failed(self):
        step = WorkflowStep(name="x")
        step.mark_running()
        step.mark_failed("boom")
        assert step.is_failed
        assert step.error == "boom"

    def test_mark_skipped(self):
        step = WorkflowStep(name="x")
        step.mark_skipped()
        assert step.is_complete  # skipped counts as complete
        assert step.status == "skipped"

    def test_reset(self):
        step = WorkflowStep(name="x")
        step.mark_running()
        step.mark_completed("done")
        step.reset()
        assert step.is_pending
        assert step.output is None
        assert step.started_at is None

    def test_duration(self):
        step = WorkflowStep(name="x")
        step.mark_running()
        step.mark_completed()
        assert step.duration_seconds is not None
        assert step.duration_seconds >= 0

    def test_duration_none_when_pending(self):
        step = WorkflowStep(name="x")
        assert step.duration_seconds is None


# ======================================================================
# 2. Workflow validation
# ======================================================================

class TestWorkflowValidation:
    def test_valid_workflow(self):
        wf = _make_linear_workflow()
        errors = wf.validate()
        assert errors == []

    def test_duplicate_step_ids(self):
        steps = [
            WorkflowStep(id="dup", name="A"),
            WorkflowStep(id="dup", name="B"),
        ]
        wf = Workflow(name="bad", steps=steps)
        errors = wf.validate()
        assert any("Duplicate" in e for e in errors)

    def test_missing_dependency(self):
        steps = [WorkflowStep(id="s1", name="A", depends_on=["missing"])]
        wf = Workflow(name="bad", steps=steps)
        errors = wf.validate()
        assert any("unknown" in e.lower() for e in errors)

    def test_cycle_detection(self):
        steps = [
            WorkflowStep(id="a", name="A", depends_on=["b"]),
            WorkflowStep(id="b", name="B", depends_on=["a"]),
        ]
        wf = Workflow(name="cycle", steps=steps)
        errors = wf.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_condition_without_expression(self):
        steps = [WorkflowStep(id="c", name="C", step_type=StepType.CONDITION)]
        wf = Workflow(name="bad", steps=steps)
        errors = wf.validate()
        assert any("condition" in e.lower() for e in errors)

    def test_loop_without_loop_over(self):
        steps = [WorkflowStep(id="l", name="L", step_type=StepType.LOOP)]
        wf = Workflow(name="bad", steps=steps)
        errors = wf.validate()
        assert any("loop_over" in e.lower() for e in errors)

    def test_sub_workflow_without_id(self):
        steps = [
            WorkflowStep(id="sw", name="SW", step_type=StepType.SUB_WORKFLOW)
        ]
        wf = Workflow(name="bad", steps=steps)
        errors = wf.validate()
        assert any("sub_workflow_id" in e.lower() for e in errors)

    def test_required_variable_missing(self):
        wf = Workflow(
            name="bad",
            variables=[
                WorkflowVariable(name="x", required=True),
            ],
        )
        errors = wf.validate()
        assert any("Required" in e for e in errors)

    def test_required_variable_with_default_ok(self):
        wf = Workflow(
            name="ok",
            variables=[
                WorkflowVariable(name="x", required=True, default="hello"),
            ],
        )
        errors = wf.validate()
        assert errors == []


# ======================================================================
# 3. Workflow variables
# ======================================================================

class TestWorkflowVariables:
    def test_set_and_get(self):
        wf = Workflow(name="t")
        wf.set_variable("color", "blue")
        assert wf.get_variable("color") == "blue"

    def test_overwrite(self):
        wf = Workflow(name="t")
        wf.set_variable("n", 1)
        wf.set_variable("n", 2)
        assert wf.get_variable("n") == 2

    def test_get_missing(self):
        wf = Workflow(name="t")
        assert wf.get_variable("nope") is None

    def test_default_value(self):
        wf = Workflow(
            name="t",
            variables=[WorkflowVariable(name="x", default=42)],
        )
        assert wf.get_variable("x") == 42

    def test_variable_type_validation(self):
        v = WorkflowVariable(name="n", var_type="number", value=42)
        assert v.validate_type()
        v.value = "not a number"
        assert not v.validate_type()


# ======================================================================
# 4. WorkflowEngine -- action steps
# ======================================================================

class TestEngineActionStep:
    async def test_execute_linear(self):
        wf = _make_linear_workflow(3)
        engine = WorkflowEngine()
        result = await engine.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        for s in result.steps:
            assert s.is_complete

    async def test_execute_with_input(self):
        wf = _make_linear_workflow(1)
        engine = WorkflowEngine()
        await engine.execute(wf, input_data={"key": "val"})
        assert wf.get_variable("key") == "val"

    async def test_empty_workflow(self):
        wf = Workflow(name="empty")
        engine = WorkflowEngine()
        result = await engine.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED


# ======================================================================
# 5. WorkflowEngine -- condition evaluation
# ======================================================================

class TestEngineCondition:
    async def test_true_condition(self):
        steps = [
            WorkflowStep(id="a", name="A"),
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="score > 5",
                depends_on=["a"],
            ),
            WorkflowStep(id="after", name="After", depends_on=["cond"]),
        ]
        wf = Workflow(name="cond", steps=steps)
        wf.set_variable("score", 10)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("cond").output is True

    async def test_false_condition(self):
        steps = [
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="score > 100",
            ),
        ]
        wf = Workflow(name="cond", steps=steps)
        wf.set_variable("score", 10)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("cond").output is False

    async def test_equality(self):
        steps = [
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="status == 'ok'",
            ),
        ]
        wf = Workflow(name="cond", steps=steps)
        wf.set_variable("status", "ok")
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("cond").output is True

    async def test_boolean_and(self):
        steps = [
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="a and b",
            ),
        ]
        wf = Workflow(name="cond", steps=steps)
        wf.set_variable("a", True)
        wf.set_variable("b", True)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("cond").output is True

    async def test_boolean_not(self):
        steps = [
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="not failed",
            ),
        ]
        wf = Workflow(name="cond", steps=steps)
        wf.set_variable("failed", False)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("cond").output is True

    async def test_in_operator(self):
        steps = [
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="color in ['red', 'blue']",
            ),
        ]
        wf = Workflow(name="cond", steps=steps)
        wf.set_variable("color", "blue")
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("cond").output is True

    async def test_step_output_reference(self):
        steps = [
            WorkflowStep(id="a", name="A"),
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="steps.a.output.status == 'completed'",
                depends_on=["a"],
            ),
        ]
        wf = Workflow(name="cond", steps=steps)
        engine = WorkflowEngine()
        await engine.execute(wf)
        # The default action output has status: "completed"
        assert wf.get_step("cond").output is True

    async def test_condition_branching(self):
        """Test that on_true/on_false routing works."""
        steps = [
            WorkflowStep(
                id="cond",
                name="Check",
                step_type=StepType.CONDITION,
                condition="val > 50",
                on_true="yes",
                on_false="no",
            ),
            WorkflowStep(id="yes", name="Yes Path", depends_on=["cond"]),
            WorkflowStep(id="no", name="No Path", depends_on=["cond"]),
        ]
        wf = Workflow(name="branch", steps=steps)
        wf.set_variable("val", 100)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("yes").status == "completed"
        assert wf.get_step("no").status == "skipped"


# ======================================================================
# 6. WorkflowEngine -- loop execution
# ======================================================================

class TestEngineLoop:
    async def test_basic_loop(self):
        body = WorkflowStep(id="body", name="Body", step_type=StepType.ACTION)
        loop = WorkflowStep(
            id="loop",
            name="Loop",
            step_type=StepType.LOOP,
            loop_over="items",
            loop_variable="item",
            loop_body=["body"],
        )
        wf = Workflow(name="loop", steps=[loop, body])
        wf.set_variable("items", [1, 2, 3])
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("loop").is_complete
        # Loop output should be a list of body outputs
        assert isinstance(wf.get_step("loop").output, list)
        assert len(wf.get_step("loop").output) == 3

    async def test_loop_max_iterations(self):
        body = WorkflowStep(id="body", name="Body")
        loop = WorkflowStep(
            id="loop",
            name="Loop",
            step_type=StepType.LOOP,
            loop_over="items",
            loop_body=["body"],
            max_iterations=2,
        )
        wf = Workflow(name="loop", steps=[loop, body])
        wf.set_variable("items", [1, 2, 3, 4, 5])
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert len(wf.get_step("loop").output) == 2


# ======================================================================
# 7. WorkflowEngine -- parallel execution
# ======================================================================

class TestEngineParallel:
    async def test_parallel_steps(self):
        """Steps with no mutual dependencies run in parallel."""
        steps = [
            WorkflowStep(id="a", name="A"),
            WorkflowStep(id="b", name="B"),
            WorkflowStep(id="c", name="C"),
            WorkflowStep(id="join", name="Join", depends_on=["a", "b", "c"]),
        ]
        wf = Workflow(name="parallel", steps=steps)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert all(s.is_complete for s in wf.steps)

    async def test_parallel_step_type(self):
        child1 = WorkflowStep(id="c1", name="C1")
        child2 = WorkflowStep(id="c2", name="C2")
        par = WorkflowStep(
            id="par",
            name="Parallel",
            step_type=StepType.PARALLEL,
            loop_body=["c1", "c2"],
        )
        wf = Workflow(name="par", steps=[par, child1, child2])
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("par").is_complete
        assert wf.get_step("c1").is_complete
        assert wf.get_step("c2").is_complete


# ======================================================================
# 8. WorkflowEngine -- approval flow
# ======================================================================

class TestEngineApproval:
    async def test_pre_approved(self):
        """Approval set before execution starts."""
        steps = [
            WorkflowStep(
                id="gate",
                name="Gate",
                step_type=StepType.APPROVAL,
                approval_message="Approve?",
            ),
            WorkflowStep(id="after", name="After", depends_on=["gate"]),
        ]
        wf = Workflow(name="approval", steps=steps)
        engine = WorkflowEngine()
        # Pre-approve
        await engine.approve(wf.id, "gate", True)
        await engine.execute(wf)
        assert wf.get_step("gate").is_complete
        assert wf.get_step("after").is_complete

    async def test_approval_rejected(self):
        steps = [
            WorkflowStep(
                id="gate",
                name="Gate",
                step_type=StepType.APPROVAL,
                approval_message="Approve?",
            ),
        ]
        wf = Workflow(name="approval", steps=steps)
        engine = WorkflowEngine()
        await engine.approve(wf.id, "gate", False)
        await engine.execute(wf)
        assert wf.get_step("gate").is_failed

    async def test_async_approval(self):
        """Approval arrives while workflow is waiting."""
        steps = [
            WorkflowStep(
                id="gate",
                name="Gate",
                step_type=StepType.APPROVAL,
                approval_message="Approve?",
            ),
            WorkflowStep(id="after", name="After", depends_on=["gate"]),
        ]
        wf = Workflow(name="approval", steps=steps)
        engine = WorkflowEngine()

        async def approve_later():
            await asyncio.sleep(0.05)
            await engine.approve(wf.id, "gate", True)

        task = asyncio.create_task(approve_later())
        await engine.execute(wf)
        # After pausing, the engine returns; resume to finish
        if wf.status == WorkflowStatus.PAUSED:
            await engine.resume(wf.id)
        await task
        assert wf.get_step("gate").is_complete


# ======================================================================
# 9. WorkflowEngine -- transform
# ======================================================================

class TestEngineTransform:
    async def test_upper(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="upper(greeting)",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("greeting", "hello")
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("t").output == "HELLO"

    async def test_lower(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="lower(greeting)",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("greeting", "WORLD")
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("t").output == "world"

    async def test_concat(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="concat(a, b)",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("a", "hello")
        wf.set_variable("b", " world")
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("t").output == "hello world"

    async def test_sum(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="sum(nums)",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("nums", [1, 2, 3, 4])
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("t").output == 10

    async def test_len_transform(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="len(items)",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("items", ["a", "b", "c"])
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("t").output == 3

    async def test_json_extract(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="json_extract(data, 'nested.key')",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("data", {"nested": {"key": "found"}})
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("t").output == "found"

    async def test_map_transform(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="map(users, 'name')",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("users", [{"name": "Alice"}, {"name": "Bob"}])
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.get_step("t").output == ["Alice", "Bob"]

    async def test_filter_transform(self):
        steps = [
            WorkflowStep(
                id="t",
                name="T",
                step_type=StepType.TRANSFORM,
                transform_expression="filter(users, 'role', 'admin')",
            ),
        ]
        wf = Workflow(name="tr", steps=steps)
        wf.set_variable("users", [
            {"name": "Alice", "role": "admin"},
            {"name": "Bob", "role": "user"},
        ])
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert len(wf.get_step("t").output) == 1
        assert wf.get_step("t").output[0]["name"] == "Alice"


# ======================================================================
# 10. Expression resolution
# ======================================================================

class TestExpressionResolution:
    def test_string_literal(self):
        engine = WorkflowEngine()
        wf = Workflow(name="t")
        assert engine._resolve_expression(wf, "'hello'") == "hello"

    def test_numeric_literal(self):
        engine = WorkflowEngine()
        wf = Workflow(name="t")
        assert engine._resolve_expression(wf, "42") == 42
        assert engine._resolve_expression(wf, "3.14") == 3.14

    def test_boolean_literal(self):
        engine = WorkflowEngine()
        wf = Workflow(name="t")
        assert engine._resolve_expression(wf, "true") is True
        assert engine._resolve_expression(wf, "false") is False

    def test_variable_reference(self):
        engine = WorkflowEngine()
        wf = Workflow(name="t")
        wf.set_variable("x", 99)
        assert engine._resolve_expression(wf, "x") == 99

    def test_step_output_reference(self):
        engine = WorkflowEngine()
        step = WorkflowStep(id="s1", name="S1")
        step.output = {"score": 0.9}
        wf = Workflow(name="t", steps=[step])
        assert engine._resolve_expression(wf, "steps.s1.output.score") == 0.9

    def test_list_literal(self):
        engine = WorkflowEngine()
        wf = Workflow(name="t")
        result = engine._resolve_expression(wf, "['a', 'b', 'c']")
        assert result == ["a", "b", "c"]

    def test_none_literal(self):
        engine = WorkflowEngine()
        wf = Workflow(name="t")
        assert engine._resolve_expression(wf, "none") is None


# ======================================================================
# 11. Template instantiation
# ======================================================================

class TestTemplateInstantiation:
    def test_basic_instantiation(self):
        tmpl = WorkflowTemplate(
            name="test",
            parameters=[
                WorkflowVariable(name="target", var_type="string", required=True),
            ],
            workflow=Workflow(
                name="Test WF",
                steps=[
                    WorkflowStep(
                        id="s1",
                        name="Deploy",
                        action="Deploy to {{target}}",
                    ),
                ],
            ),
        )
        wf = tmpl.instantiate({"target": "prod"})
        assert wf.id != tmpl.workflow.id  # new ID
        assert wf.steps[0].action == "Deploy to prod"
        assert wf.get_variable("target") == "prod"

    def test_missing_required_param(self):
        tmpl = WorkflowTemplate(
            name="test",
            parameters=[
                WorkflowVariable(name="x", required=True),
            ],
            workflow=Workflow(name="WF"),
        )
        with pytest.raises(ValueError, match="Required parameter"):
            tmpl.instantiate({})

    def test_default_param(self):
        tmpl = WorkflowTemplate(
            name="test",
            parameters=[
                WorkflowVariable(name="env", default="staging"),
            ],
            workflow=Workflow(
                name="WF",
                steps=[
                    WorkflowStep(id="s1", name="Deploy", action="Deploy to {{env}}"),
                ],
            ),
        )
        wf = tmpl.instantiate({})
        assert wf.steps[0].action == "Deploy to staging"
        assert wf.get_variable("env") == "staging"

    def test_placeholder_in_multiple_fields(self):
        tmpl = WorkflowTemplate(
            name="test",
            parameters=[
                WorkflowVariable(name="agent_name", required=True),
            ],
            workflow=Workflow(
                name="WF",
                steps=[
                    WorkflowStep(
                        id="s1",
                        name="Run",
                        agent="{{agent_name}}",
                        description="Executed by {{agent_name}}",
                    ),
                ],
            ),
        )
        wf = tmpl.instantiate({"agent_name": "my-agent"})
        assert wf.steps[0].agent == "my-agent"
        assert "my-agent" in wf.steps[0].description

    def test_template_does_not_mutate(self):
        tmpl = WorkflowTemplate(
            name="immutable",
            workflow=Workflow(
                name="WF",
                steps=[WorkflowStep(id="s1", name="S1", action="{{x}}")],
            ),
        )
        tmpl.instantiate({"x": "first"})
        # Template should still have placeholder
        assert "{{x}}" in tmpl.workflow.steps[0].action


# ======================================================================
# 12. Template registry
# ======================================================================

class TestTemplateRegistry:
    def test_register_and_get(self):
        reg = TemplateRegistry()
        tmpl = WorkflowTemplate(name="my-template")
        reg.register(tmpl)
        assert reg.get("my-template") is tmpl
        assert reg.get("nonexistent") is None

    def test_list_all(self):
        reg = TemplateRegistry()
        reg.register(WorkflowTemplate(name="a", category="devops"))
        reg.register(WorkflowTemplate(name="b", category="data"))
        assert len(reg.list_templates()) == 2

    def test_list_by_category(self):
        reg = TemplateRegistry()
        reg.register(WorkflowTemplate(name="a", category="devops"))
        reg.register(WorkflowTemplate(name="b", category="data"))
        assert len(reg.list_templates(category="devops")) == 1

    def test_search(self):
        reg = TemplateRegistry()
        reg.register(
            WorkflowTemplate(name="ci-cd", description="continuous integration")
        )
        reg.register(WorkflowTemplate(name="review", description="code review"))
        results = reg.search("continuous")
        assert len(results) == 1
        assert results[0].name == "ci-cd"

    def test_unregister(self):
        reg = TemplateRegistry()
        reg.register(WorkflowTemplate(name="x"))
        assert reg.unregister("x")
        assert reg.get("x") is None
        assert not reg.unregister("x")

    def test_categories(self):
        reg = TemplateRegistry()
        reg.register(WorkflowTemplate(name="a", category="devops"))
        reg.register(WorkflowTemplate(name="b", category="data"))
        reg.register(WorkflowTemplate(name="c", category="devops"))
        assert reg.categories() == ["data", "devops"]


# ======================================================================
# 13. Built-in templates
# ======================================================================

class TestBuiltinTemplates:
    def test_builtin_templates_load(self):
        templates = TemplateRegistry.builtin_templates()
        assert len(templates) >= 5
        names = {t.name for t in templates}
        assert "ci-cd-pipeline" in names
        assert "code-review" in names
        assert "data-analysis" in names
        assert "incident-response" in names
        assert "research-report" in names

    def test_builtin_templates_validate(self):
        for tmpl in TemplateRegistry.builtin_templates():
            errors = tmpl.workflow.validate()
            assert errors == [], f"Template '{tmpl.name}' has errors: {errors}"

    def test_ci_cd_instantiation(self):
        templates = TemplateRegistry.builtin_templates()
        ci_cd = next(t for t in templates if t.name == "ci-cd-pipeline")
        wf = ci_cd.instantiate({"project_path": "/my/project"})
        assert wf.get_variable("project_path") == "/my/project"
        assert wf.get_variable("deploy_target") == "staging"
        assert len(wf.steps) == 6


# ======================================================================
# 14. WorkflowStore save/load
# ======================================================================

class TestWorkflowStore:
    def test_save_and_load(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        wf = _make_linear_workflow()
        store.save(wf)
        loaded = store.load(wf.id)
        assert loaded is not None
        assert loaded.id == wf.id
        assert loaded.name == wf.name
        assert len(loaded.steps) == len(wf.steps)

    def test_load_missing(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        assert store.load("nope") is None

    def test_delete(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        wf = _make_linear_workflow()
        store.save(wf)
        assert store.delete(wf.id)
        assert store.load(wf.id) is None
        assert not store.delete(wf.id)

    def test_list_workflows(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        wf1 = Workflow(name="A", status=WorkflowStatus.COMPLETED)
        wf2 = Workflow(name="B", status=WorkflowStatus.FAILED)
        store.save(wf1)
        store.save(wf2)
        all_wf = store.list_workflows()
        assert len(all_wf) == 2
        completed = store.list_workflows(status=WorkflowStatus.COMPLETED)
        assert len(completed) == 1
        assert completed[0]["name"] == "A"

    def test_search_workflows(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        wf = Workflow(name="Deploy Pipeline", description="CI/CD workflow")
        store.save(wf)
        results = store.search("deploy")
        assert len(results) == 1
        assert results[0]["name"] == "Deploy Pipeline"

    def test_save_and_load_template(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        tmpl = WorkflowTemplate(name="my-tmpl", description="test")
        store.save_template(tmpl)
        loaded = store.load_template("my-tmpl")
        assert loaded is not None
        assert loaded.name == "my-tmpl"

    def test_list_templates(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        store.save_template(WorkflowTemplate(name="t1"))
        store.save_template(WorkflowTemplate(name="t2"))
        names = store.list_templates()
        assert "t1" in names
        assert "t2" in names

    def test_delete_template(self, tmp_path):
        store = WorkflowStore(str(tmp_path / "wf"))
        store.save_template(WorkflowTemplate(name="bye"))
        assert store.delete_template("bye")
        assert store.load_template("bye") is None


# ======================================================================
# 15. Workflow progress tracking
# ======================================================================

class TestWorkflowProgress:
    def test_progress_initial(self):
        wf = _make_linear_workflow(4)
        p = wf.progress
        assert p["total"] == 4
        assert p["pending"] == 4
        assert p["completed"] == 0
        assert p["percent_complete"] == 0.0

    def test_progress_partial(self):
        wf = _make_linear_workflow(4)
        wf.steps[0].mark_completed()
        wf.steps[1].mark_completed()
        p = wf.progress
        assert p["completed"] == 2
        assert p["pending"] == 2
        assert p["percent_complete"] == 50.0

    def test_progress_all_done(self):
        wf = _make_linear_workflow(3)
        for s in wf.steps:
            s.mark_completed()
        p = wf.progress
        assert p["percent_complete"] == 100.0

    def test_progress_with_skipped(self):
        wf = _make_linear_workflow(4)
        wf.steps[0].mark_completed()
        wf.steps[1].mark_skipped()
        p = wf.progress
        assert p["completed"] == 1
        assert p["skipped"] == 1
        assert p["percent_complete"] == 50.0

    def test_empty_workflow_progress(self):
        wf = Workflow(name="empty")
        p = wf.progress
        assert p["total"] == 0
        assert p["percent_complete"] == 0.0


# ======================================================================
# 16. Error handling
# ======================================================================

class TestErrorHandling:
    async def test_on_error_stop(self):
        """Default error handling stops the workflow."""

        class FailOrchestrator:
            async def execute_task(self, **kwargs):
                raise RuntimeError("fail")

        wf = _make_linear_workflow(2)
        wf.on_error = "stop"
        engine = WorkflowEngine(orchestrator=FailOrchestrator())
        await engine.execute(wf)
        assert wf.status == WorkflowStatus.FAILED
        assert wf.steps[0].is_failed

    async def test_on_error_skip(self):
        """Skip policy skips the failed step and continues."""

        class FailOnceOrchestrator:
            def __init__(self):
                self.calls = 0

            async def execute_task(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("fail")
                return {"ok": True}

        wf = _make_linear_workflow(2)
        wf.on_error = "skip"
        orch = FailOnceOrchestrator()
        engine = WorkflowEngine(orchestrator=orch)
        await engine.execute(wf)
        assert wf.steps[0].status == "skipped"
        assert wf.steps[1].is_complete
        assert wf.status == WorkflowStatus.COMPLETED

    async def test_on_error_retry(self):
        """Retry policy retries the step up to max_retries."""

        class FailThenSucceed:
            def __init__(self):
                self.calls = 0

            async def execute_task(self, **kwargs):
                self.calls += 1
                if self.calls <= 2:
                    raise RuntimeError("temporary fail")
                return {"ok": True}

        wf = _make_linear_workflow(1)
        wf.on_error = "retry"
        wf.steps[0].max_retries = 3
        orch = FailThenSucceed()
        engine = WorkflowEngine(orchestrator=orch)
        await engine.execute(wf)
        assert wf.steps[0].is_complete
        assert orch.calls == 3

    async def test_validation_failure(self):
        """Workflow with validation errors fails before executing."""
        wf = Workflow(
            name="bad",
            steps=[WorkflowStep(id="s", name="S", depends_on=["missing"])],
        )
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.status == WorkflowStatus.FAILED

    async def test_execution_log(self):
        wf = _make_linear_workflow(2)
        engine = WorkflowEngine()
        await engine.execute(wf)
        log = engine.get_execution_log(wf.id)
        assert len(log) > 0
        events = [e["event"] for e in log]
        assert "started" in events
        assert "finished" in events

    async def test_execution_log_filtering(self):
        wf1 = _make_linear_workflow(1)
        wf2 = _make_linear_workflow(1)
        engine = WorkflowEngine()
        await engine.execute(wf1)
        await engine.execute(wf2)
        log1 = engine.get_execution_log(wf1.id)
        log2 = engine.get_execution_log(wf2.id)
        assert all(e["workflow_id"] == wf1.id for e in log1)
        assert all(e["workflow_id"] == wf2.id for e in log2)


# ======================================================================
# 17. Sub-workflow execution
# ======================================================================

class TestSubWorkflow:
    async def test_sub_workflow_execution(self):
        child = Workflow(
            id="child-wf",
            name="Child",
            steps=[WorkflowStep(id="cs1", name="Child Step")],
        )
        parent_steps = [
            WorkflowStep(
                id="sw",
                name="Sub",
                step_type=StepType.SUB_WORKFLOW,
                sub_workflow_id="child-wf",
            ),
        ]
        parent = Workflow(name="Parent", steps=parent_steps)
        engine = WorkflowEngine()
        # Register child workflow
        engine._workflows["child-wf"] = child
        await engine.execute(parent)
        assert parent.get_step("sw").is_complete
        output = parent.get_step("sw").output
        assert output["status"] == "completed"

    async def test_sub_workflow_not_found(self):
        steps = [
            WorkflowStep(
                id="sw",
                name="Sub",
                step_type=StepType.SUB_WORKFLOW,
                sub_workflow_id="nonexistent",
            ),
        ]
        wf = Workflow(name="P", steps=steps)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert wf.status == WorkflowStatus.FAILED


# ======================================================================
# 18. Pause/Resume/Cancel
# ======================================================================

class TestPauseResumeCancel:
    async def test_cancel(self):
        wf = _make_linear_workflow(2)
        engine = WorkflowEngine()
        engine._workflows[wf.id] = wf
        wf.status = WorkflowStatus.RUNNING
        await engine.cancel(wf.id)
        assert wf.status == WorkflowStatus.CANCELLED


# ======================================================================
# 19. Additional model tests
# ======================================================================

class TestAdditionalModels:
    def test_workflow_trigger(self):
        trigger = WorkflowTrigger(trigger_type="cron", cron="0 * * * *")
        assert trigger.trigger_type == "cron"
        assert trigger.enabled

    def test_loop_step_model(self):
        ls = LoopStep(loop_over="items", body_steps=["s1", "s2"])
        assert ls.max_iterations == 100

    def test_sub_workflow_model(self):
        sw = SubWorkflow(workflow_id="abc", input_mapping={"x": "y"})
        assert sw.workflow_id == "abc"

    def test_conditional_branch(self):
        cb = ConditionalBranch(
            condition="x > 5",
            true_branch=["a"],
            false_branch=["b"],
        )
        assert cb.condition == "x > 5"

    def test_workflow_serialization(self):
        wf = _make_linear_workflow(2)
        wf.set_variable("key", "value")
        d = wf.to_dict()
        assert isinstance(d, dict)
        restored = Workflow.from_dict(d)
        assert restored.id == wf.id
        assert restored.get_variable("key") == "value"

    def test_workflow_add_remove_step(self):
        wf = Workflow(name="t")
        step = WorkflowStep(id="new", name="New")
        wf.add_step(step)
        assert wf.get_step("new") is not None
        assert wf.remove_step("new")
        assert wf.get_step("new") is None
        assert not wf.remove_step("new")  # already removed

    def test_workflow_get_step_by_name(self):
        wf = _make_linear_workflow(2)
        found = wf.get_step_by_name("Step 0")
        assert found is not None
        assert found.id == "s0"
        assert wf.get_step_by_name("nonexistent") is None

    async def test_workflow_reset_all(self):
        wf = _make_linear_workflow(3)
        engine = WorkflowEngine()
        await engine.execute(wf)
        assert all(s.is_complete for s in wf.steps)
        wf.reset_all_steps()
        assert all(s.is_pending for s in wf.steps)
        assert wf.status == WorkflowStatus.READY
