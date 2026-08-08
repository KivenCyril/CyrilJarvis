from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from jarvis.agents.base import AgentContext, TaskResult
from jarvis.agents.orchestrator import Orchestrator
from jarvis.engine.spec_engine import SpecEngine
from jarvis.models.streaming_spec import (
    ChangeSource,
    SpecStatus,
    StepStatus,
    StreamingSpec,
    Step,
)

logger = logging.getLogger(__name__)

FinishCallback = Callable[[StreamingSpec], Awaitable[None]]


class SpecExecutor:
    """DAG-aware executor that runs steps in parallel when possible.

    Execution strategy:
    1. Compute readiness -- find all READY steps (dependencies met)
    2. Execute them in parallel via ``asyncio.gather``
    3. On completion, recompute readiness (new steps may become READY)
    4. Repeat until all steps are done or the spec is paused/failed
    5. Between waves, re-fetch the spec so user edits are respected
       (human-in-the-loop)
    """

    def __init__(self, spec_engine: SpecEngine, orchestrator: Orchestrator) -> None:
        self.spec_engine = spec_engine
        self.orchestrator = orchestrator
        # Fired once per finished spec (COMPLETED or FAILED), e.g. for the
        # skill self-evolution feedback loop.
        self.on_finish: list[FinishCallback] = []

    # ── Full-spec execution ─────────────────────────────────────────────

    async def execute_spec(self, spec_id: str) -> StreamingSpec | None:
        """Execute a Streaming Spec with DAG-aware parallel scheduling."""
        spec = self.spec_engine.get(spec_id)
        if not spec:
            logger.error("Spec %s not found", spec_id)
            return None

        logger.info("Starting execution of spec '%s' (%s)", spec.name, spec_id)

        # Initial readiness update
        self._update_step_readiness(spec)

        while True:
            # Re-fetch spec in case the user edited it between waves
            spec = self.spec_engine.get(spec_id)
            if not spec:
                break

            # Respect user changes: stop if spec was paused/redirected/completed
            if spec.status in (
                SpecStatus.PAUSED,
                SpecStatus.REDIRECTED,
                SpecStatus.COMPLETED,
                SpecStatus.FAILED,
            ):
                logger.info(
                    "Spec status is %s, stopping execution", spec.status.value
                )
                break

            ready_steps = spec.get_ready_steps()

            if not ready_steps:
                # Nothing can run: finalize terminal status (COMPLETED /
                # FAILED) and emit the matching event, then stop.
                await self.spec_engine.finalize(spec_id)
                break

            # Execute all ready steps in parallel
            tasks = [
                self._execute_single_step(spec_id, step) for step in ready_steps
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Recompute readiness for the next wave
            spec = self.spec_engine.get(spec_id)
            if spec:
                self._update_step_readiness(spec)

        spec = self.spec_engine.get(spec_id)
        if spec:
            for callback in self.on_finish:
                try:
                    await callback(spec)
                except Exception:
                    logger.exception("on_finish callback failed for spec %s", spec_id)
        return spec

    # ── Single-step execution ───────────────────────────────────────────

    async def execute_step(self, spec_id: str, step_id: str) -> TaskResult | None:
        """Execute a single specific step (regardless of DAG readiness)."""
        spec = self.spec_engine.get(spec_id)
        if not spec:
            return None

        step = spec.get_step(step_id)
        if not step:
            return None

        return await self._execute_single_step(spec_id, step)

    # ── Internals ───────────────────────────────────────────────────────

    def _update_step_readiness(self, spec: StreamingSpec) -> None:
        """Delegate readiness computation to the model."""
        spec.update_step_readiness()

    async def _execute_single_step(
        self, spec_id: str, step: Step
    ) -> TaskResult:
        """Execute one step with retry logic."""
        spec = self.spec_engine.get(spec_id)
        if not spec:
            return TaskResult(
                task_id="unknown",
                agent_name="executor",
                success=False,
                error=f"Spec {spec_id} not found",
            )

        # Mark step as executing
        await self.spec_engine.update_step(
            spec_id, step.id, status=StepStatus.EXECUTING
        )

        # Build context with spec constraints
        context = AgentContext(
            spec_id=spec_id,
            step_id=step.id,
            constraints=[c.content for c in spec.constraints if c.active],
        )

        # Compose the message
        message = (
            f"{spec.intent} — {step.name}: {step.description}"
            if step.description
            else f"{spec.intent} — {step.name}"
        )
        if context.constraints:
            message += f"\n\nConstraints: {'; '.join(context.constraints)}"

        # Retry loop
        last_result: TaskResult | None = None
        attempts = step.max_retries + 1  # first try + retries

        for attempt in range(attempts):
            if attempt > 0:
                step.retry_count = attempt
                logger.info(
                    "Retrying step '%s' (attempt %d/%d)",
                    step.name,
                    attempt + 1,
                    attempts,
                )

            result = await self.orchestrator.handle(message, context)

            last_result = result

            if result.success:
                break

        assert last_result is not None

        # Update step with final result
        if last_result.success:
            new_status = StepStatus.COMPLETED
            step.progress_pct = 100
        else:
            new_status = StepStatus.FAILED
            # Record the error on the step
            spec = self.spec_engine.get(spec_id)
            if spec:
                s = spec.get_step(step.id)
                if s:
                    s.error = last_result.error

        await self.spec_engine.update_step(
            spec_id,
            step.id,
            status=new_status,
            output=last_result.output,
        )

        return last_result
