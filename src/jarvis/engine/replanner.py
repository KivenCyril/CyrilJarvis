from __future__ import annotations

import json
import logging
from typing import Any

from jarvis.models.streaming_spec import (
    ChangeSource,
    Constraint,
    SpecStatus,
    Step,
    StepStatus,
    StreamingSpec,
)

logger = logging.getLogger(__name__)

REPLAN_SYSTEM_PROMPT = """\
You are a task replanner. Given a partially-executed task plan and a change \
(new constraint, edited step, or redirected intent), determine which pending \
steps need adjustment.

Return a JSON object with:
- "adjusted_steps": array of {id, name, description} for steps that should be modified
- "new_steps": array of {name, description} for any new steps to add (insert after the last adjusted step)
- "remove_step_ids": array of step IDs to remove

Only modify PENDING steps. Never touch COMPLETED steps.
Respond ONLY with the JSON object, no markdown fences.
"""


class Replanner:
    """Handles re-planning when a user edits a Streaming Spec mid-execution.

    When an LLM registry is available, uses AI to intelligently replan.
    Otherwise falls back to deterministic heuristics.
    """

    def __init__(self, llm_registry: Any | None = None) -> None:
        self._llm = llm_registry

    async def _replan_with_llm(
        self, spec: StreamingSpec, change_description: str
    ) -> dict[str, Any]:
        from jarvis.llm.provider import Message, Role

        llm = self._llm.get()
        spec_summary = {
            "intent": spec.intent,
            "constraints": [c.content for c in spec.constraints if c.active],
            "steps": [
                {"id": s.id, "name": s.name, "status": s.status.value, "description": s.description}
                for s in spec.steps
            ],
        }
        prompt = (
            f"Current plan:\n{json.dumps(spec_summary, ensure_ascii=False, indent=2)}\n\n"
            f"Change: {change_description}\n\n"
            f"Determine what adjustments are needed to the pending steps."
        )
        response = await llm.chat(
            messages=[
                Message(role=Role.SYSTEM, content=REPLAN_SYSTEM_PROMPT),
                Message(role=Role.USER, content=prompt),
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)

    async def on_constraint_change(self, spec: StreamingSpec, constraint: Constraint) -> list[Step]:
        affected = spec.pending_steps()

        if self._llm and affected:
            try:
                result = await self._replan_with_llm(
                    spec, f"New constraint added: '{constraint.content}'"
                )
                self._apply_replan(spec, result)
                logger.info("LLM replanned %d steps for constraint '%s'", len(affected), constraint.content)
            except Exception as e:
                logger.warning("LLM replan failed: %s", e)

        if affected:
            logger.info(
                "Constraint '%s' affects %d pending steps: %s",
                constraint.content,
                len(affected),
                [s.name for s in affected],
            )
        return affected

    async def on_step_edit(self, spec: StreamingSpec, edited_step: Step) -> list[Step]:
        affected: list[Step] = []
        found = False
        for step in spec.steps:
            if step.id == edited_step.id:
                found = True
                continue
            if found and step.status in (StepStatus.PENDING, StepStatus.PLANNING):
                affected.append(step)

        if self._llm and affected:
            try:
                result = await self._replan_with_llm(
                    spec, f"Step '{edited_step.name}' was manually edited"
                )
                self._apply_replan(spec, result)
            except Exception as e:
                logger.warning("LLM replan failed: %s", e)

        if affected:
            logger.info("Edit to step '%s' affects %d downstream steps", edited_step.name, len(affected))
        return affected

    async def on_redirect(self, spec: StreamingSpec, new_intent: str) -> StreamingSpec:
        logger.info("Redirecting spec '%s' to new intent: %s", spec.name, new_intent)

        new_spec = StreamingSpec(
            id=spec.id,
            name=new_intent[:50],
            intent=new_intent,
            status=SpecStatus.PLANNING,
            changelog=spec.changelog.copy(),
        )

        if self._llm:
            try:
                from jarvis.llm.provider import Message, Role
                llm = self._llm.get()

                decompose_prompt = (
                    f"Original intent: {spec.intent}\n"
                    f"New intent (redirect): {new_intent}\n\n"
                    f"Completed work:\n"
                )
                for s in spec.steps:
                    if s.status == StepStatus.COMPLETED:
                        decompose_prompt += f"  - {s.name}: {s.output or 'done'}\n"

                decompose_prompt += "\nDecompose the NEW intent into steps, considering what was already done."

                from jarvis.engine.spec_engine import DECOMPOSE_SYSTEM_PROMPT
                response = await llm.chat(
                    messages=[
                        Message(role=Role.SYSTEM, content=DECOMPOSE_SYSTEM_PROMPT),
                        Message(role=Role.USER, content=decompose_prompt),
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                )
                text = response.content.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0]
                steps = json.loads(text)
                for step_data in steps:
                    new_spec.add_step(
                        step_data["name"],
                        step_data.get("description", ""),
                        source=ChangeSource.AGENT,
                    )
                new_spec.status = SpecStatus.EXECUTING
                return new_spec
            except Exception as e:
                logger.warning("LLM redirect replan failed: %s", e)

        new_spec.add_step("分析新需求", f"理解新意图: {new_intent}", source=ChangeSource.AGENT)
        new_spec.add_step("制定新方案", "基于新意图确定实施路径", source=ChangeSource.AGENT)
        new_spec.add_step("执行", "按新方案执行", source=ChangeSource.AGENT)
        new_spec.status = SpecStatus.EXECUTING
        return new_spec

    @staticmethod
    def _apply_replan(spec: StreamingSpec, result: dict[str, Any]) -> None:
        for adj in result.get("adjusted_steps", []):
            for step in spec.steps:
                if step.id == adj["id"] and step.status in (StepStatus.PENDING, StepStatus.PLANNING):
                    step.name = adj.get("name", step.name)
                    step.description = adj.get("description", step.description)

        for remove_id in result.get("remove_step_ids", []):
            spec.steps = [s for s in spec.steps if s.id != remove_id]

        for new_step in result.get("new_steps", []):
            spec.add_step(new_step["name"], new_step.get("description", ""), source=ChangeSource.AGENT)
