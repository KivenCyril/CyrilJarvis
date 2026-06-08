from __future__ import annotations
import json, logging, re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class ReviewVerdict(str, Enum):
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"
    FLAGGED = "flagged"  # needs human review

class ReviewResult(BaseModel):
    """Result of a curator review."""
    verdict: ReviewVerdict
    score: float = 0.0  # 0-1 quality score
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    hallucination_risk: float = 0.0  # 0-1
    safety_flags: list[str] = Field(default_factory=list)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewer: str = "curator"  # "curator" or "human"

_REVIEW_PROMPT = """\
You are a quality assurance reviewer for an AI assistant's output.

Review the following agent output for:
1. **Accuracy**: Are claims factually correct? Any hallucinations?
2. **Completeness**: Does it fully address the user's request?
3. **Safety**: Any harmful, biased, or inappropriate content?
4. **Quality**: Is it well-structured, clear, and actionable?
5. **Constraint compliance**: Does it follow all given constraints?

User request: {request}
Constraints: {constraints}
Agent output: {output}

Return a JSON object:
{{
    "verdict": "approved|needs_revision|rejected|flagged",
    "score": 0.85,
    "issues": ["issue 1", "issue 2"],
    "suggestions": ["suggestion 1"],
    "hallucination_risk": 0.1,
    "safety_flags": []
}}

Return ONLY valid JSON, no markdown fences.
"""

_SKILL_REVIEW_PROMPT = """\
You are reviewing an AI-generated skill for quality and safety.

Skill name: {name}
Skill procedure:
{procedure}

Check for:
1. Are the steps clear and actionable?
2. Any dangerous operations (rm -rf, DROP TABLE, etc.)?
3. Is the skill too specific or too generic?
4. Would this skill work reliably across different contexts?

Return a JSON object with verdict, score (0-1), issues, and suggestions.
Return ONLY valid JSON.
"""

def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


class Curator:
    """Meta-review system for agent output quality assurance.

    Inspired by Hermes Agent's curator.py. The Curator:
    1. Reviews agent outputs for accuracy, safety, and quality
    2. Detects potential hallucinations
    3. Checks constraint compliance
    4. Reviews skills for safety and reliability
    5. Tracks quality metrics over time
    6. Can flag outputs for human review

    Works with or without LLM (falls back to heuristic checks).
    """

    def __init__(self, llm_registry: Any = None):
        self._llm_registry = llm_registry
        self._review_history: list[ReviewResult] = []
        self._quality_scores: list[float] = []

    async def review_output(
        self,
        request: str,
        output: str,
        constraints: list[str] | None = None,
        agent_name: str = "",
    ) -> ReviewResult:
        """Review an agent's output for quality."""
        if self._llm_registry:
            result = await self._llm_review(request, output, constraints or [])
        else:
            result = self._heuristic_review(request, output, constraints or [])

        self._review_history.append(result)
        self._quality_scores.append(result.score)
        return result

    async def _llm_review(
        self, request: str, output: str, constraints: list[str]
    ) -> ReviewResult:
        from jarvis.llm.provider import Message, Role

        try:
            llm = self._llm_registry.get()
            prompt = _REVIEW_PROMPT.format(
                request=request[:1000],
                constraints=json.dumps(constraints),
                output=output[:3000],
            )
            response = await llm.chat(
                messages=[Message(role=Role.USER, content=prompt)],
                temperature=0.0,
                max_tokens=1024,
            )
            data = _parse_json(response.content)
            return ReviewResult(
                verdict=ReviewVerdict(data.get("verdict", "approved")),
                score=float(data.get("score", 0.7)),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                hallucination_risk=float(data.get("hallucination_risk", 0.0)),
                safety_flags=data.get("safety_flags", []),
            )
        except Exception as e:
            logger.warning("LLM review failed: %s", e)
            return self._heuristic_review(request, output, constraints)

    def _heuristic_review(
        self, request: str, output: str, constraints: list[str]
    ) -> ReviewResult:
        """Rule-based quality review when no LLM available."""
        issues = []
        score = 0.8
        safety_flags = []
        hallucination_risk = 0.0

        # Check output length
        if len(output) < 10:
            issues.append("Output is too short")
            score -= 0.3

        # Check for empty/error responses
        if output.startswith("Error:") or output.startswith("[Error"):
            issues.append("Output contains an error")
            score -= 0.4

        # Check constraint mentions (basic compliance check)
        output_lower = output.lower()
        for constraint in constraints:
            key_words = [w for w in constraint.lower().split() if len(w) > 3]
            if key_words and not any(w in output_lower for w in key_words[:3]):
                issues.append(f"May not address constraint: '{constraint[:50]}'")
                score -= 0.1

        # Safety checks
        dangerous_patterns = [
            "rm -rf", "DROP TABLE", "DELETE FROM", "format c:",
            "sudo rm", "chmod 777", "> /dev/sda",
        ]
        for pattern in dangerous_patterns:
            if pattern.lower() in output_lower:
                safety_flags.append(f"Contains dangerous pattern: {pattern}")
                score -= 0.2

        # Hallucination risk heuristics
        if any(phrase in output_lower for phrase in [
            "i believe", "i think", "probably", "might be",
            "as of my last", "i don't have access",
        ]):
            hallucination_risk = 0.3

        score = max(0.0, min(1.0, score))

        verdict = ReviewVerdict.APPROVED
        if safety_flags:
            verdict = ReviewVerdict.FLAGGED
        elif score < 0.4:
            verdict = ReviewVerdict.REJECTED
        elif score < 0.6:
            verdict = ReviewVerdict.NEEDS_REVISION

        return ReviewResult(
            verdict=verdict,
            score=score,
            issues=issues,
            suggestions=[],
            hallucination_risk=hallucination_risk,
            safety_flags=safety_flags,
        )

    async def review_skill(self, skill: Any) -> ReviewResult:
        """Review a skill for quality and safety before activation."""
        procedure = ""
        if hasattr(skill, "steps"):
            procedure = "\n".join(
                f"{s.order}. {s.action}" + (f" (tool: {s.tool})" if s.tool else "")
                for s in skill.steps
            )

        if self._llm_registry:
            try:
                from jarvis.llm.provider import Message, Role
                llm = self._llm_registry.get()
                prompt = _SKILL_REVIEW_PROMPT.format(
                    name=skill.metadata.name if hasattr(skill, "metadata") else "unknown",
                    procedure=procedure,
                )
                response = await llm.chat(
                    messages=[Message(role=Role.USER, content=prompt)],
                    temperature=0.0,
                    max_tokens=1024,
                )
                data = _parse_json(response.content)
                return ReviewResult(
                    verdict=ReviewVerdict(data.get("verdict", "approved")),
                    score=float(data.get("score", 0.7)),
                    issues=data.get("issues", []),
                    suggestions=data.get("suggestions", []),
                )
            except Exception:
                pass

        # Heuristic skill review
        issues = []
        score = 0.7

        if not procedure:
            issues.append("Skill has no steps defined")
            score -= 0.3

        dangerous = ["rm -rf", "DROP", "DELETE", "format", "sudo"]
        for d in dangerous:
            if d.lower() in procedure.lower():
                issues.append(f"Contains potentially dangerous operation: {d}")
                score -= 0.2

        return ReviewResult(
            verdict=ReviewVerdict.APPROVED if score >= 0.6 else ReviewVerdict.NEEDS_REVISION,
            score=max(0.0, score),
            issues=issues,
        )

    @property
    def avg_quality_score(self) -> float:
        if not self._quality_scores:
            return 0.0
        return sum(self._quality_scores) / len(self._quality_scores)

    @property
    def review_count(self) -> int:
        return len(self._review_history)

    def quality_trend(self, window: int = 10) -> list[float]:
        """Get recent quality scores for trend analysis."""
        return self._quality_scores[-window:]

    def get_flagged_reviews(self) -> list[ReviewResult]:
        """Get reviews that need human attention."""
        return [r for r in self._review_history if r.verdict == ReviewVerdict.FLAGGED]
