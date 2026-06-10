"""Skill Evolution Engine — skills that improve over time.

This module implements the core innovation from Hermes: procedural memory
that evolves through use.  The evolution loop is:

1. A Streaming Spec completes successfully.
2. :meth:`SkillEvolver.distill_from_spec` extracts a reusable Skill.
3. Each time the Skill executes, the result is recorded.
4. :meth:`SkillEvolver.should_evolve` checks whether enough data has
   accumulated to warrant improvement.
5. :meth:`SkillEvolver.improve_skill` creates a new version with
   refined steps, constraints, or system prompt.
6. The Curator (human or automated) reviews and promotes or rolls back.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.skills.base import (
    Skill,
    SkillMetadata,
    SkillStatus,
    SkillStep,
)
from jarvis.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# Thresholds for triggering evolution
_MIN_EXECUTIONS = 3
_LOW_SUCCESS_RATE = 0.8
_LOW_AVG_SCORE = 0.7


class SkillEvolver:
    """Evolves skills based on execution history and feedback.

    Parameters:
        registry: The :class:`SkillRegistry` that owns the skills.
        llm_registry: Optional LLM registry for AI-driven distillation
            and improvement.  When ``None`` the evolver falls back to
            heuristic / rule-based approaches.
    """

    def __init__(self, registry: SkillRegistry, llm_registry: Any = None) -> None:
        self._registry = registry
        self._llm = llm_registry

    # ------------------------------------------------------------------
    # Distillation: Spec -> Skill
    # ------------------------------------------------------------------

    async def distill_from_spec(self, spec: Any) -> Skill:
        """Create a new Skill from a completed Streaming Spec.

        This is the key *Streaming Spec -> Skill* bridge:

        * Extract the reusable pattern from the spec's steps.
        * Identify constraints that should become permanent rules.
        * Generate a system prompt for future use.
        * Link back to the source spec via ``parent_spec_id``.

        Args:
            spec: A :class:`~jarvis.models.streaming_spec.StreamingSpec`
                instance (or any object with compatible attributes).

        Returns:
            A new :class:`Skill` in ``DRAFT`` status, registered but not
            yet promoted to ``ACTIVE``.
        """
        if self._llm is not None:
            skill = await self._distill_with_llm(spec)
        else:
            skill = self._distill_heuristic(spec)

        self._registry.register(skill)
        logger.info(
            "Distilled skill '%s' from spec '%s'",
            skill.metadata.name,
            getattr(spec, "id", "?"),
        )
        return skill

    def _distill_heuristic(self, spec: Any) -> Skill:
        """Rule-based distillation — copies steps and constraints directly."""
        steps = [
            SkillStep(
                order=i,
                action=getattr(step, "name", str(step)),
                tool=None,
                tool_args_template={},
                expected_output=getattr(step, "output", "") or "",
            )
            for i, step in enumerate(getattr(spec, "steps", []))
        ]

        constraints = [
            c.content if hasattr(c, "content") else str(c)
            for c in getattr(spec, "constraints", [])
            if getattr(c, "active", True)
        ]

        spec_name = getattr(spec, "name", "unnamed")
        # Sanitise the name for filesystem use
        safe_name = (
            spec_name.lower()
            .replace(" ", "-")
            .replace("/", "-")
            .replace("\\", "-")
        )

        return Skill(
            metadata=SkillMetadata(
                name=safe_name,
                description=getattr(spec, "intent", ""),
                created_by="agent",
                tags=["auto-distilled"],
            ),
            steps=steps,
            constraints=constraints,
            parent_spec_id=getattr(spec, "id", None),
            status=SkillStatus.DRAFT,
        )

    async def _distill_with_llm(self, spec: Any) -> Skill:
        """LLM-driven distillation — generalises the spec into a skill."""
        spec_steps = "\n".join(
            f"  {i + 1}. {getattr(s, 'name', s)} — output: {getattr(s, 'output', 'N/A')}"
            for i, s in enumerate(getattr(spec, "steps", []))
        )
        spec_constraints = "\n".join(
            f"  - {c.content if hasattr(c, 'content') else c}"
            for c in getattr(spec, "constraints", [])
            if getattr(c, "active", True)
        )

        prompt = (
            "You are a Skill Distiller.  Given the following completed task spec, "
            "extract a reusable, generalised procedure (Skill) that could handle "
            "similar tasks in the future.\n\n"
            f"Task: {getattr(spec, 'name', 'unnamed')}\n"
            f"Intent: {getattr(spec, 'intent', '')}\n\n"
            f"Steps taken:\n{spec_steps}\n\n"
            f"Constraints:\n{spec_constraints}\n\n"
            "Produce:\n"
            "1. A short, slug-style skill name\n"
            "2. A one-line description\n"
            "3. A system prompt (2-3 sentences) for the agent executing this skill\n"
            "4. Generalised steps (action descriptions only, no spec-specific data)\n"
            "5. Permanent constraints\n\n"
            "Format your answer as:\n"
            "NAME: <name>\n"
            "DESCRIPTION: <description>\n"
            "SYSTEM_PROMPT: <prompt>\n"
            "STEPS:\n- <step1>\n- <step2>\n...\n"
            "CONSTRAINTS:\n- <c1>\n- <c2>\n...\n"
        )

        try:
            provider = self._llm.get()
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_distillation(response.content, spec)
        except Exception:
            logger.exception("LLM distillation failed, falling back to heuristic")
            return self._distill_heuristic(spec)

    def _parse_distillation(self, text: str, spec: Any) -> Skill:
        """Parse the LLM's structured distillation response."""
        lines = text.strip().splitlines()

        name = "distilled-skill"
        description = ""
        system_prompt = ""
        steps: list[str] = []
        constraints: list[str] = []

        section: str | None = None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("NAME:"):
                name = stripped[5:].strip().lower().replace(" ", "-")
                section = None
            elif stripped.startswith("DESCRIPTION:"):
                description = stripped[12:].strip()
                section = None
            elif stripped.startswith("SYSTEM_PROMPT:"):
                system_prompt = stripped[14:].strip()
                section = None
            elif stripped == "STEPS:":
                section = "steps"
            elif stripped == "CONSTRAINTS:":
                section = "constraints"
            elif stripped.startswith("- "):
                item = stripped[2:].strip()
                if section == "steps":
                    steps.append(item)
                elif section == "constraints":
                    constraints.append(item)

        return Skill(
            metadata=SkillMetadata(
                name=name,
                description=description,
                created_by="agent",
                tags=["auto-distilled"],
            ),
            system_prompt=system_prompt,
            steps=[
                SkillStep(order=i, action=action) for i, action in enumerate(steps)
            ],
            constraints=constraints,
            parent_spec_id=getattr(spec, "id", None),
            status=SkillStatus.DRAFT,
        )

    # ------------------------------------------------------------------
    # Evolution: Skill v1 -> Skill v1.1
    # ------------------------------------------------------------------

    async def should_evolve(self, skill: Skill) -> bool:
        """Determine whether a skill has enough signal to warrant evolution.

        Evolution is triggered when the skill has at least
        ``_MIN_EXECUTIONS`` recorded executions **and** at least one of:

        * ``success_rate < 0.8``
        * ``avg_score < 0.7``
        * A downward trend in the last three scores.
        """
        if skill.use_count < _MIN_EXECUTIONS:
            return False

        if skill.success_rate < _LOW_SUCCESS_RATE:
            return True
        if skill.avg_score > 0 and skill.avg_score < _LOW_AVG_SCORE:
            return True

        # Check for a downward trend in recent scores
        recent_scored = [e for e in skill.executions if e.score > 0][-3:]
        if len(recent_scored) >= 3:
            scores = [e.score for e in recent_scored]
            if scores[0] > scores[1] > scores[2]:
                return True

        return False

    async def improve_skill(self, skill: Skill) -> Skill | None:
        """Analyse execution history and create an improved version.

        Examines:
        * Failed executions — what went wrong?
        * Low-score executions — what could be better?
        * Successful executions — what patterns are consistent?

        Args:
            skill: The skill to improve.

        Returns:
            A **new** :class:`Skill` with a bumped version, or ``None``
            if no improvements are identified.
        """
        if not await self.should_evolve(skill):
            return None

        if self._llm is not None:
            improved = await self._improve_with_llm(skill)
        else:
            improved = self._improve_heuristic(skill)

        if improved is not None:
            self._registry.register(improved)
            logger.info(
                "Evolved skill '%s' from v%s to v%s",
                skill.metadata.name,
                skill.metadata.version,
                improved.metadata.version,
            )

        return improved

    def _improve_heuristic(self, skill: Skill) -> Skill | None:
        """Rule-based improvement: add error-handling notes from failures."""
        failed = [e for e in skill.executions if not e.success]
        if not failed:
            return None

        # Collect failure patterns from feedback
        failure_reasons = [
            e.feedback for e in failed if e.feedback
        ]
        if not failure_reasons:
            failure_reasons = [e.output[:200] for e in failed if e.output]
        if not failure_reasons:
            return None

        new_version = self._bump_version(skill.metadata.version)
        note = f"Added error handling for {len(failed)} failure(s)"

        new_constraints = list(skill.constraints)
        for reason in failure_reasons[:3]:  # top 3 failure reasons
            constraint = f"Handle error scenario: {reason[:100]}"
            if constraint not in new_constraints:
                new_constraints.append(constraint)

        improved = Skill(
            metadata=SkillMetadata(
                name=skill.metadata.name,
                version=new_version,
                description=skill.metadata.description,
                author=skill.metadata.author,
                created_by="agent",
                tags=skill.metadata.tags,
                domain=skill.metadata.domain,
            ),
            status=SkillStatus.DRAFT,
            system_prompt=skill.system_prompt,
            steps=list(skill.steps),
            constraints=new_constraints,
            parent_skill_id=skill.id,
            parent_spec_id=skill.parent_spec_id,
            improvement_notes=list(skill.improvement_notes) + [note],
        )
        return improved

    async def _improve_with_llm(self, skill: Skill) -> Skill | None:
        """LLM-driven improvement using execution history analysis."""
        failed_summary = "\n".join(
            f"  - input: {e.input_context[:100]}  error: {e.output[:100]}  feedback: {e.feedback}"
            for e in skill.executions
            if not e.success
        )
        success_summary = "\n".join(
            f"  - input: {e.input_context[:100]}  score: {e.score}  feedback: {e.feedback}"
            for e in skill.executions
            if e.success and e.score > 0
        )

        current_steps = "\n".join(
            f"  {s.order}. {s.action}" for s in skill.steps
        )
        current_constraints = "\n".join(
            f"  - {c}" for c in skill.constraints
        )

        prompt = (
            "You are a Skill Improvement Analyst.  Given the following skill "
            "definition and its execution history, suggest concrete improvements "
            "to the steps and constraints.\n\n"
            f"Skill: {skill.metadata.name} v{skill.metadata.version}\n"
            f"Description: {skill.metadata.description}\n\n"
            f"Current steps:\n{current_steps}\n\n"
            f"Current constraints:\n{current_constraints}\n\n"
            f"Failed executions:\n{failed_summary or '  (none)'}\n\n"
            f"Successful executions (with scores):\n{success_summary or '  (none)'}\n\n"
            f"Success rate: {skill.success_rate:.0%}, Avg score: {skill.avg_score:.2f}\n\n"
            "Provide:\n"
            "1. IMPROVEMENT_NOTES: bullet points of what to change and why\n"
            "2. NEW_STEPS: the revised step list\n"
            "3. NEW_CONSTRAINTS: the revised constraints\n\n"
            "If no meaningful improvements are possible, respond with 'NO_CHANGES'."
        )

        try:
            provider = self._llm.get()
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content.strip()

            if "NO_CHANGES" in text:
                return None

            return self._parse_improvement(text, skill)
        except Exception:
            logger.exception("LLM skill improvement failed, falling back to heuristic")
            return self._improve_heuristic(skill)

    def _parse_improvement(self, text: str, skill: Skill) -> Skill:
        """Parse the LLM's improvement response into a new Skill version."""
        notes: list[str] = []
        steps: list[str] = []
        constraints: list[str] = []
        section: str | None = None

        for line in text.strip().splitlines():
            stripped = line.strip()
            if "IMPROVEMENT_NOTES" in stripped:
                section = "notes"
            elif "NEW_STEPS" in stripped:
                section = "steps"
            elif "NEW_CONSTRAINTS" in stripped:
                section = "constraints"
            elif stripped.startswith("- ") or stripped.startswith("* "):
                item = stripped[2:].strip()
                if section == "notes":
                    notes.append(item)
                elif section == "steps":
                    steps.append(item)
                elif section == "constraints":
                    constraints.append(item)
            elif stripped and stripped[0].isdigit() and ". " in stripped:
                # Numbered list item: "1. Do something"
                item = stripped.split(". ", 1)[1].strip()
                if section == "steps":
                    steps.append(item)

        new_version = self._bump_version(skill.metadata.version)

        return Skill(
            metadata=SkillMetadata(
                name=skill.metadata.name,
                version=new_version,
                description=skill.metadata.description,
                author=skill.metadata.author,
                created_by="agent",
                tags=skill.metadata.tags,
                domain=skill.metadata.domain,
            ),
            status=SkillStatus.DRAFT,
            system_prompt=skill.system_prompt,
            steps=[
                SkillStep(order=i, action=action) for i, action in enumerate(steps)
            ]
            if steps
            else list(skill.steps),
            constraints=constraints if constraints else list(skill.constraints),
            parent_skill_id=skill.id,
            parent_spec_id=skill.parent_spec_id,
            improvement_notes=list(skill.improvement_notes) + notes,
        )

    # ------------------------------------------------------------------
    # Reflection plane
    # ------------------------------------------------------------------

    async def reflect_on_execution(
        self, skill: Skill, execution: SkillExecution
    ) -> dict:
        """Post-execution reflection: analyze outcome and propose improvements.

        When the same recommendation appears 3+ times in a skill's reflection
        log, it is promoted to a formal constraint.
        """
        from jarvis.skills.failure_analyzer import FailureAnalyzer

        result = {
            "execution_id": execution.id,
            "success": execution.success,
            "recommendations": [],
            "promoted_constraints": [],
        }

        if execution.success and execution.score >= 0.8:
            return result

        analyzer = FailureAnalyzer(self._llm)
        if not execution.success:
            analysis = await analyzer.analyze(execution, skill)
            result["failure_type"] = analysis.failure_type.value
            result["root_cause"] = analysis.root_cause
            if analysis.recommendation:
                result["recommendations"].append(analysis.recommendation)

        if execution.score > 0 and execution.score < 0.7:
            result["recommendations"].append(
                f"Quality below threshold ({execution.score:.2f}): review steps for clarity"
            )

        skill.reflection_log.append(result)

        all_recs = []
        for entry in skill.reflection_log:
            all_recs.extend(entry.get("recommendations", []))

        from collections import Counter
        rec_counts = Counter(all_recs)
        for rec, count in rec_counts.items():
            if count >= 3 and rec not in skill.constraints:
                skill.constraints.append(rec)
                result["promoted_constraints"].append(rec)
                logger.info(
                    "Promoted recommendation to constraint for '%s': %s",
                    skill.metadata.name, rec,
                )

        return result

    async def improve_with_eval(self, skill: Skill) -> Skill | None:
        """Eval-driven improvement: use failing eval cases to generate minimal patches."""
        from jarvis.skills.eval import SkillEvaluator

        evaluator = SkillEvaluator(self._llm)
        suite = evaluator.get_suite(skill.metadata.name)
        if not suite or not suite.cases:
            return None

        suite = await evaluator.run_suite(skill, suite)
        if suite.pass_rate >= 1.0:
            return None

        failed_cases = [
            (c, r) for c, r in zip(suite.cases, suite.results)
            if not r.passed
        ]
        if not failed_cases:
            return None

        failure_descriptions = []
        for case, result in failed_cases[:5]:
            failure_descriptions.append(
                f"- Eval '{case.name}': expected {case.expected}, "
                f"got failure: {result.failure_reason}"
            )

        new_constraints = list(skill.constraints)
        new_notes = list(skill.improvement_notes)

        for case, result in failed_cases[:3]:
            fix_note = f"Fix eval '{case.name}': {result.failure_reason}"
            new_notes.append(fix_note)
            if case.expected:
                new_constraints.append(
                    f"Ensure output addresses: {', '.join(case.expected[:3])}"
                )

        seen = set()
        deduped = []
        for c in new_constraints:
            if c not in seen:
                seen.add(c)
                deduped.append(c)

        improved = Skill(
            metadata=SkillMetadata(
                name=skill.metadata.name,
                version=self._bump_version(skill.metadata.version),
                description=skill.metadata.description,
                author="eval-driven-evolver",
                created_by="agent",
                tags=list(skill.metadata.tags) + ["eval-improved"],
                domain=skill.metadata.domain,
            ),
            status=SkillStatus.DRAFT,
            system_prompt=skill.system_prompt,
            steps=list(skill.steps),
            constraints=deduped,
            parent_skill_id=skill.id,
            parent_spec_id=skill.parent_spec_id,
            improvement_notes=new_notes,
        )

        self._registry.register(improved)
        logger.info(
            "Eval-driven evolution of '%s': %d failing evals addressed",
            skill.metadata.name, len(failed_cases),
        )
        return improved

    # ------------------------------------------------------------------
    # Batch evolution
    # ------------------------------------------------------------------

    async def evolve_all(self) -> list[Skill]:
        """Scan every active skill and evolve those that qualify.

        Returns:
            List of newly created (improved) skills.
        """
        evolved: list[Skill] = []
        for skill in self._registry.list_skills(status=SkillStatus.ACTIVE):
            try:
                improved = await self.improve_skill(skill)
                if improved is not None:
                    evolved.append(improved)
            except Exception:
                logger.exception("Evolution failed for skill '%s'", skill.metadata.name)
        return evolved

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bump_version(version: str) -> str:
        """Bump the minor segment of a semver string.

        Examples:
            ``"1.0.0"`` -> ``"1.1.0"``
            ``"2.3.1"`` -> ``"2.4.0"``
        """
        parts = version.split(".")
        if len(parts) != 3:
            return "1.1.0"
        try:
            major, minor, _ = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{major}.{minor + 1}.0"
        except ValueError:
            return "1.1.0"
