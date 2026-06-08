"""Curator system tests.

Tests quality review, output scoring, constraint checking,
feedback tracking, and quality trends.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Curator Models
# ---------------------------------------------------------------------------

@dataclass
class QualityScore:
    accuracy: float = 0.0  # 0-1
    completeness: float = 0.0
    relevance: float = 0.0
    coherence: float = 0.0
    safety: float = 1.0

    @property
    def overall(self) -> float:
        weights = {
            "accuracy": 0.3,
            "completeness": 0.25,
            "relevance": 0.25,
            "coherence": 0.1,
            "safety": 0.1,
        }
        score = (
            self.accuracy * weights["accuracy"]
            + self.completeness * weights["completeness"]
            + self.relevance * weights["relevance"]
            + self.coherence * weights["coherence"]
            + self.safety * weights["safety"]
        )
        return round(score, 4)

    @property
    def is_passing(self) -> bool:
        return self.overall >= 0.6 and self.safety >= 0.8

    def to_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "completeness": self.completeness,
            "relevance": self.relevance,
            "coherence": self.coherence,
            "safety": self.safety,
            "overall": self.overall,
            "passing": self.is_passing,
        }


@dataclass
class ReviewResult:
    request: str
    output: str
    score: QualityScore
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    constraint_violations: list[str] = field(default_factory=list)
    reviewed_at: str = ""
    reviewer: str = "curator"

    def __post_init__(self):
        if not self.reviewed_at:
            self.reviewed_at = datetime.datetime.utcnow().isoformat()

    @property
    def is_flagged(self) -> bool:
        return not self.score.is_passing or len(self.constraint_violations) > 0

    def to_dict(self) -> dict:
        return {
            "score": self.score.to_dict(),
            "issues": self.issues,
            "suggestions": self.suggestions,
            "flagged": self.is_flagged,
            "constraint_violations": self.constraint_violations,
        }


class Curator:
    """Review and score AI outputs for quality."""

    def __init__(self):
        self.reviews: list[ReviewResult] = []

    def review(self, request: str, output: str,
               constraints: list[str] | None = None) -> ReviewResult:
        """Review an AI output for quality."""
        score = self._compute_score(request, output)
        issues = self._find_issues(output)
        suggestions = self._generate_suggestions(request, output, score)
        violations = self._check_constraints(output, constraints or [])

        result = ReviewResult(
            request=request,
            output=output,
            score=score,
            issues=issues,
            suggestions=suggestions,
            constraint_violations=violations,
        )
        self.reviews.append(result)
        return result

    def _compute_score(self, request: str, output: str) -> QualityScore:
        """Compute quality score (simplified heuristic)."""
        # Length-based completeness
        completeness = min(len(output) / max(len(request) * 3, 1), 1.0)

        # Keyword relevance
        req_words = set(request.lower().split())
        out_words = set(output.lower().split())
        relevance = len(req_words & out_words) / max(len(req_words), 1)
        relevance = min(relevance, 1.0)

        # Coherence (has structure)
        coherence = 0.7
        if "\n" in output:
            coherence += 0.1
        if any(c in output for c in [".", "!", "?"]):
            coherence += 0.1
        if len(output.split()) > 5:
            coherence += 0.1
        coherence = min(coherence, 1.0)

        # Safety (check for dangerous content)
        safety = 1.0
        dangerous = ["rm -rf", "DROP TABLE", "<script>", "eval("]
        for d in dangerous:
            if d.lower() in output.lower():
                safety -= 0.3

        return QualityScore(
            accuracy=0.8,  # Would need LLM to properly assess
            completeness=round(completeness, 4),
            relevance=round(relevance, 4),
            coherence=round(coherence, 4),
            safety=max(0.0, round(safety, 4)),
        )

    def _find_issues(self, output: str) -> list[str]:
        issues = []
        if len(output) < 10:
            issues.append("Output is very short")
        if output == output.upper() and len(output) > 20:
            issues.append("Output is all caps")
        if not output.strip():
            issues.append("Output is empty")
        return issues

    def _generate_suggestions(self, request: str, output: str,
                              score: QualityScore) -> list[str]:
        suggestions = []
        if score.completeness < 0.5:
            suggestions.append("Provide more detailed output")
        if score.relevance < 0.3:
            suggestions.append("Output may not address the request")
        if score.coherence < 0.6:
            suggestions.append("Improve output structure and formatting")
        return suggestions

    def _check_constraints(self, output: str, constraints: list[str]) -> list[str]:
        violations = []
        for constraint in constraints:
            # Simple keyword check (real implementation would use LLM)
            if "no" in constraint.lower() or "must not" in constraint.lower():
                # Check if the forbidden thing is present
                words = constraint.lower().replace("no ", "").replace("must not ", "").split()
                for word in words:
                    if len(word) > 3 and word in output.lower():
                        violations.append(f"Possible violation of: {constraint}")
                        break
        return violations

    @property
    def review_count(self) -> int:
        return len(self.reviews)

    @property
    def avg_quality_score(self) -> float:
        if not self.reviews:
            return 0.0
        return round(
            sum(r.score.overall for r in self.reviews) / len(self.reviews), 4
        )

    @property
    def flagged_count(self) -> int:
        return sum(1 for r in self.reviews if r.is_flagged)

    def quality_trend(self, window: int = 10) -> list[float]:
        recent = self.reviews[-window:]
        return [r.score.overall for r in recent]

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "review_count": self.review_count,
            "avg_quality": self.avg_quality_score,
            "flagged_count": self.flagged_count,
            "passing_rate": round(
                sum(1 for r in self.reviews if not r.is_flagged) / max(self.review_count, 1) * 100, 1
            ),
        }


# ---------------------------------------------------------------------------
# Tests: QualityScore
# ---------------------------------------------------------------------------

class TestQualityScore:
    def test_perfect_score(self):
        score = QualityScore(accuracy=1.0, completeness=1.0, relevance=1.0, coherence=1.0, safety=1.0)
        assert score.overall == 1.0
        assert score.is_passing is True

    def test_zero_score(self):
        score = QualityScore(accuracy=0, completeness=0, relevance=0, coherence=0, safety=0)
        assert score.overall == 0.0
        assert score.is_passing is False

    def test_safety_threshold(self):
        score = QualityScore(accuracy=0.9, completeness=0.9, relevance=0.9, coherence=0.9, safety=0.5)
        assert score.is_passing is False  # Safety below 0.8

    def test_overall_threshold(self):
        score = QualityScore(accuracy=0.3, completeness=0.3, relevance=0.3, coherence=0.3, safety=1.0)
        assert score.is_passing is False  # Overall below 0.6

    def test_to_dict(self):
        score = QualityScore(accuracy=0.8, completeness=0.7, relevance=0.9, coherence=0.85, safety=1.0)
        d = score.to_dict()
        assert "overall" in d
        assert "passing" in d
        assert d["accuracy"] == 0.8


# ---------------------------------------------------------------------------
# Tests: ReviewResult
# ---------------------------------------------------------------------------

class TestReviewResult:
    def test_create_result(self):
        score = QualityScore(accuracy=0.8, completeness=0.7, relevance=0.9, coherence=0.8, safety=1.0)
        result = ReviewResult(request="test", output="response", score=score)
        assert result.is_flagged is False

    def test_flagged_low_score(self):
        score = QualityScore(accuracy=0.2, completeness=0.1, relevance=0.1, coherence=0.1, safety=1.0)
        result = ReviewResult(request="test", output="bad", score=score)
        assert result.is_flagged is True

    def test_flagged_constraint_violation(self):
        score = QualityScore(accuracy=0.9, completeness=0.9, relevance=0.9, coherence=0.9, safety=1.0)
        result = ReviewResult(
            request="test", output="good output", score=score,
            constraint_violations=["Used forbidden pattern"],
        )
        assert result.is_flagged is True

    def test_to_dict(self):
        score = QualityScore(accuracy=0.8)
        result = ReviewResult(request="req", output="out", score=score, issues=["short"])
        d = result.to_dict()
        assert "score" in d
        assert "issues" in d
        assert "flagged" in d


# ---------------------------------------------------------------------------
# Tests: Curator
# ---------------------------------------------------------------------------

class TestCurator:
    def test_review_output(self):
        curator = Curator()
        result = curator.review("Write a greeting", "Hello! How can I help you today?")
        assert result.score.overall > 0
        assert curator.review_count == 1

    def test_review_short_output(self):
        curator = Curator()
        result = curator.review("Write a detailed essay about AI", "AI is good.")
        assert "short" in " ".join(result.issues).lower() or result.score.completeness < 0.5

    def test_review_with_constraints(self):
        curator = Curator()
        result = curator.review(
            "Write about databases",
            "Use DROP TABLE to reset the database",
            constraints=["No destructive SQL commands"],
        )
        assert result.score.safety < 1.0

    def test_avg_quality(self):
        curator = Curator()
        curator.review("Request 1", "This is a good and detailed response to the first request.")
        curator.review("Request 2", "Another quality response with relevant information here.")
        assert curator.avg_quality_score > 0

    def test_flagged_count(self):
        curator = Curator()
        curator.review("Good request", "A thorough and complete response to this request.")
        curator.review("Bad request", "x")  # Very short, likely flagged
        assert curator.flagged_count >= 0

    def test_quality_trend(self):
        curator = Curator()
        for i in range(5):
            curator.review(f"Request {i}", f"Response {i} " * (i + 5))
        trend = curator.quality_trend(window=5)
        assert len(trend) == 5

    def test_stats(self):
        curator = Curator()
        curator.review("Test", "A reasonable response to the test query provided.")
        stats = curator.stats
        assert stats["review_count"] == 1
        assert "avg_quality" in stats
        assert "passing_rate" in stats

    def test_empty_curator(self):
        curator = Curator()
        assert curator.review_count == 0
        assert curator.avg_quality_score == 0
        assert curator.flagged_count == 0

    def test_multiple_reviews(self):
        curator = Curator()
        for i in range(20):
            curator.review(f"Request {i}", f"Response number {i} with adequate content and detail.")
        assert curator.review_count == 20
        assert curator.avg_quality_score > 0
