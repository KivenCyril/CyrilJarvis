from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable, Awaitable

from jarvis.engine.replanner import Replanner
from jarvis.models.streaming_spec import (
    ChangeSource,
    ChangeType,
    SpecEvent,
    SpecStatus,
    StepStatus,
    StreamingSpec,
)

logger = logging.getLogger(__name__)

DECOMPOSE_SYSTEM_PROMPT = """\
You are a task decomposition engine. Given a user's intent, break it down into \
concrete, actionable steps. Return a JSON array of objects with "name", \
"description" and "depends_on" fields.

Rules:
- "depends_on" is an array of NAMES of earlier steps that must finish before \
this step can start; use [] when the step can start immediately
- Steps that do not depend on each other should stay independent so they can \
run in parallel -- do not chain steps unnecessarily
- Each step should be independently executable
- Use clear, imperative language for step names
- Description should explain WHAT to do, not HOW
- 3-8 steps typically. Don't over-decompose simple tasks
- Respond ONLY with the JSON array, no markdown fences or extra text
"""

EventCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class SpecEngine:
    """Core engine for creating, streaming, and editing Streaming Specs.

    Supports both LLM-powered and mock modes. When an LLM registry is provided,
    uses real AI decomposition; otherwise falls back to deterministic steps.
    """

    def __init__(self, llm_registry: Any | None = None) -> None:
        self._specs: dict[str, StreamingSpec] = {}
        self._subscribers: dict[str, list[asyncio.Queue[SpecEvent]]] = {}
        self._replanner = Replanner()
        self._llm = llm_registry
        self._event_callbacks: list[EventCallback] = []

    def on_event(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    def _emit(self, spec_id: str, event_type: str, data: dict) -> None:
        event = SpecEvent(event_type=event_type, spec_id=spec_id, data=data)
        for queue in self._subscribers.get(spec_id, []):
            queue.put_nowait(event)
        for cb in self._event_callbacks:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(cb(spec_id, event_type, data))
            except RuntimeError:
                pass

    async def _decompose_with_llm(self, intent: str) -> list[dict[str, str]]:
        from jarvis.llm.provider import Message, Role
        llm = self._llm.get()
        response = await llm.chat(
            messages=[
                Message(role=Role.SYSTEM, content=DECOMPOSE_SYSTEM_PROMPT),
                Message(role=Role.USER, content=intent),
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)

    async def create(self, intent: str, name: str | None = None) -> StreamingSpec:
        spec = StreamingSpec(
            name=name or intent[:50],
            intent=intent,
            status=SpecStatus.PLANNING,
        )

        if self._llm:
            try:
                steps = await self._decompose_with_llm(intent)
                for step_data in steps:
                    spec.add_step(
                        step_data["name"],
                        step_data.get("description", ""),
                        source=ChangeSource.AGENT,
                    )
                self._wire_dependencies(spec, steps)
            except Exception as e:
                logger.warning("LLM decomposition failed, using fallback: %s", e)
                self._add_fallback_steps(spec, intent)
        else:
            self._add_fallback_steps(spec, intent)

        spec.status = SpecStatus.EXECUTING
        self._specs[spec.id] = spec
        self._emit(spec.id, "spec_created", spec.model_dump(mode="json"))
        logger.info("Created spec %s: %s (%d steps)", spec.id, spec.name, len(spec.steps))
        return spec

    @staticmethod
    def _add_fallback_steps(spec: StreamingSpec, intent: str) -> None:
        spec.add_step("分析需求", f"理解意图: {intent}", source=ChangeSource.AGENT)
        spec.add_step("制定方案", "确定实施路径", source=ChangeSource.AGENT)
        spec.add_step("执行", "按方案执行", source=ChangeSource.AGENT)
        spec.add_step("验证", "验证执行结果", source=ChangeSource.AGENT)
        # Fallback chain is sequential by design
        spec.add_dependency(spec.steps[1].id, spec.steps[0].id, source=ChangeSource.AGENT)
        spec.add_dependency(spec.steps[2].id, spec.steps[1].id, source=ChangeSource.AGENT)
        spec.add_dependency(spec.steps[3].id, spec.steps[2].id, source=ChangeSource.AGENT)
        spec.update_step_readiness()

    @staticmethod
    def _wire_dependencies(spec: StreamingSpec, steps_data: list[dict]) -> None:
        """Resolve LLM-provided dependency step names into DAG edges.

        Names are matched against previously defined steps (first occurrence
        wins); unknown names are skipped. ``add_dependency`` rejects edges
        that would create a cycle.
        """
        name_to_id: dict[str, str] = {}
        for step, data in zip(spec.steps, steps_data):
            for dep_name in data.get("depends_on") or []:
                dep_id = name_to_id.get(dep_name)
                if dep_id:
                    spec.add_dependency(step.id, dep_id, source=ChangeSource.AGENT)
            name_to_id.setdefault(step.name, step.id)
        spec.update_step_readiness()

    def get(self, spec_id: str) -> StreamingSpec | None:
        return self._specs.get(spec_id)

    def list_specs(self) -> list[StreamingSpec]:
        return list(self._specs.values())

    async def update_step(
        self,
        spec_id: str,
        step_id: str,
        status: StepStatus | None = None,
        output: str | None = None,
    ) -> StreamingSpec | None:
        spec = self._specs.get(spec_id)
        if not spec:
            return None

        if status:
            spec.update_step_status(step_id, status, source=ChangeSource.AGENT)
        if output:
            spec.set_step_output(step_id, output)

        self._emit(spec_id, "step_updated", {"step_id": step_id, "status": status, "output": output})

        # Emit terminal event if all steps reached a terminal state
        await self.finalize(spec_id)

        return spec

    async def add_constraint(
        self,
        spec_id: str,
        content: str,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> StreamingSpec | None:
        spec = self._specs.get(spec_id)
        if not spec:
            return None

        constraint = spec.add_constraint(content, source=source)
        affected = await self._replanner.on_constraint_change(spec, constraint)
        self._emit(spec_id, "constraint_added", {
            "constraint_id": constraint.id,
            "content": content,
            "affected_steps": [s.id for s in affected],
        })
        return spec

    async def remove_constraint(
        self,
        spec_id: str,
        constraint_id: str,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> StreamingSpec | None:
        spec = self._specs.get(spec_id)
        if not spec:
            return None

        removed = spec.remove_constraint(constraint_id, source=source)
        if removed:
            self._emit(spec_id, "constraint_removed", {"constraint_id": constraint_id})
        return spec

    async def edit_step(
        self,
        spec_id: str,
        step_id: str,
        name: str | None = None,
        description: str | None = None,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> StreamingSpec | None:
        spec = self._specs.get(spec_id)
        if not spec:
            return None

        for step in spec.steps:
            if step.id == step_id:
                if name:
                    old_name = step.name
                    step.name = name
                    spec._record_change(source, ChangeType.STEP_MODIFIED, f"steps.{step_id}.name", old_value=old_name, new_value=name)
                if description:
                    step.description = description

                affected = await self._replanner.on_step_edit(spec, step)
                self._emit(spec_id, "step_edited", {"step_id": step_id, "affected_steps": [s.id for s in affected]})
                return spec
        return None

    async def redirect(
        self,
        spec_id: str,
        new_intent: str,
    ) -> StreamingSpec | None:
        spec = self._specs.get(spec_id)
        if not spec:
            return None

        spec.change_intent(new_intent, source=ChangeSource.HUMAN)
        new_spec = await self._replanner.on_redirect(spec, new_intent)
        self._specs[spec_id] = new_spec
        self._emit(spec_id, "spec_redirected", new_spec.model_dump(mode="json"))
        return new_spec

    async def add_dependency(
        self,
        spec_id: str,
        step_id: str,
        depends_on_id: str,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> StreamingSpec | None:
        """Add a dependency edge and emit an event.

        Returns the updated spec, or ``None`` if the spec doesn't exist or
        the dependency would create a cycle.
        """
        spec = self._specs.get(spec_id)
        if not spec:
            return None

        ok = spec.add_dependency(step_id, depends_on_id, source=source)
        if not ok:
            logger.warning(
                "Cannot add dependency %s -> %s (cycle or missing step)",
                step_id,
                depends_on_id,
            )
            return None

        # Recompute readiness after the graph changed
        spec.update_step_readiness()

        self._emit(spec_id, "dependency_added", {
            "step_id": step_id,
            "depends_on_id": depends_on_id,
        })
        return spec

    async def remove_dependency(
        self,
        spec_id: str,
        step_id: str,
        depends_on_id: str,
        source: ChangeSource = ChangeSource.HUMAN,
    ) -> StreamingSpec | None:
        """Remove a dependency edge and emit an event."""
        spec = self._specs.get(spec_id)
        if not spec:
            return None

        removed = spec.remove_dependency(step_id, depends_on_id, source=source)
        if not removed:
            return None

        spec.update_step_readiness()

        self._emit(spec_id, "dependency_removed", {
            "step_id": step_id,
            "depends_on_id": depends_on_id,
        })
        return spec

    _TERMINAL_STEP_STATES = (
        StepStatus.COMPLETED,
        StepStatus.SKIPPED,
        StepStatus.FAILED,
        StepStatus.CANCELLED,
    )

    async def finalize(self, spec_id: str) -> StreamingSpec | None:
        """Recompute terminal status from step states and emit terminal events.

        - All steps terminal -> COMPLETED, or FAILED if any step failed
        - Remaining steps all BLOCKED (failed dependency chain) -> FAILED
        Emits ``spec_completed`` / ``spec_failed`` exactly once per transition.
        """
        spec = self._specs.get(spec_id)
        if not spec or spec.status in (
            SpecStatus.COMPLETED,
            SpecStatus.FAILED,
            SpecStatus.PAUSED,
            SpecStatus.REDIRECTED,
        ):
            return spec

        # Refresh BLOCKED/READY states before judging the terminal condition,
        # otherwise steps unblocked by a just-completed dependency still look
        # BLOCKED and the spec would be wrongly failed.
        spec.update_step_readiness()

        remaining = [s for s in spec.steps if s.status not in self._TERMINAL_STEP_STATES]
        any_failed = any(s.status == StepStatus.FAILED for s in spec.steps)

        if not remaining:
            self._transition(spec, SpecStatus.FAILED if any_failed else SpecStatus.COMPLETED)
        elif all(s.status == StepStatus.BLOCKED for s in remaining):
            self._transition(spec, SpecStatus.FAILED)
        return spec

    def _transition(self, spec: StreamingSpec, new_status: SpecStatus) -> None:
        """Set a terminal status, record it, and emit the matching event."""
        if spec.status == new_status:
            return
        old = spec.status
        spec.status = new_status
        spec._record_change(
            ChangeSource.AGENT,
            ChangeType.STATUS_CHANGED,
            "status",
            old_value=old.value,
            new_value=new_status.value,
        )
        if new_status == SpecStatus.COMPLETED:
            self._emit(spec.id, "spec_completed", {
                "status": new_status.value,
                "progress": spec.progress,
            })
        elif new_status == SpecStatus.FAILED:
            self._emit(spec.id, "spec_failed", {
                "status": new_status.value,
                "failed_steps": [
                    {"id": s.id, "name": s.name, "error": s.error}
                    for s in spec.steps
                    if s.status == StepStatus.FAILED
                ],
            })
        logger.info("Spec %s transitioned %s -> %s", spec.id, old.value, new_status.value)

    async def stream(self, spec_id: str) -> AsyncIterator[SpecEvent]:
        queue: asyncio.Queue[SpecEvent] = asyncio.Queue()
        self._subscribers.setdefault(spec_id, []).append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
                if event.event_type in ("spec_completed", "spec_failed", "spec_redirected"):
                    break
        finally:
            self._subscribers[spec_id].remove(queue)
