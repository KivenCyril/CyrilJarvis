"""Skill Evaluation Framework — measure, compare, and regression-test skills.

The evaluation loop complements the evolution loop in
:mod:`jarvis.skills.evolve`:

1. :meth:`SkillEvaluator.generate_evals` creates a test suite from the
   skill definition (LLM-assisted or heuristic).
2. :meth:`SkillEvaluator.run_suite` executes all cases and records results.
3. :meth:`SkillEvaluator.compare_versions` A/B-tests two skill versions.
4. :meth:`SkillEvaluator.regression_test` gates evolution: an improved
   skill must pass every case the original already passed.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from jarvis.skills.base import Skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_GENERATE_EVALS_PROMPT = """\
You are a Skill Test Engineer.  Given the following skill definition,
generate test cases that verify the skill works correctly.

Skill: {name}
Description: {description}
System prompt: {system_prompt}

Steps:
{steps}

Constraints:
{constraints}

Generate 3-5 test cases as a JSON array.  Each element:
{{
    "name": "short test name",
    "prompt": "user input that should trigger this skill",
    "expected": ["keyword1", "keyword2"],
    "must_not": ["bad_keyword"],
    "eval_type": "trigger|structure|validation",
    "timeout_ms": 30000
}}

Return ONLY valid JSON (an array), no markdown fences.
"""

_VALIDATION_PROMPT = """\
You are simulating a skill execution.  Given the skill definition and a
user prompt, produce the output the skill would generate.

Skill: {name}
System prompt: {system_prompt}

Steps:
{steps}

Constraints:
{constraints}

User prompt: {prompt}

Produce a realistic output as if you were the agent executing this skill.
"""

_TRIGGER_PROMPT = """\
You are evaluating whether a skill should be triggered for a given input.

Skill: {name}
Description: {description}
Tags: {tags}

User input: {prompt}

Should this skill be triggered?  Answer with a JSON object:
{{"match": true/false, "confidence": 0.0-1.0, "reason": "..."}}

Return ONLY valid JSON.
"""


# ---------------------------------------------------------------------------
# Enums & data models
# ---------------------------------------------------------------------------

class EvalType(str, Enum):
    """What aspect of the skill a test case evaluates."""

    TRIGGER = "trigger"
    STRUCTURE = "structure"
    VALIDATION = "validation"


class EvalCase(BaseModel):
    """A single evaluation case for a skill."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    prompt: str
    expected: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    eval_type: EvalType = EvalType.VALIDATION
    timeout_ms: int = 30000


class EvalResult(BaseModel):
    """Outcome of running a single :class:`EvalCase`."""

    eval_id: str
    eval_name: str
    skill_name: str
    passed: bool
    score: float = 0.0
    actual_output: str = ""
    failure_reason: str = ""
    duration_ms: int = 0
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComparisonResult(BaseModel):
    """A/B comparison between two skill versions."""

    skill_a: str
    skill_b: str
    winner: str  # "a", "b", or "tie"
    score_a: float
    score_b: float
    details: list[dict[str, Any]] = Field(default_factory=list)


class EvalSuite(BaseModel):
    """A collection of evaluation cases and their results."""

    skill_name: str
    cases: list[EvalCase] = Field(default_factory=list)
    results: list[EvalResult] = Field(default_factory=list)
    pass_rate: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict | list:
    """Extract JSON from LLM output, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON array or object in the text
        for pattern in (r"\[.*\]", r"\{.*\}"):
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue
    return {}


def _format_steps(skill: Skill) -> str:
    if not skill.steps:
        return "  (none)"
    return "\n".join(f"  {s.order}. {s.action}" for s in skill.steps)


def _format_constraints(skill: Skill) -> str:
    if not skill.constraints:
        return "  (none)"
    return "\n".join(f"  - {c}" for c in skill.constraints)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class SkillEvaluator:
    """Evaluates skills through trigger-matching, structural checks, and
    simulated execution.

    Parameters:
        llm_registry: Optional LLM registry for AI-driven evaluation and
            test-case generation.  When ``None`` the evaluator falls back
            to heuristic / rule-based approaches.
    """

    def __init__(self, llm_registry: Any = None) -> None:
        self._llm = llm_registry
        self._suites: dict[str, EvalSuite] = {}

    # ------------------------------------------------------------------
    # Single-case evaluation
    # ------------------------------------------------------------------

    async def run_eval(self, skill: Skill, case: EvalCase) -> EvalResult:
        """Execute a single evaluation case against *skill*."""
        start = time.monotonic()

        if case.eval_type == EvalType.TRIGGER:
            result = await self._eval_trigger(skill, case)
        elif case.eval_type == EvalType.STRUCTURE:
            result = self._eval_structure(skill, case)
        else:
            result = await self._eval_validation(skill, case)

        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    # -- TRIGGER ---------------------------------------------------------

    async def _eval_trigger(self, skill: Skill, case: EvalCase) -> EvalResult:
        """Check whether *skill* correctly matches (or rejects) the prompt."""
        if self._llm is not None:
            return await self._eval_trigger_llm(skill, case)
        return self._eval_trigger_heuristic(skill, case)

    async def _eval_trigger_llm(self, skill: Skill, case: EvalCase) -> EvalResult:
        try:
            provider = self._llm.get()
            prompt = _TRIGGER_PROMPT.format(
                name=skill.metadata.name,
                description=skill.metadata.description,
                tags=", ".join(skill.metadata.tags),
                prompt=case.prompt,
            )
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=512,
            )
            data = _parse_json(response.content)
            if not isinstance(data, dict):
                data = {}

            matched = data.get("match", False)
            confidence = float(data.get("confidence", 0.0))
            reason = data.get("reason", "")

            passed = self._check_expectations(
                f"match={matched} confidence={confidence}", case
            )
            return EvalResult(
                eval_id=case.id,
                eval_name=case.name,
                skill_name=skill.metadata.name,
                passed=passed,
                score=confidence if passed else 1.0 - confidence,
                actual_output=f"match={matched} confidence={confidence} reason={reason}",
            )
        except Exception:
            logger.exception("LLM trigger eval failed, falling back to heuristic")
            return self._eval_trigger_heuristic(skill, case)

    def _eval_trigger_heuristic(self, skill: Skill, case: EvalCase) -> EvalResult:
        """Keyword-overlap trigger check."""
        haystack = " ".join([
            skill.metadata.name,
            skill.metadata.description,
            " ".join(skill.metadata.tags),
            skill.metadata.domain,
        ]).lower()
        tokens = case.prompt.lower().split()
        hits = sum(1 for t in tokens if len(t) > 3 and t in haystack)
        score = min(1.0, hits / max(len(tokens), 1))

        output = f"keyword_hits={hits} total_tokens={len(tokens)} score={score:.2f}"
        passed = self._check_expectations(output, case)

        return EvalResult(
            eval_id=case.id,
            eval_name=case.name,
            skill_name=skill.metadata.name,
            passed=passed,
            score=score,
            actual_output=output,
            failure_reason="" if passed else "Keyword match score below threshold",
        )

    # -- STRUCTURE -------------------------------------------------------

    def _eval_structure(self, skill: Skill, case: EvalCase) -> EvalResult:
        """Structural checks: step count, constraint completeness, etc."""
        issues: list[str] = []
        score = 1.0

        if not skill.steps:
            issues.append("no steps defined")
            score -= 0.4

        if not skill.constraints:
            issues.append("no constraints defined")
            score -= 0.2

        if not skill.system_prompt:
            issues.append("empty system prompt")
            score -= 0.1

        if len(skill.steps) > 20:
            issues.append(f"too many steps ({len(skill.steps)})")
            score -= 0.1

        if skill.system_prompt and len(skill.system_prompt) > 5000:
            issues.append(f"system prompt too long ({len(skill.system_prompt)} chars)")
            score -= 0.1

        for step in skill.steps:
            if not step.action.strip():
                issues.append(f"step {step.order} has empty action")
                score -= 0.1

        score = max(0.0, score)
        output = "; ".join(issues) if issues else "all structural checks passed"
        passed = self._check_expectations(output, case) and score >= 0.5

        return EvalResult(
            eval_id=case.id,
            eval_name=case.name,
            skill_name=skill.metadata.name,
            passed=passed,
            score=score,
            actual_output=output,
            failure_reason="; ".join(issues) if not passed else "",
        )

    # -- VALIDATION ------------------------------------------------------

    async def _eval_validation(self, skill: Skill, case: EvalCase) -> EvalResult:
        """Simulate execution and check the output."""
        if self._llm is not None:
            return await self._eval_validation_llm(skill, case)
        return self._eval_validation_heuristic(skill, case)

    async def _eval_validation_llm(self, skill: Skill, case: EvalCase) -> EvalResult:
        try:
            provider = self._llm.get()
            prompt = _VALIDATION_PROMPT.format(
                name=skill.metadata.name,
                system_prompt=skill.system_prompt[:1000],
                steps=_format_steps(skill),
                constraints=_format_constraints(skill),
                prompt=case.prompt,
            )
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048,
            )
            output = response.content.strip()
            passed = self._check_expectations(output, case)
            failure = ""
            if not passed:
                failure = self._describe_failure(output, case)

            return EvalResult(
                eval_id=case.id,
                eval_name=case.name,
                skill_name=skill.metadata.name,
                passed=passed,
                score=1.0 if passed else 0.0,
                actual_output=output[:3000],
                failure_reason=failure,
            )
        except Exception:
            logger.exception("LLM validation eval failed, falling back to heuristic")
            return self._eval_validation_heuristic(skill, case)

    def _eval_validation_heuristic(self, skill: Skill, case: EvalCase) -> EvalResult:
        """Without LLM, check whether the skill's steps plausibly cover the prompt."""
        step_text = " ".join(s.action for s in skill.steps).lower()
        constraint_text = " ".join(skill.constraints).lower()
        combined = f"{step_text} {constraint_text} {skill.system_prompt.lower()}"

        passed = self._check_expectations(combined, case)
        score = 0.5 if passed else 0.0

        return EvalResult(
            eval_id=case.id,
            eval_name=case.name,
            skill_name=skill.metadata.name,
            passed=passed,
            score=score,
            actual_output="[heuristic] " + combined[:500],
            failure_reason="" if passed else self._describe_failure(combined, case),
        )

    # ------------------------------------------------------------------
    # Suite execution
    # ------------------------------------------------------------------

    async def run_suite(self, skill: Skill, suite: EvalSuite) -> EvalSuite:
        """Run all cases in *suite* against *skill*, updating results and pass_rate."""
        suite.results.clear()
        for case in suite.cases:
            result = await self.run_eval(skill, case)
            suite.results.append(result)
            logger.debug(
                "Eval '%s' %s (score=%.2f, %dms)",
                case.name,
                "PASSED" if result.passed else "FAILED",
                result.score,
                result.duration_ms,
            )

        passed_count = sum(1 for r in suite.results if r.passed)
        suite.pass_rate = passed_count / len(suite.results) if suite.results else 0.0

        logger.info(
            "Suite for '%s': %d/%d passed (%.0f%%)",
            skill.metadata.name,
            passed_count,
            len(suite.results),
            suite.pass_rate * 100,
        )
        return suite

    # ------------------------------------------------------------------
    # Test-case generation
    # ------------------------------------------------------------------

    async def generate_evals(self, skill: Skill) -> list[EvalCase]:
        """Auto-generate evaluation cases from the skill definition."""
        if self._llm is not None:
            cases = await self._generate_evals_llm(skill)
            if cases:
                return cases

        return self._generate_evals_heuristic(skill)

    async def _generate_evals_llm(self, skill: Skill) -> list[EvalCase]:
        try:
            provider = self._llm.get()
            prompt = _GENERATE_EVALS_PROMPT.format(
                name=skill.metadata.name,
                description=skill.metadata.description,
                system_prompt=skill.system_prompt[:500],
                steps=_format_steps(skill),
                constraints=_format_constraints(skill),
            )
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            data = _parse_json(response.content)
            if not isinstance(data, list):
                return []

            cases: list[EvalCase] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                cases.append(EvalCase(
                    name=item.get("name", "unnamed"),
                    prompt=item.get("prompt", ""),
                    expected=item.get("expected", []),
                    must_not=item.get("must_not", []),
                    eval_type=EvalType(item.get("eval_type", "validation")),
                    timeout_ms=item.get("timeout_ms", 30000),
                ))
            return cases
        except Exception:
            logger.exception("LLM eval generation failed, falling back to heuristic")
            return []

    def _generate_evals_heuristic(self, skill: Skill) -> list[EvalCase]:
        """Generate one case per step + one per constraint as boundary tests."""
        cases: list[EvalCase] = []

        for step in skill.steps:
            cases.append(EvalCase(
                name=f"step-{step.order}-basic",
                prompt=f"Execute step: {step.action}",
                expected=[w for w in step.action.lower().split() if len(w) > 4][:3],
                eval_type=EvalType.VALIDATION,
            ))

        for i, constraint in enumerate(skill.constraints):
            cases.append(EvalCase(
                name=f"constraint-{i}-boundary",
                prompt=f"Test with constraint violated: {constraint}",
                expected=[],
                must_not=[],
                eval_type=EvalType.STRUCTURE,
            ))

        if skill.metadata.description:
            cases.append(EvalCase(
                name="trigger-positive",
                prompt=skill.metadata.description,
                expected=[skill.metadata.name],
                eval_type=EvalType.TRIGGER,
            ))

        return cases

    # ------------------------------------------------------------------
    # Version comparison
    # ------------------------------------------------------------------

    async def compare_versions(
        self, skill_a: Skill, skill_b: Skill, suite: EvalSuite
    ) -> ComparisonResult:
        """A/B-test two skill versions on the same suite."""
        suite_a = EvalSuite(
            skill_name=skill_a.metadata.name,
            cases=list(suite.cases),
        )
        suite_b = EvalSuite(
            skill_name=skill_b.metadata.name,
            cases=list(suite.cases),
        )

        suite_a = await self.run_suite(skill_a, suite_a)
        suite_b = await self.run_suite(skill_b, suite_b)

        details: list[dict[str, Any]] = []
        for ra, rb in zip(suite_a.results, suite_b.results):
            details.append({
                "case": ra.eval_name,
                "a_passed": ra.passed,
                "b_passed": rb.passed,
                "a_score": ra.score,
                "b_score": rb.score,
            })

        score_a = suite_a.pass_rate
        score_b = suite_b.pass_rate

        if abs(score_a - score_b) < 0.01:
            winner = "tie"
        elif score_a > score_b:
            winner = "a"
        else:
            winner = "b"

        label_a = f"{skill_a.metadata.name}@v{skill_a.metadata.version}"
        label_b = f"{skill_b.metadata.name}@v{skill_b.metadata.version}"

        logger.info(
            "Comparison %s vs %s: winner=%s (%.0f%% vs %.0f%%)",
            label_a, label_b, winner, score_a * 100, score_b * 100,
        )

        return ComparisonResult(
            skill_a=label_a,
            skill_b=label_b,
            winner=winner,
            score_a=score_a,
            score_b=score_b,
            details=details,
        )

    # ------------------------------------------------------------------
    # Regression testing
    # ------------------------------------------------------------------

    async def regression_test(
        self, original: Skill, improved: Skill, suite: EvalSuite
    ) -> bool:
        """Verify that *improved* passes every case *original* already passed.

        Returns ``True`` if no regressions are detected.
        """
        suite_orig = EvalSuite(
            skill_name=original.metadata.name,
            cases=list(suite.cases),
        )
        suite_orig = await self.run_suite(original, suite_orig)

        passed_case_ids = {r.eval_id for r in suite_orig.results if r.passed}
        if not passed_case_ids:
            logger.info("Original skill passed no cases; regression test trivially passes")
            return True

        baseline_cases = [c for c in suite.cases if c.id in passed_case_ids]
        suite_improved = EvalSuite(
            skill_name=improved.metadata.name,
            cases=baseline_cases,
        )
        suite_improved = await self.run_suite(improved, suite_improved)

        regressions = [r for r in suite_improved.results if not r.passed]
        if regressions:
            names = ", ".join(r.eval_name for r in regressions)
            logger.warning(
                "Regression detected in '%s': %d case(s) regressed [%s]",
                improved.metadata.name,
                len(regressions),
                names,
            )
            return False

        logger.info(
            "Regression test passed for '%s': all %d baseline cases still pass",
            improved.metadata.name,
            len(baseline_cases),
        )
        return True

    # ------------------------------------------------------------------
    # Suite management
    # ------------------------------------------------------------------

    def get_suite(self, skill_name: str) -> EvalSuite | None:
        """Retrieve the stored evaluation suite for a skill."""
        return self._suites.get(skill_name)

    def add_eval(self, skill_name: str, case: EvalCase) -> None:
        """Append an evaluation case to the skill's suite (creates if needed)."""
        if skill_name not in self._suites:
            self._suites[skill_name] = EvalSuite(skill_name=skill_name)
        self._suites[skill_name].cases.append(case)
        logger.debug("Added eval '%s' to suite for '%s'", case.name, skill_name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_expectations(output: str, case: EvalCase) -> bool:
        """Return ``True`` if *output* contains all expected keywords and
        none of the must_not keywords."""
        output_lower = output.lower()

        for keyword in case.expected:
            if keyword.lower() not in output_lower:
                return False

        for keyword in case.must_not:
            if keyword.lower() in output_lower:
                return False

        return True

    @staticmethod
    def _describe_failure(output: str, case: EvalCase) -> str:
        """Build a human-readable explanation of why a case failed."""
        output_lower = output.lower()
        reasons: list[str] = []

        missing = [k for k in case.expected if k.lower() not in output_lower]
        if missing:
            reasons.append(f"missing expected: {missing}")

        forbidden = [k for k in case.must_not if k.lower() in output_lower]
        if forbidden:
            reasons.append(f"contains forbidden: {forbidden}")

        return "; ".join(reasons) if reasons else "unknown failure"
