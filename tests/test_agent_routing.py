"""Agent routing and scoring tests.

Tests agent scoring algorithms, multi-agent routing, delegation chains,
intent matching, domain routing, and fallback behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Agent Routing Models
# ---------------------------------------------------------------------------

@dataclass
class AgentCapability:
    name: str
    description: str = ""
    weight: float = 1.0


@dataclass
class AgentCard:
    name: str
    description: str
    domain: str
    skills: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    capabilities: list[AgentCapability] = field(default_factory=list)
    can_delegate: bool = False
    priority: int = 0  # Higher = preferred when scores tie
    max_concurrent: int = 5
    model: str = "gpt-4"
    version: str = "1.0"

    @property
    def all_keywords(self) -> list[str]:
        """Combine skills and keywords for matching."""
        return list(set(self.skills + self.keywords))


@dataclass
class RoutingResult:
    agent_name: str
    score: float
    confidence: str  # high, medium, low
    matched_keywords: list[str] = field(default_factory=list)
    domain_match: bool = False


class AgentRouter:
    """Route messages to the best-matching agent."""

    def __init__(self):
        self.agents: list[AgentCard] = []
        self._domain_weights: dict[str, float] = {}

    def register(self, agent: AgentCard) -> None:
        self.agents.append(agent)

    def set_domain_weight(self, domain: str, weight: float) -> None:
        self._domain_weights[domain] = weight

    def score_agent(self, agent: AgentCard, message: str) -> RoutingResult:
        """Score how well an agent can handle a message."""
        msg_lower = message.lower()
        score = 0.0
        matched = []

        # Keyword matching (skills + keywords)
        for keyword in agent.all_keywords:
            kw_lower = keyword.lower()
            if kw_lower in msg_lower:
                score += 0.15
                matched.append(keyword)
            # Partial word match
            elif any(kw_lower in word for word in msg_lower.split()):
                score += 0.05
                matched.append(f"~{keyword}")

        # Domain matching
        domain_match = agent.domain.lower() in msg_lower
        if domain_match:
            score += 0.25
        # Domain weight boost
        domain_weight = self._domain_weights.get(agent.domain, 1.0)
        score *= domain_weight

        # Capability matching
        for cap in agent.capabilities:
            if cap.name.lower() in msg_lower:
                score += 0.1 * cap.weight
                matched.append(f"cap:{cap.name}")

        # Description similarity (simple keyword overlap)
        desc_words = set(agent.description.lower().split())
        msg_words = set(msg_lower.split())
        overlap = len(desc_words & msg_words)
        if overlap > 0:
            score += min(overlap * 0.05, 0.15)

        # Priority tiebreaker
        score += agent.priority * 0.001

        # Clamp score
        score = min(score, 1.0)

        # Determine confidence
        if score >= 0.6:
            confidence = "high"
        elif score >= 0.3:
            confidence = "medium"
        else:
            confidence = "low"

        return RoutingResult(
            agent_name=agent.name,
            score=round(score, 4),
            confidence=confidence,
            matched_keywords=matched,
            domain_match=domain_match,
        )

    def route(self, message: str, top_k: int = 3) -> list[RoutingResult]:
        """Route a message and return top-k ranked agents."""
        results = [self.score_agent(a, message) for a in self.agents]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def best_match(self, message: str) -> RoutingResult | None:
        """Get the single best matching agent."""
        results = self.route(message, top_k=1)
        if results and results[0].score > 0:
            return results[0]
        return None

    def route_with_fallback(self, message: str, fallback_agent: str) -> RoutingResult:
        """Route with a guaranteed fallback agent."""
        best = self.best_match(message)
        if best and best.confidence != "low":
            return best
        # Use fallback
        fallback = next((a for a in self.agents if a.name == fallback_agent), None)
        if fallback:
            return RoutingResult(
                agent_name=fallback.name,
                score=0.1,
                confidence="low",
                matched_keywords=["fallback"],
            )
        return RoutingResult(
            agent_name=fallback_agent,
            score=0.0,
            confidence="low",
        )


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def router():
    r = AgentRouter()
    r.register(AgentCard(
        name="code-agent",
        description="Expert in writing and reviewing code",
        domain="software engineering",
        skills=["python", "javascript", "code review", "refactoring", "debugging"],
        keywords=["code", "program", "function", "class", "bug", "error", "implement"],
        priority=5,
    ))
    r.register(AgentCard(
        name="research-agent",
        description="Research and analyze topics thoroughly",
        domain="research",
        skills=["research", "analysis", "summarize", "compare"],
        keywords=["find", "search", "analyze", "study", "investigate", "paper", "article"],
        priority=3,
    ))
    r.register(AgentCard(
        name="writer-agent",
        description="Write documents, articles, and content",
        domain="content creation",
        skills=["writing", "editing", "copywriting", "blogging"],
        keywords=["write", "draft", "article", "document", "content", "blog", "essay"],
        priority=2,
    ))
    r.register(AgentCard(
        name="devops-agent",
        description="Manage infrastructure and deployments",
        domain="devops",
        skills=["docker", "kubernetes", "ci/cd", "deployment", "monitoring"],
        keywords=["deploy", "server", "container", "pipeline", "infrastructure", "k8s"],
        priority=4,
    ))
    r.register(AgentCard(
        name="data-agent",
        description="Analyze data and create visualizations",
        domain="data science",
        skills=["sql", "pandas", "visualization", "statistics", "machine learning"],
        keywords=["data", "dataset", "csv", "chart", "graph", "model", "predict"],
        priority=3,
    ))
    return r


# ---------------------------------------------------------------------------
# Tests: AgentCard
# ---------------------------------------------------------------------------

class TestAgentCard:
    def test_create_card(self):
        card = AgentCard(name="test", description="Test agent", domain="testing")
        assert card.name == "test"
        assert card.domain == "testing"

    def test_all_keywords(self):
        card = AgentCard(
            name="test", description="", domain="",
            skills=["python", "java"],
            keywords=["python", "code"],
        )
        assert len(card.all_keywords) == 3  # python deduplicated

    def test_default_values(self):
        card = AgentCard(name="test", description="", domain="")
        assert card.can_delegate is False
        assert card.priority == 0
        assert card.max_concurrent == 5

    def test_capabilities(self):
        card = AgentCard(
            name="test", description="", domain="",
            capabilities=[
                AgentCapability(name="fast-response", weight=2.0),
                AgentCapability(name="multi-lang", weight=1.5),
            ],
        )
        assert len(card.capabilities) == 2
        assert card.capabilities[0].weight == 2.0


# ---------------------------------------------------------------------------
# Tests: AgentRouter - Basic Routing
# ---------------------------------------------------------------------------

class TestAgentRouterBasic:
    def test_route_code_request(self, router):
        results = router.route("review this python code for bugs")
        assert results[0].agent_name == "code-agent"
        assert results[0].confidence in ("high", "medium")

    def test_route_research_request(self, router):
        results = router.route("research the latest trends in AI papers")
        assert results[0].agent_name == "research-agent"

    def test_route_writing_request(self, router):
        results = router.route("write a blog article about technology")
        assert results[0].agent_name == "writer-agent"

    def test_route_devops_request(self, router):
        results = router.route("deploy the new container to kubernetes")
        assert results[0].agent_name == "devops-agent"

    def test_route_data_request(self, router):
        results = router.route("analyze this dataset and create a chart")
        assert results[0].agent_name == "data-agent"

    def test_route_returns_top_k(self, router):
        results = router.route("test", top_k=3)
        assert len(results) <= 3

    def test_route_returns_sorted(self, router):
        results = router.route("write python code")
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score


# ---------------------------------------------------------------------------
# Tests: AgentRouter - Scoring
# ---------------------------------------------------------------------------

class TestAgentRouterScoring:
    def test_keyword_match_boosts_score(self, router):
        result = router.score_agent(router.agents[0], "python code review")
        assert result.score > 0
        assert len(result.matched_keywords) >= 2

    def test_domain_match_boosts_score(self, router):
        result = router.score_agent(router.agents[0], "software engineering task")
        assert result.domain_match is True
        assert result.score > 0.2

    def test_no_match_low_score(self, router):
        result = router.score_agent(router.agents[0], "cook a delicious meal")
        assert result.score < 0.1
        assert result.confidence == "low"

    def test_score_capped_at_one(self, router):
        # Create an agent that matches everything
        agent = AgentCard(
            name="omniscient", description="everything everywhere",
            domain="all",
            skills=["every", "thing", "all", "of", "the", "words"],
            keywords=["test", "every", "keyword", "possible"],
        )
        result = router.score_agent(agent, "test every keyword possible thing all of the words")
        assert result.score <= 1.0

    def test_matched_keywords_tracked(self, router):
        result = router.score_agent(router.agents[0], "debug this python code")
        assert any("python" in kw for kw in result.matched_keywords)
        assert any("code" in kw or "debug" in kw for kw in result.matched_keywords)


# ---------------------------------------------------------------------------
# Tests: AgentRouter - Best Match
# ---------------------------------------------------------------------------

class TestAgentRouterBestMatch:
    def test_best_match(self, router):
        result = router.best_match("write a python function")
        assert result is not None
        assert result.agent_name in ["code-agent", "writer-agent"]

    def test_best_match_none(self):
        router = AgentRouter()  # Empty router
        result = router.best_match("hello world")
        assert result is None

    def test_best_match_no_match(self, router):
        result = router.best_match("xyzzy foo bar baz")
        # Should still return something but low confidence
        assert result is None or result.confidence == "low"


# ---------------------------------------------------------------------------
# Tests: AgentRouter - Fallback
# ---------------------------------------------------------------------------

class TestAgentRouterFallback:
    def test_fallback_on_low_confidence(self, router):
        result = router.route_with_fallback("xyzzy unknown request", "code-agent")
        assert result.agent_name == "code-agent"
        assert "fallback" in result.matched_keywords

    def test_no_fallback_on_good_match(self, router):
        result = router.route_with_fallback("review python code", "writer-agent")
        assert result.agent_name == "code-agent"
        assert "fallback" not in result.matched_keywords

    def test_fallback_nonexistent_agent(self, router):
        result = router.route_with_fallback("xyzzy", "nonexistent-agent")
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# Tests: AgentRouter - Domain Weights
# ---------------------------------------------------------------------------

class TestAgentRouterDomainWeights:
    def test_domain_weight_boost(self, router):
        # Without weight
        result1 = router.score_agent(router.agents[0], "fix this")

        # With weight
        router.set_domain_weight("software engineering", 2.0)
        result2 = router.score_agent(router.agents[0], "fix this")

        assert result2.score >= result1.score

    def test_domain_weight_reduces(self, router):
        router.set_domain_weight("software engineering", 0.5)
        result = router.score_agent(router.agents[0], "python code")
        # Score should be lower than default
        assert result.score < 0.5  # Reduced by weight


# ---------------------------------------------------------------------------
# Tests: RoutingResult
# ---------------------------------------------------------------------------

class TestRoutingResult:
    def test_create_result(self):
        r = RoutingResult(agent_name="test", score=0.8, confidence="high")
        assert r.agent_name == "test"
        assert r.score == 0.8

    def test_confidence_levels(self):
        for conf in ["high", "medium", "low"]:
            r = RoutingResult(agent_name="t", score=0.5, confidence=conf)
            assert r.confidence == conf

    def test_matched_keywords(self):
        r = RoutingResult(
            agent_name="t", score=0.5, confidence="medium",
            matched_keywords=["python", "code"],
        )
        assert len(r.matched_keywords) == 2

    def test_domain_match_flag(self):
        r = RoutingResult(
            agent_name="t", score=0.5, confidence="medium",
            domain_match=True,
        )
        assert r.domain_match is True


# ---------------------------------------------------------------------------
# Tests: Multi-Agent Scenarios
# ---------------------------------------------------------------------------

class TestMultiAgentScenarios:
    def test_ambiguous_request(self, router):
        """A request that could match multiple agents."""
        results = router.route("write python code to analyze data", top_k=5)
        # Multiple agents should score > 0
        positive = [r for r in results if r.score > 0]
        assert len(positive) >= 2

    def test_very_specific_request(self, router):
        """A very specific request should have clear winner."""
        results = router.route("deploy docker container to kubernetes cluster")
        assert results[0].agent_name == "devops-agent"
        assert results[0].confidence in ("high", "medium")

    def test_empty_message(self, router):
        results = router.route("")
        # All should score 0 or near 0
        assert all(r.score < 0.01 for r in results)

    def test_single_word_message(self, router):
        results = router.route("python")
        # code-agent should match
        code_result = next(r for r in results if r.agent_name == "code-agent")
        assert code_result.score > 0

    def test_many_agents(self):
        """Test with many agents registered."""
        router = AgentRouter()
        for i in range(50):
            router.register(AgentCard(
                name=f"agent-{i}",
                description=f"Agent {i} for domain {i}",
                domain=f"domain-{i}",
                skills=[f"xskill_{i}_x"],
                keywords=[f"xkw_{i}_x"],
            ))
        results = router.route("xkw_42_x")
        assert results[0].agent_name == "agent-42"
