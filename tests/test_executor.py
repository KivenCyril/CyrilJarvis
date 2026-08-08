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
        # Step 1 depends on step 0 in the fallback chain -> now ready
        assert updated.steps[1].status == StepStatus.READY

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
        """Steps with no dependencies should all be ready in one wave.

        The fallback decomposition is a sequential chain; remove its edges
        so all 4 steps become independent, then verify readiness and
        completion.
        """
        spec = await app.spec_engine.create("parallel task")
        assert len(spec.steps) == 4
        s0, s1, s2, s3 = spec.steps
        await app.spec_engine.remove_dependency(spec.id, s1.id, s0.id)
        await app.spec_engine.remove_dependency(spec.id, s2.id, s1.id)
        await app.spec_engine.remove_dependency(spec.id, s3.id, s2.id)

        spec.update_step_readiness()
        assert len(spec.get_ready_steps()) == 4

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status == SpecStatus.COMPLETED
        assert all(s.status == StepStatus.COMPLETED for s in result.steps)

    @pytest.mark.asyncio
    async def test_dag_execution_respects_dependencies(self, app: JarvisApp):
        """Steps with dependencies should not execute until deps are done."""
        spec = await app.spec_engine.create("dag execution task")
        a, b, c, d = spec.steps
        # Fallback is the chain a->b->c->d; cut c's dep on b to get two
        # independent chains: a->b and c->d
        await app.spec_engine.remove_dependency(spec.id, c.id, b.id)

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status == SpecStatus.COMPLETED
        assert all(s.status == StepStatus.COMPLETED for s in result.steps)

        # Verify ordering: B started after A completed, D after C
        step_a = result.get_step(a.id)
        step_b = result.get_step(b.id)
        step_c = result.get_step(c.id)
        step_d = result.get_step(d.id)
        assert step_b.started_at >= step_a.completed_at
        assert step_d.started_at >= step_c.completed_at
        # Cross-chain independence: C ran in the first wave, not after B
        assert step_c.started_at < step_b.completed_at


class TestHonestFailure:
    """No synthesized success: unhandled steps must fail visibly."""

    @pytest.mark.asyncio
    async def test_unhandled_steps_fail_spec(self):
        import asyncio

        from jarvis.agents.orchestrator import Orchestrator
        from jarvis.agents.registry import AgentRegistry
        from jarvis.engine.executor import SpecExecutor
        from jarvis.engine.spec_engine import SpecEngine

        engine = SpecEngine()
        executor = SpecExecutor(engine, Orchestrator(AgentRegistry()))

        events: list[str] = []

        async def on_event(spec_id, event_type, data):
            events.append(event_type)

        engine.on_event(on_event)

        spec = await engine.create("task nobody can handle")
        result = await executor.execute_spec(spec.id)

        assert result is not None
        assert result.status == SpecStatus.FAILED
        # The executed step fails honestly; dependents are blocked on it
        assert result.steps[0].status == StepStatus.FAILED
        assert result.steps[0].error  # the real error is recorded
        assert all(s.status == StepStatus.BLOCKED for s in result.steps[1:])

        await asyncio.sleep(0.05)
        assert "spec_failed" in events
        assert "spec_completed" not in events
