from __future__ import annotations

import pytest

from jarvis.app import JarvisApp
from jarvis.models.streaming_spec import SpecStatus, StepStatus


class TestSpecExecutor:
    @pytest.fixture
    async def app(self):
        j = JarvisApp()
        await j.initialize()
        yield j
        await j.shutdown()

    @pytest.mark.asyncio
    async def test_execute_spec_end_to_end(self, app: JarvisApp):
        spec = await app.spec_engine.create("review the code for security issues")
        assert spec.status == SpecStatus.EXECUTING
        assert len(spec.steps) == 4

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status == SpecStatus.COMPLETED
        assert all(s.status == StepStatus.COMPLETED for s in result.steps)
        assert all(s.output for s in result.steps)

    @pytest.mark.asyncio
    async def test_execute_single_step(self, app: JarvisApp):
        spec = await app.spec_engine.create("deploy to production")
        step_id = spec.steps[0].id

        result = await app.executor.execute_step(spec.id, step_id)
        assert result is not None
        assert result.success

        updated = app.spec_engine.get(spec.id)
        assert updated.steps[0].status == StepStatus.COMPLETED
        assert updated.steps[1].status == StepStatus.PENDING

    @pytest.mark.asyncio
    async def test_execute_respects_pause(self, app: JarvisApp):
        spec = await app.spec_engine.create("long running task")
        spec.status = SpecStatus.PAUSED

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert all(s.status in (StepStatus.PENDING, StepStatus.READY, StepStatus.BLOCKED) for s in result.steps)

    @pytest.mark.asyncio
    async def test_constraints_passed_to_agent(self, app: JarvisApp):
        spec = await app.spec_engine.create("review code changes")
        await app.spec_engine.add_constraint(spec.id, "no database changes allowed")

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status == SpecStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_spec_via_app(self, app: JarvisApp):
        result = await app.run_spec("help me with code testing")
        assert "steps" in result
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_chat_via_app(self, app: JarvisApp):
        output = await app.chat("review this code")
        assert output
        assert "CodeAgent" in output or "code" in output.lower()

    @pytest.mark.asyncio
    async def test_parallel_execution(self, app: JarvisApp):
        """Steps with no dependencies should all run in parallel.

        The fallback decomposition creates 4 independent steps.
        After one wave of parallel execution, all 4 should be completed.
        """
        spec = await app.spec_engine.create("parallel task")
        assert len(spec.steps) == 4

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status == SpecStatus.COMPLETED
        assert all(s.status == StepStatus.COMPLETED for s in result.steps)

    @pytest.mark.asyncio
    async def test_dag_execution_respects_dependencies(self, app: JarvisApp):
        """Steps with dependencies should not execute until deps are done."""
        spec = await app.spec_engine.create("dag execution task")
        a, b, c, d = spec.steps
        # Make step[1] depend on step[0], and step[3] depend on step[2]
        await app.spec_engine.add_dependency(spec.id, b.id, a.id)
        await app.spec_engine.add_dependency(spec.id, d.id, c.id)

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status == SpecStatus.COMPLETED
        assert all(s.status == StepStatus.COMPLETED for s in result.steps)

        # Verify ordering: B started after A completed
        step_b = result.get_step(b.id)
        step_a = result.get_step(a.id)
        assert step_b.started_at >= step_a.completed_at
