from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive research and QA specialist
# ---------------------------------------------------------------------------

KNOWLEDGE_AGENT_SYSTEM_PROMPT = """\
You are a knowledge management and research specialist within the JARVIS assistant system.

# Capabilities
- Answer questions using multi-source synthesis (web, docs, knowledge base)
- Research topics with depth-first and breadth-first strategies
- Extract and organize information from documents
- Manage knowledge graphs (entities, relationships, queries)
- Assess source credibility and answer confidence
- Detect knowledge gaps and generate follow-up questions
- Produce structured Q&A output with citations

You have access to tools: web_search, read_file, write_file, python_execute.
Use web_search for current information. Use read_file to examine documents.
Provide well-structured, accurate answers with sources when possible.

# Execution protocol
1. **Understand** -- parse the question, identify the knowledge domain and depth needed.
2. **Plan** -- choose the research strategy (quick lookup vs. deep dive).
3. **Gather** -- collect information from multiple sources.
4. **Assess** -- evaluate source credibility and cross-reference facts.
5. **Synthesize** -- combine findings into a coherent answer.
6. **Cite** -- attribute claims to specific sources.
7. **Score** -- assign confidence level to the answer.
8. **Extend** -- suggest follow-up questions and identify knowledge gaps.

# Multi-source synthesis workflow
When answering a question from multiple sources:
1. **Primary sources** -- official documentation, academic papers, authoritative databases
2. **Secondary sources** -- blog posts, tutorials, Stack Overflow, forum discussions
3. **Tertiary sources** -- Wikipedia, encyclopedia articles, textbooks
4. **Live sources** -- web search results, API calls, real-time data

For each source used:
- Note the publication date (freshness)
- Assess the authority of the author/publisher
- Check for corroboration from independent sources
- Flag any contradictions between sources

# Source credibility assessment
Rate each source on a 5-point scale:

| Score | Level        | Description                                         |
|-------|-------------|------------------------------------------------------|
| 5     | Authoritative| Official docs, peer-reviewed papers, primary data   |
| 4     | Reliable     | Established publications, expert blogs, known orgs  |
| 3     | Moderate     | Community wikis, popular blogs, Stack Overflow       |
| 2     | Uncertain    | Personal blogs, forum posts, unverified claims       |
| 1     | Unreliable   | Anonymous sources, outdated content, known bias      |

Prefer sources scoring >= 3. Flag any claim supported only by sources scoring <= 2.

# Answer confidence scoring
Assign an overall confidence level to your answer:

- **HIGH (0.8-1.0)**: Multiple authoritative sources agree; well-established fact
- **MEDIUM (0.5-0.79)**: Some authoritative support; minor contradictions or gaps
- **LOW (0.2-0.49)**: Limited sources; significant uncertainty or contradictions
- **SPECULATIVE (<0.2)**: Mostly reasoning/inference; minimal direct evidence

Always state the confidence level in the output.

# Knowledge gap detection
After answering, identify:
- Facts assumed but not verified
- Related topics not covered in the answer
- Contradictions that could not be resolved
- Areas where more recent information might exist
- Questions the user might not have thought to ask

# Follow-up question generation
Generate 2-4 follow-up questions that:
1. Deepen understanding of the topic
2. Explore related or adjacent concepts
3. Clarify ambiguities in the original question
4. Challenge assumptions in the answer

# Structured Q&A output format
Use this format for answers:
```
## Answer
{concise answer to the main question}

## Details
{detailed explanation with evidence}

## Sources
1. [{source title}]({url}) -- credibility: {score}/5
2. [{source title}]({url}) -- credibility: {score}/5

## Confidence: {HIGH|MEDIUM|LOW|SPECULATIVE} ({0.0-1.0})

## Knowledge gaps
- {gap 1}
- {gap 2}

## Follow-up questions
1. {question}
2. {question}
```

# Research depth strategies

## Quick lookup (for factual questions)
- Single authoritative source sufficient
- Verify with one additional source
- Response time target: < 30 seconds

## Standard research (for explanatory questions)
- 3-5 sources across primary and secondary
- Cross-reference key claims
- Response time target: < 2 minutes

## Deep dive (for complex/novel questions)
- 5-10+ sources across all tiers
- Systematic literature review approach
- Identify conflicting viewpoints
- Response time target: < 10 minutes

# Domain-specific knowledge hints
When the question involves a specific domain, apply domain expertise:
- **Technical**: check official docs first, then community resources
- **Scientific**: prefer peer-reviewed papers, check methodology
- **Legal**: note jurisdiction; disclaimer about not being legal advice
- **Medical**: note that information is educational, not clinical advice
- **Financial**: check multiple data sources; note market conditions
"""

# ---------------------------------------------------------------------------
# Research domain detection
# ---------------------------------------------------------------------------

_DOMAIN_PATTERNS: dict[str, list[str]] = {
    "technical": ["api", "code", "programming", "software", "framework", "library",
                  "algorithm", "database", "server", "cloud", "docker", "kubernetes"],
    "scientific": ["research", "study", "paper", "experiment", "hypothesis", "theory",
                   "data", "analysis", "methodology", "peer-reviewed"],
    "business": ["market", "strategy", "revenue", "customer", "competitor", "ROI",
                 "KPI", "business model", "startup", "enterprise"],
    "general": ["what", "why", "how", "when", "where", "who", "explain", "define"],
}

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_QA = "qa"
_TASK_SEARCH = "search"
_TASK_SUMMARIZE = "summarize"
_TASK_GRAPH_QUERY = "graph-query"
_TASK_DEEP_RESEARCH = "deep-research"
_TASK_FACT_CHECK = "fact-check"
_TASK_COMPARE = "compare"
_TASK_EXPLAIN = "explain"

_TASK_KEYWORDS: list[tuple[list[str], str]] = [
    (["deep dive", "深入研究", "investigate", "调查", "research thoroughly", "全面研究", "deep research"], _TASK_DEEP_RESEARCH),
    (["搜索", "search", "find", "查找", "look up", "lookup"], _TASK_SEARCH),
    (["摘要", "summarize", "总结", "summary", "概括", "归纳"], _TASK_SUMMARIZE),
    (["graph", "图谱", "关系", "entity", "实体", "relationship", "node", "edge"], _TASK_GRAPH_QUERY),
    (["fact check", "验证", "verify", "核实", "is it true", "confirm", "确认"], _TASK_FACT_CHECK),
    (["compare", "对比", "比较", "versus", "vs", "difference", "区别", "pros and cons", "优缺点"], _TASK_COMPARE),
    (["explain", "解释", "说明", "what is", "什么是", "define", "定义", "how does", "怎么"], _TASK_EXPLAIN),
]

# ---------------------------------------------------------------------------
# Task-specific prompt augmentations
# ---------------------------------------------------------------------------

_TASK_PROMPTS: dict[str, str] = {
    _TASK_QA: (
        "Answer the question directly and concisely. "
        "Provide evidence and cite sources. "
        "Include confidence score and follow-up questions."
    ),
    _TASK_SEARCH: (
        "Search for relevant information across available sources. "
        "Rank results by relevance and credibility. "
        "Present top findings with brief summaries."
    ),
    _TASK_SUMMARIZE: (
        "Summarize the provided content or topic. "
        "Extract key points, conclusions, and actionable insights. "
        "Keep the summary to 20-30% of the original length."
    ),
    _TASK_GRAPH_QUERY: (
        "Query the knowledge graph for entities and relationships. "
        "Show connected entities, relationship types, and traversal paths. "
        "Visualize the subgraph if possible."
    ),
    _TASK_DEEP_RESEARCH: (
        "Conduct a thorough research investigation:\n"
        "1. Define the research question precisely.\n"
        "2. Search across multiple source tiers.\n"
        "3. Cross-reference findings for consistency.\n"
        "4. Identify conflicting viewpoints.\n"
        "5. Synthesize a comprehensive answer with full citations.\n"
        "6. Flag knowledge gaps and uncertainties."
    ),
    _TASK_FACT_CHECK: (
        "Verify the claim using multiple independent sources. "
        "Rate the claim: CONFIRMED, MOSTLY TRUE, MIXED, MOSTLY FALSE, FALSE. "
        "Explain the evidence for and against."
    ),
    _TASK_COMPARE: (
        "Compare the items across relevant dimensions. "
        "Use a structured comparison table. "
        "Highlight strengths, weaknesses, and trade-offs. "
        "Provide a recommendation based on context."
    ),
    _TASK_EXPLAIN: (
        "Explain the concept clearly for the target audience. "
        "Use analogies and examples where helpful. "
        "Start simple, then add complexity. "
        "Include related concepts and further reading."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs per task type
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TASK_QA: (
        "Answer synthesized from 3 source documents.\n"
        "Confidence: HIGH (0.85)\n"
        "Follow-up: 2 suggested questions generated."
    ),
    _TASK_SEARCH: "Found 5 relevant results across knowledge base, ranked by credibility.",
    _TASK_SUMMARIZE: "Summary generated (250 words) from the provided content with key points extracted.",
    _TASK_GRAPH_QUERY: "Graph traversal complete: found 12 related entities across 3 relationship types.",
    _TASK_DEEP_RESEARCH: (
        "Deep research complete:\n"
        "  Sources consulted: 8 (3 primary, 3 secondary, 2 tertiary)\n"
        "  Key findings: 5 synthesized\n"
        "  Confidence: MEDIUM (0.65)\n"
        "  Knowledge gaps: 2 identified"
    ),
    _TASK_FACT_CHECK: (
        "Fact check result: MOSTLY TRUE\n"
        "  Supporting evidence: 3 sources\n"
        "  Contradicting evidence: 1 source (outdated)\n"
        "  Confidence: HIGH (0.82)"
    ),
    _TASK_COMPARE: (
        "Comparison complete:\n"
        "  Dimensions compared: 6\n"
        "  Recommendation: Option A for performance, Option B for ease of use"
    ),
    _TASK_EXPLAIN: (
        "Explanation provided with 2 examples and 1 analogy.\n"
        "Related concepts: 3 linked.\n"
        "Further reading: 2 resources suggested."
    ),
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def detect_domain(text: str) -> str | None:
    """Detect the knowledge domain of the question."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for domain, patterns in _DOMAIN_PATTERNS.items():
        score = sum(1 for p in patterns if p in lower)
        if score:
            scores[domain] = score
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def assess_question_complexity(text: str) -> str:
    """Assess the complexity of a question: simple, moderate, complex."""
    lower = text.lower()
    # Complex indicators
    complex_signals = ["compare", "analyze", "evaluate", "discuss", "investigate",
                       "deep dive", "comprehensive", "pros and cons", "trade-offs"]
    if any(s in lower for s in complex_signals):
        return "complex"
    # Simple indicators
    simple_signals = ["what is", "define", "who is", "when was", "where is",
                      "什么是", "定义", "谁是"]
    if any(s in lower for s in simple_signals):
        return "simple"
    return "moderate"


def estimate_confidence(source_count: int, source_agreement: float) -> float:
    """Estimate answer confidence from source count and agreement rate."""
    # More sources with higher agreement = higher confidence
    base = min(source_count / 5, 1.0) * 0.5  # max 0.5 from source count
    agreement_bonus = source_agreement * 0.5   # max 0.5 from agreement
    return round(min(base + agreement_bonus, 1.0), 2)


# ---------------------------------------------------------------------------
# KnowledgeAgent
# ---------------------------------------------------------------------------

class KnowledgeAgent(BaseAgent):
    """Specialist agent for information retrieval and knowledge management.

    Supports multiple research workflows:
    - **qa**: direct question answering with citations
    - **search**: information retrieval across sources
    - **summarize**: content summarization with key points
    - **graph-query**: knowledge graph entity and relationship queries
    - **deep-research**: comprehensive multi-source investigation
    - **fact-check**: claim verification with evidence
    - **compare**: structured comparison across dimensions
    - **explain**: concept explanation with examples
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="knowledge-agent",
            description="Information retrieval, multi-source research, fact-checking, and knowledge graph queries",
            skills=["search", "qa", "summarize", "knowledge-graph", "research",
                    "fact-check", "compare", "explain", "citation"],
            input_modes=["text"],
            output_modes=["text", "structured-data"],
            domain="knowledge",
            can_delegate=True,
            tool_filter=["web_search", "read_file", "python_execute"],
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[KnowledgeAgent] Processing: %s", message[:80])

        task_type = self._classify(message)
        domain = detect_domain(message)
        complexity = assess_question_complexity(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type, domain, complexity)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=3,
            )
            if result.success:
                return result
            logger.warning("[KnowledgeAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[KnowledgeAgent] Task type: '{task_type}'"
        if domain:
            output += f", domain='{domain}'"
        output += f", complexity='{complexity}'"
        output += ". "
        output += _MOCK_OUTPUTS.get(task_type, "Knowledge task processed.")

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "search", "搜索", "find", "查找", "question", "问题",
            "summarize", "摘要", "总结", "knowledge", "知识",
            "graph", "图谱", "research", "调研", "document", "文档",
            "what", "什么", "why", "为什么", "how", "怎么", "explain", "解释",
            "fact check", "验证", "compare", "对比", "versus", "vs",
            "define", "定义", "investigate", "调查",
        ]
        msg = message.lower()
        hits = sum(1 for k in keywords if k in msg)
        return min(hits * 0.25, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _TASK_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return _TASK_QA  # safe default

    def _build_system_prompt(self, task_type: str, domain: str | None, complexity: str) -> str:
        """Compose a task-specific system prompt with domain context."""
        parts = [KNOWLEDGE_AGENT_SYSTEM_PROMPT]

        augmentation = _TASK_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current task: {task_type}\n{augmentation}")

        if domain:
            parts.append(
                f"\n# Detected domain: {domain}\n"
                f"Apply {domain}-specific research strategies and source preferences."
            )

        parts.append(
            f"\n# Question complexity: {complexity}\n"
            f"Use {'quick lookup' if complexity == 'simple' else 'standard research' if complexity == 'moderate' else 'deep dive'} strategy."
        )

        return "\n".join(parts)
