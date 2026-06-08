"""Advanced tests for the JARVIS workflow engine.

Covers conditional branches, loops, parallel steps, approval gates,
transform steps, expression resolution, error handling policies,
workflow templates, template registry, workflow store, validation,
progress tracking, complex DAGs, sub-workflows, and pause/resume/cancel.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from jarvis.workflow.engine import WorkflowEngine
from jarvis.workflow.models import (
    ConditionalBranch,
    StepType,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    WorkflowVariable,
)
from jarvis.workflow.persistence import WorkflowStore
from jarvis.workflow.templates import TemplateRegistry, WorkflowTemplate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workflow(name: str = "test-wf") -> Workflow:
    """Create a minimal valid workflow."""
    return Workflow(name=name)


def _action_step(name: str, **kw: Any) -> WorkflowStep:
    return WorkflowStep(name=name, step_type=StepType.ACTION, **kw)


def _condition_step(name: str, condition: str, **kw: Any) -> WorkflowStep:
    return WorkflowStep(name=name, step_type=StepType.CONDITION, condition=condition, **kw)


# ===========================================================================
# 1. Conditional branches
# ===========================================================================


class TestConditionalBranches:
    """Workflow with condition steps that follow true/false paths."""

    @pytest.mark.asyncio
    async def test_condition_true_path(self):
        wf = _make_workflow()
        s1 = _action_step("Init")
        s_cond = _condition_step("Check", "score > 5", depends_on=[s1.id])
        s_true = _action_step("TrueBranch", depends_on=[s_cond.id])
        s_false = _action_step("FalseBranch", depends_on=[s_cond.id])

        s_cond.on_true = s_true.id
        s_cond.on_false = s_false.id

        wf.steps = [s1, s_cond, s_true, s_false]
        wf.set_variable("score", 10)

        engine = WorkflowEngine()
        result = await engine.execute(wf)

        assert result.status == WorkflowStatus.COMPLETED
        assert wf.get_step(s_true.id).status == "completed"
        assert wf.get_step(s_false.id).status == "skipped"

    @pytest.mark.asyncio
    async def test_condition_false_path(self):
        wf = _make_workflow()
        s_cond = _condition_step("Check", "score > 5")
        s_true = _action_step("TrueBranch", depends_on=[s_cond.id])
        s_false = _action_step("FalseBranch", depends_on=[s_cond.id])

        s_cond.on_true = s_true.id
        s_cond.on_false = s_false.id

        wf.steps = [s_cond, s_true, s_false]
        wf.set_variable("score", 2)

        engine = WorkflowEngine()
        result = await engine.execute(wf)

        assert result.status == WorkflowStatus.COMPLETED
        assert wf.get_step(s_true.id).status == "skipped"
        assert wf.get_step(s_false.id).status == "completed"

    @pytest.mark.asyncio
    async def test_condition_with_conditional_branch_objects(self):
        wf = _make_workflow()
        s_cond = _condition_step("Gate", "flag == true")
        s_a = _action_step("A", depends_on=[s_cond.id])
        s_b = _action_step("B", depends_on=[s_cond.id])

        wf.steps = [s_cond, s_a, s_b]
        wf.branches = [
            ConditionalBranch(condition="flag == true", true_branch=[s_a.id], false_branch=[s_b.id])
        ]
        wf.set_variable("flag", True)

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert wf.get_step(s_a.id).status == "completed"
        assert wf.get_step(s_b.id).status == "skipped"


# ===========================================================================
# 2. Loop steps
# ===========================================================================


class TestLoopSteps:
    """Workflow with loop steps iterating over a list."""

    @pytest.mark.asyncio
    async def test_loop_over_list(self):
        wf = _make_workflow()
        body = _action_step("ProcessItem")
        loop = WorkflowStep(
            name="Loop",
            step_type=StepType.LOOP,
            loop_over="items",
            loop_variable="item",
            loop_body=[body.id],
        )
        wf.steps = [loop, body]
        wf.set_variable("items", ["a", "b", "c"])

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert loop.status == "completed"
        assert isinstance(loop.output, list)
        assert len(loop.output) == 3

    @pytest.mark.asyncio
    async def test_loop_max_iterations(self):
        wf = _make_workflow()
        body = _action_step("Body")
        loop = WorkflowStep(
            name="CappedLoop",
            step_type=StepType.LOOP,
            loop_over="big_list",
            loop_variable="x",
            loop_body=[body.id],
            max_iterations=2,
        )
        wf.steps = [loop, body]
        wf.set_variable("big_list", list(range(10)))

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert len(loop.output) == 2

    @pytest.mark.asyncio
    async def test_loop_sets_loop_variable_and_index(self):
        wf = _make_workflow()
        body = _action_step("Body")
        loop = WorkflowStep(
            name="Loop",
            step_type=StepType.LOOP,
            loop_over="names",
            loop_variable="current_name",
            loop_body=[body.id],
        )
        wf.steps = [loop, body]
        wf.set_variable("names", ["alice", "bob"])

        engine = WorkflowEngine()
        await engine.execute(wf)

        # After the loop the variable holds the last item
        assert wf.get_variable("current_name") == "bob"
        assert wf.get_variable("loop_index") == 1


# ===========================================================================
# 3. Parallel steps
# ===========================================================================


class TestParallelSteps:
    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        wf = _make_workflow()
        c1 = _action_step("Child1")
        c2 = _action_step("Child2")
        c3 = _action_step("Child3")
        par = WorkflowStep(
            name="Parallel",
            step_type=StepType.PARALLEL,
            loop_body=[c1.id, c2.id, c3.id],
        )
        wf.steps = [par, c1, c2, c3]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert par.status == "completed"
        for c in (c1, c2, c3):
            assert c.status == "completed"

    @pytest.mark.asyncio
    async def test_parallel_implicit_children(self):
        """If loop_body is empty, parallel finds children that depend only on it."""
        wf = _make_workflow()
        par = WorkflowStep(name="Par", step_type=StepType.PARALLEL)
        c1 = _action_step("C1", depends_on=[par.id])
        c2 = _action_step("C2", depends_on=[par.id])
        wf.steps = [par, c1, c2]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert par.status == "completed"
        assert c1.status == "completed"
        assert c2.status == "completed"


# ===========================================================================
# 4. Approval gates
# ===========================================================================


class TestApprovalGates:
    @pytest.mark.asyncio
    async def test_pre_approved(self):
        wf = _make_workflow()
        s = WorkflowStep(
            name="Gate",
            step_type=StepType.APPROVAL,
            approval_message="Approve?",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        # Pre-approve
        key = f"{wf.id}:{s.id}"
        engine._approval_results[key] = True

        await engine.execute(wf)
        assert s.status == "completed"
        assert s.output == {"approved": True}

    @pytest.mark.asyncio
    async def test_pre_rejected(self):
        wf = _make_workflow()
        s = WorkflowStep(
            name="Gate",
            step_type=StepType.APPROVAL,
            approval_message="Approve deploy?",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        engine._approval_results[f"{wf.id}:{s.id}"] = False

        await engine.execute(wf)
        assert s.status == "failed"

    @pytest.mark.asyncio
    async def test_approval_pauses_then_resumes(self):
        wf = _make_workflow()
        s1 = _action_step("Before")
        s_gate = WorkflowStep(
            name="Gate",
            step_type=StepType.APPROVAL,
            approval_message="Ready?",
            depends_on=[s1.id],
        )
        s2 = _action_step("After", depends_on=[s_gate.id])
        wf.steps = [s1, s_gate, s2]

        engine = WorkflowEngine()

        async def _approve_later():
            await asyncio.sleep(0.05)
            await engine.approve(wf.id, s_gate.id, True)

        task = asyncio.create_task(_approve_later())
        await engine.execute(wf)
        await task

        # After approve + resume
        if wf.status == WorkflowStatus.PAUSED:
            await engine.resume(wf.id)

        assert wf.status == WorkflowStatus.COMPLETED
        assert s2.status == "completed"


# ===========================================================================
# 5. Transform steps
# ===========================================================================


class TestTransformSteps:
    @pytest.mark.asyncio
    async def test_upper_transform(self):
        wf = _make_workflow()
        wf.set_variable("msg", "hello")
        s = WorkflowStep(
            name="Upper",
            step_type=StepType.TRANSFORM,
            transform_expression="upper(msg)",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.output == "HELLO"

    @pytest.mark.asyncio
    async def test_lower_transform(self):
        wf = _make_workflow()
        wf.set_variable("msg", "WORLD")
        s = WorkflowStep(
            name="Lower",
            step_type=StepType.TRANSFORM,
            transform_expression="lower(msg)",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.output == "world"

    @pytest.mark.asyncio
    async def test_concat_transform(self):
        wf = _make_workflow()
        wf.set_variable("a", "foo")
        wf.set_variable("b", "bar")
        s = WorkflowStep(
            name="Concat",
            step_type=StepType.TRANSFORM,
            transform_expression="concat(a, b)",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.output == "foobar"

    @pytest.mark.asyncio
    async def test_json_extract(self):
        wf = _make_workflow()
        wf.set_variable("data", {"a": {"b": 42}})
        s = WorkflowStep(
            name="Extract",
            step_type=StepType.TRANSFORM,
            transform_expression="json_extract(data, 'a.b')",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.output == 42

    @pytest.mark.asyncio
    async def test_sum_transform(self):
        wf = _make_workflow()
        wf.set_variable("nums", [1, 2, 3, 4])
        s = WorkflowStep(
            name="Sum",
            step_type=StepType.TRANSFORM,
            transform_expression="sum(nums)",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.output == 10

    @pytest.mark.asyncio
    async def test_len_transform(self):
        wf = _make_workflow()
        wf.set_variable("items", [10, 20, 30])
        s = WorkflowStep(
            name="Len",
            step_type=StepType.TRANSFORM,
            transform_expression="len(items)",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.output == 3

    @pytest.mark.asyncio
    async def test_map_transform(self):
        wf = _make_workflow()
        wf.set_variable("records", [{"name": "a"}, {"name": "b"}])
        s = WorkflowStep(
            name="Map",
            step_type=StepType.TRANSFORM,
            transform_expression="map(records, 'name')",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.output == ["a", "b"]

    @pytest.mark.asyncio
    async def test_filter_transform(self):
        wf = _make_workflow()
        wf.set_variable("records", [
            {"status": "ok", "v": 1},
            {"status": "fail", "v": 2},
            {"status": "ok", "v": 3},
        ])
        s = WorkflowStep(
            name="Filter",
            step_type=StepType.TRANSFORM,
            transform_expression="filter(records, 'status', 'ok')",
        )
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert len(s.output) == 2
        assert all(r["status"] == "ok" for r in s.output)


# ===========================================================================
# 6. Expression resolution
# ===========================================================================


class TestExpressionResolution:
    def test_literal_string(self):
        wf = _make_workflow()
        engine = WorkflowEngine()
        assert engine._resolve_expression(wf, "'hello'") == "hello"
        assert engine._resolve_expression(wf, '"world"') == "world"

    def test_literal_number(self):
        wf = _make_workflow()
        engine = WorkflowEngine()
        assert engine._resolve_expression(wf, "42") == 42
        assert engine._resolve_expression(wf, "3.14") == 3.14

    def test_literal_boolean(self):
        wf = _make_workflow()
        engine = WorkflowEngine()
        assert engine._resolve_expression(wf, "true") is True
        assert engine._resolve_expression(wf, "false") is False
        assert engine._resolve_expression(wf, "none") is None

    def test_variable_resolution(self):
        wf = _make_workflow()
        wf.set_variable("x", 99)
        engine = WorkflowEngine()
        assert engine._resolve_expression(wf, "x") == 99

    def test_step_output_reference(self):
        wf = _make_workflow()
        s = _action_step("DoStuff")
        s.mark_completed({"score": 0.95})
        wf.steps = [s]
        engine = WorkflowEngine()
        assert engine._resolve_step_ref(wf, f"steps.{s.id}.output.score") == 0.95

    def test_step_by_name_reference(self):
        wf = _make_workflow()
        s = _action_step("DoStuff")
        s.mark_completed({"val": "ok"})
        wf.steps = [s]
        engine = WorkflowEngine()
        assert engine._resolve_step_ref(wf, "steps.DoStuff.output.val") == "ok"

    def test_nested_path_resolution(self):
        wf = _make_workflow()
        s = _action_step("Deep")
        s.mark_completed({"level1": {"level2": {"level3": "deep_value"}}})
        wf.steps = [s]
        engine = WorkflowEngine()
        val = engine._resolve_step_ref(wf, f"steps.{s.id}.output.level1.level2.level3")
        assert val == "deep_value"

    def test_list_literal(self):
        wf = _make_workflow()
        engine = WorkflowEngine()
        result = engine._resolve_expression(wf, "['a', 'b', 'c']")
        assert result == ["a", "b", "c"]

    def test_empty_list_literal(self):
        wf = _make_workflow()
        engine = WorkflowEngine()
        assert engine._resolve_expression(wf, "[]") == []


# ===========================================================================
# 7. Error handling policies
# ===========================================================================


class TestErrorHandlingPolicies:
    @pytest.mark.asyncio
    async def test_stop_policy_on_error(self):
        wf = _make_workflow()
        wf.on_error = "stop"
        s1 = _action_step("WillFail")
        s2 = _action_step("NeverReached", depends_on=[s1.id])
        wf.steps = [s1, s2]

        class FailOrchestrator:
            async def execute_task(self, **kw: Any) -> None:
                raise RuntimeError("boom")

        engine = WorkflowEngine(orchestrator=FailOrchestrator())
        await engine.execute(wf)

        assert wf.status == WorkflowStatus.FAILED
        assert s1.status == "failed"
        assert s2.status == "pending"

    @pytest.mark.asyncio
    async def test_skip_policy_on_error(self):
        wf = _make_workflow()
        wf.on_error = "skip"
        s1 = _action_step("WillFail")
        s2 = _action_step("ShouldRun", depends_on=[s1.id])
        wf.steps = [s1, s2]

        call_count = 0

        class FailOnceOrchestrator:
            async def execute_task(self, **kw: Any) -> dict:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("boom")
                return {"ok": True}

        engine = WorkflowEngine(orchestrator=FailOnceOrchestrator())
        await engine.execute(wf)

        assert s1.status == "skipped"
        assert s2.status == "completed"

    @pytest.mark.asyncio
    async def test_retry_policy_on_error(self):
        wf = _make_workflow()
        wf.on_error = "retry"
        s1 = _action_step("Flaky")
        s1.max_retries = 2
        wf.steps = [s1]

        attempt = 0

        class FlakyOrchestrator:
            async def execute_task(self, **kw: Any) -> dict:
                nonlocal attempt
                attempt += 1
                if attempt < 3:
                    raise RuntimeError("transient")
                return {"ok": True}

        engine = WorkflowEngine(orchestrator=FlakyOrchestrator())
        await engine.execute(wf)

        assert s1.status == "completed"
        assert attempt == 3


# ===========================================================================
# 8. Workflow template instantiation and rendering
# ===========================================================================


class TestWorkflowTemplateInstantiation:
    def test_template_instantiate_basic(self):
        tpl = WorkflowTemplate(
            name="test-tpl",
            parameters=[WorkflowVariable(name="env", required=True)],
            workflow=Workflow(
                name="Deploy",
                steps=[
                    WorkflowStep(name="Deploy", action="Deploy to {{env}}")
                ],
            ),
        )
        wf = tpl.instantiate({"env": "production"})
        assert wf.id != tpl.workflow.id
        assert wf.steps[0].action == "Deploy to production"
        assert wf.get_variable("env") == "production"

    def test_template_missing_required_raises(self):
        tpl = WorkflowTemplate(
            name="need-param",
            parameters=[WorkflowVariable(name="key", required=True)],
            workflow=Workflow(name="W"),
        )
        with pytest.raises(ValueError, match="Required parameter"):
            tpl.instantiate({})

    def test_template_default_values(self):
        tpl = WorkflowTemplate(
            name="defaults",
            parameters=[
                WorkflowVariable(name="target", default="staging"),
            ],
            workflow=Workflow(
                name="W",
                steps=[WorkflowStep(name="S", action="Deploy to {{target}}")],
            ),
        )
        wf = tpl.instantiate({})
        assert wf.steps[0].action == "Deploy to staging"

    def test_placeholder_replacement_in_all_fields(self):
        tpl = WorkflowTemplate(
            name="full",
            parameters=[WorkflowVariable(name="svc", required=True)],
            workflow=Workflow(
                name="W",
                steps=[
                    WorkflowStep(
                        name="S",
                        description="Desc {{svc}}",
                        agent="{{svc}}-agent",
                        condition="{{svc}} > 0",
                        tool="{{svc}}_tool",
                        approval_message="Approve {{svc}}?",
                        transform_expression="upper({{svc}})",
                    )
                ],
            ),
        )
        wf = tpl.instantiate({"svc": "myapp"})
        s = wf.steps[0]
        assert "myapp" in s.description
        assert s.agent == "myapp-agent"
        assert "myapp" in s.condition
        assert s.tool == "myapp_tool"
        assert "myapp" in s.approval_message
        assert "myapp" in s.transform_expression


# ===========================================================================
# 9. Template registry CRUD
# ===========================================================================


class TestTemplateRegistryCRUD:
    def test_register_and_get(self):
        reg = TemplateRegistry()
        tpl = WorkflowTemplate(name="x", workflow=Workflow(name="X"))
        reg.register(tpl)
        assert reg.get("x") is tpl

    def test_unregister(self):
        reg = TemplateRegistry()
        tpl = WorkflowTemplate(name="y", workflow=Workflow(name="Y"))
        reg.register(tpl)
        assert reg.unregister("y") is True
        assert reg.get("y") is None
        assert reg.unregister("y") is False

    def test_list_templates_by_category(self):
        reg = TemplateRegistry()
        reg.register(WorkflowTemplate(name="a", category="dev", workflow=Workflow(name="A")))
        reg.register(WorkflowTemplate(name="b", category="ops", workflow=Workflow(name="B")))
        reg.register(WorkflowTemplate(name="c", category="dev", workflow=Workflow(name="C")))
        assert len(reg.list_templates(category="dev")) == 2
        assert len(reg.list_templates(category="ops")) == 1
        assert len(reg.list_templates()) == 3

    def test_search(self):
        reg = TemplateRegistry()
        reg.register(WorkflowTemplate(name="deploy-pipeline", description="Deploys code", workflow=Workflow(name="D")))
        reg.register(WorkflowTemplate(name="data-etl", description="ETL job", workflow=Workflow(name="E")))
        matches = reg.search("deploy")
        assert len(matches) == 1
        assert matches[0].name == "deploy-pipeline"

    def test_categories(self):
        reg = TemplateRegistry()
        reg.register(WorkflowTemplate(name="a", category="alpha", workflow=Workflow(name="A")))
        reg.register(WorkflowTemplate(name="b", category="beta", workflow=Workflow(name="B")))
        cats = reg.categories()
        assert "alpha" in cats
        assert "beta" in cats

    def test_builtin_templates_count(self):
        templates = TemplateRegistry.builtin_templates()
        assert len(templates) >= 5


# ===========================================================================
# 10. WorkflowStore CRUD
# ===========================================================================


class TestWorkflowStoreCRUD:
    def test_save_load_roundtrip(self, tmp_path: Path):
        store = WorkflowStore(storage_path=str(tmp_path / "wf_store"))
        wf = Workflow(name="Test WF", tags=["t1"], description="desc")
        wf.add_step(_action_step("Step1"))
        store.save(wf)

        loaded = store.load(wf.id)
        assert loaded is not None
        assert loaded.name == "Test WF"
        assert loaded.tags == ["t1"]
        assert len(loaded.steps) == 1

    def test_delete(self, tmp_path: Path):
        store = WorkflowStore(storage_path=str(tmp_path / "wf_store"))
        wf = Workflow(name="ToDelete")
        store.save(wf)
        assert store.delete(wf.id) is True
        assert store.load(wf.id) is None
        assert store.delete(wf.id) is False

    def test_list_workflows(self, tmp_path: Path):
        store = WorkflowStore(storage_path=str(tmp_path / "wf_store"))
        wf1 = Workflow(name="A")
        wf2 = Workflow(name="B")
        store.save(wf1)
        store.save(wf2)
        listing = store.list_workflows()
        assert len(listing) == 2

    def test_list_by_status(self, tmp_path: Path):
        store = WorkflowStore(storage_path=str(tmp_path / "wf_store"))
        wf1 = Workflow(name="Draft1", status=WorkflowStatus.DRAFT)
        wf2 = Workflow(name="Run1", status=WorkflowStatus.RUNNING)
        store.save(wf1)
        store.save(wf2)
        drafts = store.list_workflows(status=WorkflowStatus.DRAFT)
        assert len(drafts) == 1
        assert drafts[0]["name"] == "Draft1"

    def test_search(self, tmp_path: Path):
        store = WorkflowStore(storage_path=str(tmp_path / "wf_store"))
        store.save(Workflow(name="Deploy Pipeline", description="CI/CD"))
        store.save(Workflow(name="Data ETL", description="ETL job"))
        results = store.search("deploy")
        assert len(results) == 1

    def test_template_save_load(self, tmp_path: Path):
        store = WorkflowStore(storage_path=str(tmp_path / "wf_store"))
        tpl = WorkflowTemplate(name="my-tpl", description="Custom", workflow=Workflow(name="T"))
        store.save_template(tpl)
        loaded = store.load_template("my-tpl")
        assert loaded is not None
        assert loaded.description == "Custom"

    def test_template_list_delete(self, tmp_path: Path):
        store = WorkflowStore(storage_path=str(tmp_path / "wf_store"))
        store.save_template(WorkflowTemplate(name="tpl-a", workflow=Workflow(name="A")))
        store.save_template(WorkflowTemplate(name="tpl-b", workflow=Workflow(name="B")))
        assert len(store.list_templates()) == 2
        assert store.delete_template("tpl-a") is True
        assert len(store.list_templates()) == 1
        assert store.delete_template("tpl-a") is False


# ===========================================================================
# 11. Workflow validation
# ===========================================================================


class TestWorkflowValidation:
    def test_valid_workflow_no_errors(self):
        wf = _make_workflow()
        s1 = _action_step("A")
        s2 = _action_step("B", depends_on=[s1.id])
        wf.steps = [s1, s2]
        assert wf.validate() == []

    def test_duplicate_step_ids(self):
        wf = _make_workflow()
        s1 = _action_step("A")
        s2 = _action_step("B")
        s2.id = s1.id  # duplicate
        wf.steps = [s1, s2]
        errors = wf.validate()
        assert any("Duplicate" in e for e in errors)

    def test_unknown_dependency(self):
        wf = _make_workflow()
        s1 = _action_step("A", depends_on=["nonexistent"])
        wf.steps = [s1]
        errors = wf.validate()
        assert any("unknown" in e.lower() for e in errors)

    def test_condition_step_without_condition(self):
        wf = _make_workflow()
        s = WorkflowStep(name="NoCond", step_type=StepType.CONDITION)
        wf.steps = [s]
        errors = wf.validate()
        assert any("condition" in e.lower() for e in errors)

    def test_loop_step_without_loop_over(self):
        wf = _make_workflow()
        s = WorkflowStep(name="NoLoop", step_type=StepType.LOOP)
        wf.steps = [s]
        errors = wf.validate()
        assert any("loop_over" in e.lower() for e in errors)

    def test_sub_workflow_without_id(self):
        wf = _make_workflow()
        s = WorkflowStep(name="NoSubId", step_type=StepType.SUB_WORKFLOW)
        wf.steps = [s]
        errors = wf.validate()
        assert any("sub_workflow_id" in e.lower() for e in errors)

    def test_required_variable_missing(self):
        wf = _make_workflow()
        wf.variables = [WorkflowVariable(name="req_var", required=True)]
        errors = wf.validate()
        assert any("Required variable" in e for e in errors)


# ===========================================================================
# 12. Workflow progress tracking
# ===========================================================================


class TestWorkflowProgress:
    def test_progress_all_pending(self):
        wf = _make_workflow()
        wf.steps = [_action_step("A"), _action_step("B"), _action_step("C")]
        p = wf.progress
        assert p["total"] == 3
        assert p["pending"] == 3
        assert p["percent_complete"] == 0.0

    def test_progress_mixed(self):
        wf = _make_workflow()
        s1 = _action_step("A")
        s2 = _action_step("B")
        s3 = _action_step("C")
        s1.mark_completed()
        s3.mark_skipped()
        wf.steps = [s1, s2, s3]
        p = wf.progress
        assert p["completed"] == 1
        assert p["skipped"] == 1
        assert p["pending"] == 1
        assert p["percent_complete"] == pytest.approx(66.7, abs=0.1)

    @pytest.mark.asyncio
    async def test_progress_after_execution(self):
        wf = _make_workflow()
        wf.steps = [_action_step("A"), _action_step("B")]
        engine = WorkflowEngine()
        await engine.execute(wf)
        p = wf.progress
        assert p["completed"] == 2
        assert p["percent_complete"] == 100.0


# ===========================================================================
# 13. Complex DAG with mixed step types
# ===========================================================================


class TestComplexDAG:
    @pytest.mark.asyncio
    async def test_diamond_dag(self):
        wf = _make_workflow()
        s_start = _action_step("Start")
        s_a = _action_step("A", depends_on=[s_start.id])
        s_b = _action_step("B", depends_on=[s_start.id])
        s_end = _action_step("End", depends_on=[s_a.id, s_b.id])
        wf.steps = [s_start, s_a, s_b, s_end]

        engine = WorkflowEngine()
        await engine.execute(wf)

        for s in wf.steps:
            assert s.status == "completed"

    @pytest.mark.asyncio
    async def test_mixed_action_and_transform(self):
        wf = _make_workflow()
        wf.set_variable("greeting", "hello world")
        s1 = _action_step("Act")
        s2 = WorkflowStep(
            name="Transform",
            step_type=StepType.TRANSFORM,
            transform_expression="upper(greeting)",
            depends_on=[s1.id],
        )
        wf.steps = [s1, s2]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s2.output == "HELLO WORLD"


# ===========================================================================
# 14. Sub-workflow execution
# ===========================================================================


class TestSubWorkflow:
    @pytest.mark.asyncio
    async def test_sub_workflow_basic(self):
        sub = Workflow(name="SubWF", id="sub-1")
        sub.add_step(_action_step("SubStep"))

        parent = _make_workflow()
        s_sub = WorkflowStep(
            name="RunSub",
            step_type=StepType.SUB_WORKFLOW,
            sub_workflow_id="sub-1",
        )
        parent.steps = [s_sub]

        engine = WorkflowEngine()
        engine._workflows["sub-1"] = sub

        await engine.execute(parent)

        assert s_sub.status == "completed"
        assert s_sub.output["status"] == "completed"

    @pytest.mark.asyncio
    async def test_sub_workflow_input_mapping(self):
        sub = Workflow(name="SubWF", id="sub-input")
        sub.add_step(_action_step("S"))

        parent = _make_workflow()
        parent.set_variable("parent_val", "hello")
        s = WorkflowStep(
            name="RunSub",
            step_type=StepType.SUB_WORKFLOW,
            sub_workflow_id="sub-input",
            sub_workflow_input={"child_var": "parent_val"},
        )
        parent.steps = [s]

        engine = WorkflowEngine()
        engine._workflows["sub-input"] = sub

        await engine.execute(parent)

        assert sub.get_variable("child_var") == "hello"

    @pytest.mark.asyncio
    async def test_sub_workflow_not_found(self):
        parent = _make_workflow()
        s = WorkflowStep(
            name="MissingSub",
            step_type=StepType.SUB_WORKFLOW,
            sub_workflow_id="nonexistent",
        )
        parent.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(parent)

        assert parent.status == WorkflowStatus.FAILED


# ===========================================================================
# 15. Pause / resume / cancel
# ===========================================================================


class TestPauseResumeCancel:
    @pytest.mark.asyncio
    async def test_cancel_workflow(self):
        wf = _make_workflow()
        wf.steps = [_action_step("A")]

        engine = WorkflowEngine()
        engine._workflows[wf.id] = wf
        wf.status = WorkflowStatus.RUNNING

        await engine.cancel(wf.id)
        assert wf.status == WorkflowStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_pause_and_resume(self):
        wf = _make_workflow()
        wf.steps = [_action_step("A"), _action_step("B")]

        engine = WorkflowEngine()
        engine._workflows[wf.id] = wf
        wf.status = WorkflowStatus.RUNNING

        await engine.pause(wf.id)
        assert wf.status == WorkflowStatus.PAUSED

        await engine.resume(wf.id)
        assert wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING)

    @pytest.mark.asyncio
    async def test_execution_log_populated(self):
        wf = _make_workflow()
        wf.steps = [_action_step("A")]

        engine = WorkflowEngine()
        await engine.execute(wf)

        log = engine.get_execution_log(wf.id)
        assert len(log) >= 2
        events = [e["event"] for e in log]
        assert "started" in events
        assert "finished" in events

    @pytest.mark.asyncio
    async def test_execution_log_filtering(self):
        wf1 = Workflow(name="WF1", id="wf1")
        wf1.steps = [_action_step("A")]
        wf2 = Workflow(name="WF2", id="wf2")
        wf2.steps = [_action_step("B")]

        engine = WorkflowEngine()
        await engine.execute(wf1)
        await engine.execute(wf2)

        log1 = engine.get_execution_log("wf1")
        log2 = engine.get_execution_log("wf2")
        assert all(e["workflow_id"] == "wf1" for e in log1)
        assert all(e["workflow_id"] == "wf2" for e in log2)


# ===========================================================================
# 16. Workflow model helpers
# ===========================================================================


class TestWorkflowModelHelpers:
    def test_add_and_remove_step(self):
        wf = _make_workflow()
        s = _action_step("X")
        wf.add_step(s)
        assert len(wf.steps) == 1
        assert wf.remove_step(s.id) is True
        assert len(wf.steps) == 0
        assert wf.remove_step("ghost") is False

    def test_remove_step_cleans_deps(self):
        wf = _make_workflow()
        s1 = _action_step("A")
        s2 = _action_step("B", depends_on=[s1.id])
        wf.steps = [s1, s2]
        wf.remove_step(s1.id)
        assert s1.id not in s2.depends_on

    def test_reset_all_steps(self):
        wf = _make_workflow()
        s1 = _action_step("A")
        s1.mark_completed("done")
        wf.steps = [s1]
        wf.reset_all_steps()
        assert s1.status == "pending"
        assert wf.status == WorkflowStatus.READY

    def test_to_dict_and_from_dict(self):
        wf = _make_workflow()
        wf.add_step(_action_step("S"))
        wf.set_variable("x", 42)
        data = wf.to_dict()
        wf2 = Workflow.from_dict(data)
        assert wf2.id == wf.id
        assert wf2.get_variable("x") == 42

    def test_step_duration(self):
        s = _action_step("S")
        assert s.duration_seconds is None
        s.mark_running()
        s.mark_completed()
        assert s.duration_seconds is not None
        assert s.duration_seconds >= 0

    def test_get_step_by_name(self):
        wf = _make_workflow()
        s = _action_step("MyStep")
        wf.steps = [s]
        assert wf.get_step_by_name("mystep") is s
        assert wf.get_step_by_name("MYSTEP") is s
        assert wf.get_step_by_name("other") is None


# ===========================================================================
# 17. Boolean expression evaluation
# ===========================================================================


class TestBooleanExpressions:
    def _eval(self, wf: Workflow, expr: str) -> bool:
        engine = WorkflowEngine()
        return engine._eval_expression(wf, expr)

    def test_and_expression(self):
        wf = _make_workflow()
        wf.set_variable("a", True)
        wf.set_variable("b", True)
        assert self._eval(wf, "a and b") is True

    def test_or_expression(self):
        wf = _make_workflow()
        wf.set_variable("a", False)
        wf.set_variable("b", True)
        assert self._eval(wf, "a or b") is True

    def test_not_expression(self):
        wf = _make_workflow()
        wf.set_variable("flag", False)
        assert self._eval(wf, "not flag") is True

    def test_comparison_operators(self):
        wf = _make_workflow()
        wf.set_variable("x", 10)
        assert self._eval(wf, "x > 5") is True
        assert self._eval(wf, "x < 5") is False
        assert self._eval(wf, "x >= 10") is True
        assert self._eval(wf, "x <= 10") is True
        assert self._eval(wf, "x == 10") is True
        assert self._eval(wf, "x != 10") is False

    def test_in_expression(self):
        wf = _make_workflow()
        wf.set_variable("val", "a")
        assert self._eval(wf, "val in ['a', 'b', 'c']") is True

    def test_not_in_expression(self):
        wf = _make_workflow()
        wf.set_variable("val", "d")
        assert self._eval(wf, "val not in ['a', 'b']") is True


# ===========================================================================
# 18. Wait step
# ===========================================================================


class TestWaitStep:
    @pytest.mark.asyncio
    async def test_wait_zero_seconds(self):
        wf = _make_workflow()
        s = WorkflowStep(name="NoWait", step_type=StepType.WAIT, wait_seconds=0)
        wf.steps = [s]

        engine = WorkflowEngine()
        await engine.execute(wf)

        assert s.status == "completed"
        assert s.output == {"waited": 0}
