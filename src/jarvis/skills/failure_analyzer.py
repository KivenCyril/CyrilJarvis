"""Skill execution failure classifier and analyzer.

Classifies failed executions into actionable categories, aggregates
patterns across a skill's history, and decides when to trigger
automatic improvement via :class:`~jarvis.skills.evolve.SkillEvolver`.

Supports two analysis paths:

* **Heuristic** -- keyword / threshold rules (always available).
* **LLM** -- contextual analysis via an LLM provider (when configured).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from jarvis.skills.base import Skill, SkillExecution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety-related patterns
# ---------------------------------------------------------------------------

_SAFETY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
    re.compile(r"DELETE\s+FROM\s+\S+\s*(;|$)", re.IGNORECASE),
    re.compile(r"sudo\s+chmod\s+777", re.IGNORECASE),
    re.compile(r":(){ :\|:& };:", re.IGNORECASE),  # fork bomb
    re.compile(r"curl\s+.*\|\s*sh", re.IGNORECASE),
]

_TRIGGER_KEYWORDS: list[str] = [
    "wrong tool",
    "incorrect",
    "shouldn't have",
    "should not have",
    "not what i asked",
    "wrong function",
]

# Thresholds for triggering improvement
_CONSECUTIVE_FAILURE_THRESHOLD = 3
_FAILURE_RATE_24H_THRESHOLD = 0.20
_RECOMMENDATION_REPEAT_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FailureType(str, Enum):
    """Category of a skill execution failure."""

    TRIGGER_ERROR = "trigger_error"
    PATTERN_ERROR = "pattern_error"
    CAPABILITY_EXCEEDED = "capability_exceeded"
    SAFETY_VIOLATION = "safety_violation"
    QUALITY_DEGRADATION = "quality_degradation"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class FailureAnalysis(BaseModel):
    """Result of analyzing a single failed execution."""

    execution_id: str
    skill_name: str
    failure_type: FailureType
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause: str
    recommendation: str
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class FailureSummary(BaseModel):
    """Aggregated failure statistics for a single skill."""

    skill_name: str
    total_failures: int
    type_distribution: dict[str, int]
    top_recommendations: list[str]
    consecutive_failures: int
    failure_rate_24h: float
    has_safety_violation: bool
    should_improve: bool


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class FailureAnalyzer:
    """Classifies skill execution failures and aggregates patterns.

    Parameters:
        llm_registry: Optional LLM registry for AI-driven analysis.
            When ``None`` the analyzer uses heuristic rules only.
    """

    def __init__(self, llm_registry: Any = None) -> None:
        self._llm = llm_registry
        self._analyses: dict[str, list[FailureAnalysis]] = {}

    # ------------------------------------------------------------------
    # Single-execution analysis
    # ------------------------------------------------------------------

    async def analyze(
        self, execution: SkillExecution, skill: Skill
    ) -> FailureAnalysis:
        """Analyze a single failed execution and classify the failure.

        Uses heuristic rules first; falls back to LLM when the heuristic
        yields ``UNKNOWN`` and an LLM provider is available.
        """
        analysis = self._analyze_heuristic(execution, skill)

        if analysis.failure_type is FailureType.UNKNOWN and self._llm is not None:
            try:
                analysis = await self._analyze_with_llm(execution, skill)
            except Exception:
                logger.exception(
                    "LLM failure analysis failed for execution '%s', "
                    "keeping heuristic result",
                    execution.id,
                )

        self._analyses.setdefault(skill.metadata.name, []).append(analysis)
        logger.debug(
            "Classified execution '%s' of skill '%s' as %s (confidence=%.2f)",
            execution.id,
            skill.metadata.name,
            analysis.failure_type.value,
            analysis.confidence,
        )
        return analysis

    # ------------------------------------------------------------------
    # Heuristic classification
    # ------------------------------------------------------------------

    def _analyze_heuristic(
        self, execution: SkillExecution, skill: Skill
    ) -> FailureAnalysis:
        """Rule-based classification using keywords and thresholds."""
        output_lower = execution.output.lower()
        feedback_lower = execution.feedback.lower()
        combined = f"{output_lower} {feedback_lower}"

        # 1. Safety violation -- highest priority
        for pattern in _SAFETY_PATTERNS:
            if pattern.search(execution.output):
                return self._build(
                    execution,
                    skill,
                    FailureType.SAFETY_VIOLATION,
                    confidence=0.95,
                    root_cause=f"Output matched safety pattern: {pattern.pattern}",
                    recommendation="Add explicit safety constraint to prevent this pattern",
                )

        # 2. Timeout
        if execution.duration_ms > 0 and self._looks_like_timeout(
            execution, skill
        ):
            return self._build(
                execution,
                skill,
                FailureType.TIMEOUT,
                confidence=0.85,
                root_cause=(
                    f"Execution took {execution.duration_ms}ms, "
                    f"exceeding expected duration"
                ),
                recommendation="Add timeout guard or break task into smaller steps",
            )

        # 3. Trigger / pattern error -- feedback keywords
        for keyword in _TRIGGER_KEYWORDS:
            if keyword in combined:
                return self._build(
                    execution,
                    skill,
                    FailureType.PATTERN_ERROR,
                    confidence=0.80,
                    root_cause=f"Feedback indicates wrong behaviour: '{keyword}'",
                    recommendation="Refine trigger conditions or step routing logic",
                )

        if "should not trigger" in combined or "false positive" in combined:
            return self._build(
                execution,
                skill,
                FailureType.TRIGGER_ERROR,
                confidence=0.80,
                root_cause="Skill triggered when it should not have",
                recommendation="Tighten skill matching criteria",
            )

        if "should have triggered" in combined or "false negative" in combined:
            return self._build(
                execution,
                skill,
                FailureType.TRIGGER_ERROR,
                confidence=0.75,
                root_cause="Skill failed to trigger when it should have",
                recommendation="Broaden skill matching criteria",
            )

        # 4. Quality degradation -- score trend
        if self._has_quality_degradation(execution, skill):
            return self._build(
                execution,
                skill,
                FailureType.QUALITY_DEGRADATION,
                confidence=0.70,
                root_cause="Scores show a consistent downward trend",
                recommendation="Review recent changes for regressions",
            )

        # 5. Capability exceeded -- empty or extremely short output
        if not execution.output or len(execution.output.strip()) < 10:
            return self._build(
                execution,
                skill,
                FailureType.CAPABILITY_EXCEEDED,
                confidence=0.60,
                root_cause="Output is empty or nearly empty, suggesting the task is beyond skill scope",
                recommendation="Expand skill capabilities or decompose into sub-skills",
            )

        # 6. Unknown
        return self._build(
            execution,
            skill,
            FailureType.UNKNOWN,
            confidence=0.30,
            root_cause="No heuristic rule matched; manual review recommended",
            recommendation="Investigate execution logs for root cause",
        )

    def _looks_like_timeout(
        self, execution: SkillExecution, skill: Skill
    ) -> bool:
        """Heuristic: execution took > 3x the average of successful runs."""
        successful = [
            e for e in skill.executions
            if e.success and e.duration_ms > 0
        ]
        if not successful:
            # No baseline; treat anything > 60 seconds as suspicious
            return execution.duration_ms > 60_000

        avg_ms = sum(e.duration_ms for e in successful) / len(successful)
        return execution.duration_ms > avg_ms * 3

    def _has_quality_degradation(
        self, execution: SkillExecution, skill: Skill
    ) -> bool:
        """Check for a monotonically decreasing score trend (last 3+)."""
        scored = [e for e in skill.executions if e.score > 0]
        # Include the current execution if scored
        if execution.score > 0:
            scored.append(execution)
        recent = scored[-3:]
        if len(recent) < 3:
            return False
        scores = [e.score for e in recent]
        return scores[0] > scores[1] > scores[2]

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    async def _analyze_with_llm(
        self, execution: SkillExecution, skill: Skill
    ) -> FailureAnalysis:
        """Use an LLM to classify the failure when heuristics are uncertain."""
        failure_types_desc = "\n".join(
            f"  - {ft.value}: {_FAILURE_TYPE_DESCRIPTIONS[ft]}"
            for ft in FailureType
        )

        prompt = (
            "You are a Skill Failure Analyst.  Given the execution context "
            "below, classify the failure and suggest an improvement.\n\n"
            f"Skill: {skill.metadata.name} v{skill.metadata.version}\n"
            f"Description: {skill.metadata.description}\n"
            f"Input: {execution.input_context[:500]}\n"
            f"Output: {execution.output[:500]}\n"
            f"Feedback: {execution.feedback}\n"
            f"Duration: {execution.duration_ms}ms\n"
            f"Score: {execution.score}\n\n"
            f"Failure categories:\n{failure_types_desc}\n\n"
            "Respond in exactly this format:\n"
            "FAILURE_TYPE: <one of the category values above>\n"
            "CONFIDENCE: <0.0-1.0>\n"
            "ROOT_CAUSE: <one-line description>\n"
            "RECOMMENDATION: <one-line suggestion>\n"
        )

        provider = self._llm.get()
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_llm_analysis(response.content, execution, skill)

    def _parse_llm_analysis(
        self, text: str, execution: SkillExecution, skill: Skill
    ) -> FailureAnalysis:
        """Parse structured LLM response into a FailureAnalysis."""
        failure_type = FailureType.UNKNOWN
        confidence = 0.5
        root_cause = "LLM analysis (unparsed)"
        recommendation = "Review LLM output manually"

        for line in text.strip().splitlines():
            stripped = line.strip()
            if stripped.startswith("FAILURE_TYPE:"):
                raw = stripped[13:].strip().lower()
                try:
                    failure_type = FailureType(raw)
                except ValueError:
                    failure_type = FailureType.UNKNOWN
            elif stripped.startswith("CONFIDENCE:"):
                try:
                    confidence = max(0.0, min(1.0, float(stripped[11:].strip())))
                except ValueError:
                    pass
            elif stripped.startswith("ROOT_CAUSE:"):
                root_cause = stripped[11:].strip()
            elif stripped.startswith("RECOMMENDATION:"):
                recommendation = stripped[15:].strip()

        return self._build(
            execution, skill, failure_type, confidence, root_cause, recommendation
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def aggregate(self, skill_name: str) -> FailureSummary:
        """Aggregate all recorded failure analyses for a skill."""
        analyses = self._analyses.get(skill_name, [])

        type_counts: Counter[str] = Counter(
            a.failure_type.value for a in analyses
        )

        # Top recommendations: those appearing >= _RECOMMENDATION_REPEAT_THRESHOLD times
        rec_counts: Counter[str] = Counter(a.recommendation for a in analyses)
        top_recs = [
            rec
            for rec, count in rec_counts.most_common()
            if count >= _RECOMMENDATION_REPEAT_THRESHOLD
        ]
        # If none meet the threshold, take the top-3 by frequency anyway
        if not top_recs:
            top_recs = [rec for rec, _ in rec_counts.most_common(3)]

        consecutive = self._consecutive_tail_failures(analyses)
        rate_24h = self._failure_rate_24h(skill_name)
        has_safety = type_counts.get(FailureType.SAFETY_VIOLATION.value, 0) > 0

        summary = FailureSummary(
            skill_name=skill_name,
            total_failures=len(analyses),
            type_distribution=dict(type_counts),
            top_recommendations=top_recs,
            consecutive_failures=consecutive,
            failure_rate_24h=rate_24h,
            has_safety_violation=has_safety,
            should_improve=False,  # filled in below
        )
        summary.should_improve = self.should_trigger_improvement(summary)
        return summary

    # ------------------------------------------------------------------
    # Improvement trigger
    # ------------------------------------------------------------------

    def should_trigger_improvement(self, summary: FailureSummary) -> bool:
        """Decide whether accumulated failures justify triggering evolution."""
        # Rule 1: safety violation -> immediate
        if summary.has_safety_violation:
            logger.warning(
                "Safety violation detected for skill '%s'; triggering improvement",
                summary.skill_name,
            )
            return True

        # Rule 2: consecutive failures >= threshold
        if summary.consecutive_failures >= _CONSECUTIVE_FAILURE_THRESHOLD:
            return True

        # Rule 3: 24h failure rate > threshold
        if summary.failure_rate_24h > _FAILURE_RATE_24H_THRESHOLD:
            return True

        # Rule 4: same recommendation repeated enough times
        rec_counts: Counter[str] = Counter(
            a.recommendation
            for a in self._analyses.get(summary.skill_name, [])
        )
        if any(c >= _RECOMMENDATION_REPEAT_THRESHOLD for c in rec_counts.values()):
            return True

        return False

    def get_improvement_context(self, summary: FailureSummary) -> dict[str, Any]:
        """Build structured context for SkillEvolver consumption."""
        analyses = self._analyses.get(summary.skill_name, [])

        # Pick up to 3 representative failures (highest confidence per type)
        seen_types: set[str] = set()
        exemplars: list[dict[str, Any]] = []
        for a in sorted(analyses, key=lambda x: x.confidence, reverse=True):
            if a.failure_type.value not in seen_types and len(exemplars) < 3:
                seen_types.add(a.failure_type.value)
                exemplars.append(
                    {
                        "execution_id": a.execution_id,
                        "failure_type": a.failure_type.value,
                        "root_cause": a.root_cause,
                        "recommendation": a.recommendation,
                        "confidence": a.confidence,
                    }
                )

        return {
            "skill_name": summary.skill_name,
            "total_failures": summary.total_failures,
            "type_distribution": summary.type_distribution,
            "top_recommendations": summary.top_recommendations,
            "consecutive_failures": summary.consecutive_failures,
            "failure_rate_24h": summary.failure_rate_24h,
            "has_safety_violation": summary.has_safety_violation,
            "exemplar_failures": exemplars,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build(
        execution: SkillExecution,
        skill: Skill,
        failure_type: FailureType,
        confidence: float,
        root_cause: str,
        recommendation: str,
    ) -> FailureAnalysis:
        """Convenience factory for FailureAnalysis."""
        return FailureAnalysis(
            execution_id=execution.id,
            skill_name=skill.metadata.name,
            failure_type=failure_type,
            confidence=confidence,
            root_cause=root_cause,
            recommendation=recommendation,
        )

    @staticmethod
    def _consecutive_tail_failures(analyses: list[FailureAnalysis]) -> int:
        """Count how many of the most recent analyses are consecutive."""
        count = 0
        for a in reversed(analyses):
            # Every entry in _analyses is already a failure, so just count tail length
            count += 1
        return count

    def _failure_rate_24h(self, skill_name: str) -> float:
        """Compute failure rate in the last 24 hours.

        Uses the ratio of failure analyses to total analyses stored.
        Since only failures are tracked here, we return 1.0 when any
        exist and 0.0 otherwise -- callers should cross-reference with
        ``Skill.use_count`` for a true rate.  If the caller has access
        to the Skill object, the recommended approach is::

            rate = failures_24h / max(total_executions_24h, 1)

        For the in-memory summary, we approximate by counting analyses
        whose ``analyzed_at`` falls within the window.
        """
        analyses = self._analyses.get(skill_name, [])
        if not analyses:
            return 0.0

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [a for a in analyses if a.analyzed_at >= cutoff]
        if not recent:
            return 0.0

        # Without access to total execution count we report the fraction
        # of recent failures over all recorded analyses as a proxy.
        total_all = len(analyses)
        return len(recent) / max(total_all, 1)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_FAILURE_TYPE_DESCRIPTIONS: dict[FailureType, str] = {
    FailureType.TRIGGER_ERROR: "Skill triggered incorrectly or failed to trigger",
    FailureType.PATTERN_ERROR: "Chose the wrong processing path or tool",
    FailureType.CAPABILITY_EXCEEDED: "Task exceeds the skill's designed capability",
    FailureType.SAFETY_VIOLATION: "Output contains dangerous or forbidden patterns",
    FailureType.QUALITY_DEGRADATION: "Output quality declined compared to history",
    FailureType.TIMEOUT: "Execution exceeded expected time limits",
    FailureType.UNKNOWN: "Failure could not be classified automatically",
}
