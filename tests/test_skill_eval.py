"""Tests for the Skill Eval framework, failure analyzer, and self-evolution pipeline."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from jarvis.skills.base import Skill, SkillMetadata, SkillStep, SkillExecution, SkillStatus
from jarvis.skills.eval import EvalCase, EvalType, EvalSuite, SkillEvaluator
from jarvis.skills.failure_analyzer import FailureAnalyzer, FailureType
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.evolve import SkillEvolver


def _make_skill(name="test-skill", steps=None, constraints=None) -> Skill:
    return Skill(
        metadata=SkillMetadata(name=name, description=f"A test skill: {name}"),
        status=SkillStatus.ACTIVE,
        system_prompt="You are a helpful assistant.",
        steps=steps or [
            SkillStep(order=1, action="Analyze the input", tool="read_file"),
            SkillStep(order=2, action="Generate output", tool="write_file"),
        ],
        constraints=constraints or ["Be concise", "Use JSON format"],
    )


def _make_execution(success=True, score=0.9, output="result", feedback="", duration_ms=100) -> SkillExecution:
    return SkillExecution(
        success=success,
        score=score,
        output=output,
        feedback=feedback,
        duration_ms=duration_ms,
        input_context="test input",
    )


# ── EvalCase / EvalSuite ───────────────────────────────────────────────


class TestEvalModels:
    def test_eval_case_creation(self):
        case = EvalCase(
            name="basic-test",
            prompt="Analyze this code",
            expected=["analysis", "review"],
            must_not=["error"],
        )
        assert case.id
        assert case.eval_type == EvalType.VALIDATION
        assert len(case.expected) == 2

    def test_eval_suite_creation(self):
        cases = [
            EvalCase(name="test-1", prompt="prompt 1", expected=["output"]),
            EvalCase(name="test-2", prompt="prompt 2", expected=["result"]),
        ]
        suite = EvalSuite(
            skill_name="test-skill",
            cases=cases,
            created_at=datetime.now(timezone.utc),
        )
        assert suite.pass_rate == 0.0
        assert len(suite.cases) == 2


# ── SkillEvaluator ─────────────────────────────────────────────────────


class TestSkillEvaluator:
    def test_add_and_get_suite(self):
        evaluator = SkillEvaluator()
        case = EvalCase(name="t1", prompt="test", expected=["ok"])
        evaluator.add_eval("my-skill", case)
        suite = evaluator.get_suite("my-skill")
        assert suite is not None
        assert len(suite.cases) == 1

    @pytest.mark.asyncio
    async def test_run_eval_structure_type(self):
        evaluator = SkillEvaluator()
        skill = _make_skill()
        case = EvalCase(
            name="structure-check",
            prompt="check structure",
            expected=[],
            eval_type=EvalType.STRUCTURE,
        )
        result = await evaluator.run_eval(skill, case)
        assert result.passed
        assert result.score > 0

    @pytest.mark.asyncio
    async def test_run_eval_trigger_type(self):
        evaluator = SkillEvaluator()
        skill = _make_skill(name="code-review")
        case = EvalCase(
            name="trigger-check",
            prompt="review my code",
            expected=[],
            eval_type=EvalType.TRIGGER,
        )
        result = await evaluator.run_eval(skill, case)
        assert result.skill_name == "code-review"

    @pytest.mark.asyncio
    async def test_run_suite(self):
        evaluator = SkillEvaluator()
        skill = _make_skill()
        cases = [
            EvalCase(name="s1", prompt="test", expected=[], eval_type=EvalType.STRUCTURE),
            EvalCase(name="s2", prompt="test", expected=[], eval_type=EvalType.STRUCTURE),
        ]
        suite = EvalSuite(
            skill_name="test-skill",
            cases=cases,
            created_at=datetime.now(timezone.utc),
        )
        result = await evaluator.run_suite(skill, suite)
        assert result.pass_rate > 0
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_generate_evals(self):
        evaluator = SkillEvaluator()
        skill = _make_skill()
        evals = await evaluator.generate_evals(skill)
        assert len(evals) > 0
        assert all(isinstance(e, EvalCase) for e in evals)

    @pytest.mark.asyncio
    async def test_regression_test(self):
        evaluator = SkillEvaluator()
        original = _make_skill()
        improved = _make_skill()
        cases = [
            EvalCase(name="r1", prompt="test", expected=[], eval_type=EvalType.STRUCTURE),
        ]
        suite = EvalSuite(
            skill_name="test-skill",
            cases=cases,
            created_at=datetime.now(timezone.utc),
        )
        passed = await evaluator.regression_test(original, improved, suite)
        assert isinstance(passed, bool)


# ── FailureAnalyzer ────────────────────────────────────────────────────


class TestFailureAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_timeout(self):
        analyzer = FailureAnalyzer()
        skill = _make_skill()
        execution = _make_execution(success=False, duration_ms=120000, output="timeout")
        analysis = await analyzer.analyze(execution, skill)
        assert analysis.failure_type == FailureType.TIMEOUT

    @pytest.mark.asyncio
    async def test_analyze_safety_violation(self):
        analyzer = FailureAnalyzer()
        skill = _make_skill()
        execution = _make_execution(success=False, output="rm -rf /")
        analysis = await analyzer.analyze(execution, skill)
        assert analysis.failure_type == FailureType.SAFETY_VIOLATION

    @pytest.mark.asyncio
    async def test_analyze_pattern_error(self):
        analyzer = FailureAnalyzer()
        skill = _make_skill()
        execution = _make_execution(success=False, feedback="wrong tool used")
        analysis = await analyzer.analyze(execution, skill)
        assert analysis.failure_type == FailureType.PATTERN_ERROR

    @pytest.mark.asyncio
    async def test_aggregate_and_trigger(self):
        analyzer = FailureAnalyzer()
        skill = _make_skill()

        for _ in range(4):
            execution = _make_execution(success=False, output="rm -rf /tmp")
            await analyzer.analyze(execution, skill)

        summary = analyzer.aggregate(skill.metadata.name)
        assert summary.total_failures == 4
        assert summary.has_safety_violation
        assert analyzer.should_trigger_improvement(summary)

    @pytest.mark.asyncio
    async def test_trigger_even_single_high_rate(self):
        analyzer = FailureAnalyzer()
        skill = _make_skill()
        execution = _make_execution(success=False, output="minor issue")
        await analyzer.analyze(execution, skill)
        summary = analyzer.aggregate(skill.metadata.name)
        assert summary.failure_rate_24h == 1.0
        assert analyzer.should_trigger_improvement(summary)


# ── Reflection + Evolution Pipeline ────────────────────────────────────


class TestEvolutionPipeline:
    @pytest.mark.asyncio
    async def test_reflect_on_success(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = _make_skill()
        execution = _make_execution(success=True, score=0.95)
        result = await evolver.reflect_on_execution(skill, execution)
        assert result["success"]
        assert len(result["recommendations"]) == 0

    @pytest.mark.asyncio
    async def test_reflect_on_failure(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = _make_skill()
        execution = _make_execution(success=False, score=0.3, output="rm -rf /")
        result = await evolver.reflect_on_execution(skill, execution)
        assert not result["success"]
        assert "failure_type" in result

    @pytest.mark.asyncio
    async def test_constraint_promotion_after_repeated_recommendation(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = _make_skill()
        original_constraint_count = len(skill.constraints)

        for _ in range(4):
            execution = _make_execution(
                success=False, score=0.3,
                feedback="wrong tool used",
                output="failed output",
            )
            await evolver.reflect_on_execution(skill, execution)

        assert len(skill.reflection_log) == 4
        assert len(skill.constraints) >= original_constraint_count

    @pytest.mark.asyncio
    async def test_should_evolve_threshold(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = _make_skill()

        assert not await evolver.should_evolve(skill)

        for i in range(4):
            skill.record_execution(_make_execution(success=(i < 1), score=0.5))

        assert await evolver.should_evolve(skill)

    @pytest.mark.asyncio
    async def test_heuristic_improve(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = _make_skill()
        registry.register(skill)

        for _ in range(4):
            skill.record_execution(
                _make_execution(success=False, score=0.4, feedback="Missing validation")
            )

        improved = await evolver.improve_skill(skill)
        assert improved is not None
        assert improved.metadata.version != skill.metadata.version
        assert improved.parent_skill_id == skill.id
