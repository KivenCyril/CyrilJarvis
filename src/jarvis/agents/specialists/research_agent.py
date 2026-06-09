from __future__ import annotations

import logging
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive research specialist
# ---------------------------------------------------------------------------

RESEARCH_AGENT_SYSTEM_PROMPT = """\
You are a deep research specialist within the JARVIS assistant system.

# Capabilities
- Multi-source research and information synthesis
- Technology and product comparison reports
- Market analysis and competitive landscape assessment
- Literature review and academic research
- Fact checking and claim verification
- Source credibility assessment and bias detection

You have access to tools: web_search, read_file, python_execute, write_file.
Be thorough: gather information from multiple sources, cross-reference findings,
and present balanced, well-structured analyses. Always cite sources.

# Multi-Source Research Workflow

## Phase 1: Scoping
1. Define the research question precisely.
2. Identify the type of research (comparison, market, literature, fact-check).
3. Determine scope boundaries -- what's in and out of scope.
4. List key terms and synonyms for comprehensive searching.

## Phase 2: Collection
1. Search across multiple source types:
   - Academic (papers, preprints, conference proceedings)
   - Industry (reports, whitepapers, case studies)
   - Technical (documentation, changelogs, benchmarks)
   - Community (forums, discussions, expert opinions)
   - News (articles, press releases, announcements)
2. Collect at least 3-5 sources per claim.
3. Record source metadata: author, date, publisher, URL.

## Phase 3: Assessment
1. Evaluate source credibility (see checklist below).
2. Identify consensus and disagreements across sources.
3. Flag potential biases and conflicts of interest.
4. Note information gaps and limitations.

## Phase 4: Synthesis
1. Integrate findings into a coherent narrative.
2. Use structured output format (see below).
3. Distinguish facts from interpretations.
4. Provide confidence levels for key claims.

## Phase 5: Review
1. Cross-check key facts against primary sources.
2. Verify numerical data and statistics.
3. Ensure balanced representation of viewpoints.
4. Proofread for logical consistency.

# Source Credibility Assessment

Rate each source on these dimensions (1-5 scale):

| Dimension        | 1 (Low)                    | 5 (High)                      |
|------------------|----------------------------|-------------------------------|
| Authority        | Unknown author              | Recognized domain expert      |
| Currency         | >5 years old               | Published within last year    |
| Objectivity      | Clear commercial bias      | Peer-reviewed, neutral        |
| Accuracy         | No citations, anecdotal    | Data-driven, well-sourced     |
| Coverage         | Single perspective         | Comprehensive analysis        |

Flag sources scoring < 3 on any dimension.
Discard sources scoring < 2 on Authority or Accuracy.

# Structured Research Output Format

## For all research types, use this structure:

### Executive Summary (2-3 sentences)
Key findings and recommendation in brief.

### Background
Context needed to understand the research question.

### Methodology
How the research was conducted, what sources were consulted.

### Findings
Organized by theme or criterion. Use tables for comparisons.
Each finding should note:
- The claim
- Supporting evidence (with citations)
- Confidence level: HIGH / MEDIUM / LOW
- Caveats or limitations

### Analysis
Interpretation of findings. Patterns, implications, trade-offs.

### Conclusions
Actionable takeaways and recommendations.

### Sources
Numbered reference list with full citations.

# Comparative Analysis Template

When comparing options (technologies, products, approaches):

| Criterion       | Option A | Option B | Option C | Weight |
|-----------------|----------|----------|----------|--------|
| Performance     | ...      | ...      | ...      | 25%    |
| Cost            | ...      | ...      | ...      | 20%    |
| Ease of use     | ...      | ...      | ...      | 20%    |
| Community       | ...      | ...      | ...      | 15%    |
| Maturity        | ...      | ...      | ...      | 10%    |
| Documentation   | ...      | ...      | ...      | 10%    |

Score each cell 1-5, compute weighted score, provide clear winner and rationale.

# Fact-Checking Workflow
1. Identify the specific claim to verify.
2. Determine the claim type (statistical, historical, scientific, policy).
3. Find 3+ independent authoritative sources.
4. Check for:
   - Context stripping (true statement taken out of context)
   - Cherry-picking (selective data presentation)
   - Outdated information (was true, no longer is)
   - Logical fallacies (correlation != causation)
5. Rate the claim: CONFIRMED / MOSTLY TRUE / MIXED / MOSTLY FALSE / FALSE / UNVERIFIABLE.
6. Provide the nuanced truth with proper context.

# Citation Format
Use numbered inline citations [1], [2], etc.
In the Sources section, provide:
  [N] Author(s). "Title." Publisher/Journal, Date. URL (if available).
"""

# ---------------------------------------------------------------------------
# Research type definitions
# ---------------------------------------------------------------------------

_TYPE_COMPARISON = "comparison"
_TYPE_MARKET = "market"
_TYPE_LITERATURE = "literature"
_TYPE_FACT_CHECK = "fact-check"
_TYPE_TECHNOLOGY = "technology"
_TYPE_GENERAL = "research"

_TYPE_KEYWORDS: list[tuple[list[str], str]] = [
    (["compare", "比较", "vs", "versus", "对比", "difference", "区别", "pros and cons", "优缺点"], _TYPE_COMPARISON),
    (
        ["market", "市场", "competitive", "竞争", "industry", "行业", "trend", "趋势",
         "landscape", "格局", "share", "份额", "growth", "增长"],
        _TYPE_MARKET,
    ),
    (
        ["literature", "文献", "paper", "论文", "academic", "学术", "journal", "期刊",
         "preprint", "arxiv", "survey", "综述", "meta-analysis", "systematic review"],
        _TYPE_LITERATURE,
    ),
    (
        ["fact", "事实", "verify", "验证", "check", "核实", "claim", "true",
         "false", "debunk", "myth", "谣言"],
        _TYPE_FACT_CHECK,
    ),
    (
        ["technology", "技术", "framework", "框架", "library", "库", "tool", "工具",
         "stack", "architecture", "架构", "benchmark", "基准"],
        _TYPE_TECHNOLOGY,
    ),
]

# ---------------------------------------------------------------------------
# Strategy-specific prompt augmentations
# ---------------------------------------------------------------------------

_TYPE_PROMPTS: dict[str, str] = {
    _TYPE_COMPARISON: (
        "Perform a comparative analysis:\n"
        "1. Identify all options to compare.\n"
        "2. Define evaluation criteria with weights.\n"
        "3. Research each option against each criterion.\n"
        "4. Fill in the comparison table with scores (1-5) and evidence.\n"
        "5. Compute weighted scores.\n"
        "6. Provide a clear recommendation with rationale."
    ),
    _TYPE_MARKET: (
        "Conduct market analysis:\n"
        "1. Define the market segment and geography.\n"
        "2. Identify key players and their market positions.\n"
        "3. Analyze trends (growth rate, adoption, disruption).\n"
        "4. Assess competitive dynamics (Porter's Five Forces if applicable).\n"
        "5. Identify opportunities and threats.\n"
        "6. Provide market size estimates with confidence ranges."
    ),
    _TYPE_LITERATURE: (
        "Conduct a literature review:\n"
        "1. Define inclusion/exclusion criteria for sources.\n"
        "2. Search across academic databases and preprint servers.\n"
        "3. Screen and select relevant papers.\n"
        "4. Extract key findings from each paper.\n"
        "5. Synthesize findings into themes.\n"
        "6. Identify research gaps and future directions."
    ),
    _TYPE_FACT_CHECK: (
        "Perform fact-checking:\n"
        "1. State the exact claim being checked.\n"
        "2. Identify the claim type.\n"
        "3. Find 3+ independent authoritative sources.\n"
        "4. Check for context stripping, cherry-picking, outdated info.\n"
        "5. Rate: CONFIRMED / MOSTLY TRUE / MIXED / MOSTLY FALSE / FALSE.\n"
        "6. Provide the nuanced truth with full context."
    ),
    _TYPE_TECHNOLOGY: (
        "Conduct technology research:\n"
        "1. Identify the technology landscape.\n"
        "2. Evaluate maturity and adoption (Gartner Hype Cycle position).\n"
        "3. Assess technical capabilities and limitations.\n"
        "4. Review community health (contributors, activity, issues).\n"
        "5. Analyze learning curve and documentation quality.\n"
        "6. Consider long-term viability and vendor/community lock-in."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TYPE_COMPARISON: (
        "Comparison report generated:\n"
        "- 5 criteria evaluated across 3 options.\n"
        "- Option B leads with weighted score 4.2/5.0.\n"
        "- Key differentiator: performance (2x faster) and community size.\n"
        "- Sources: 8 references from official docs, benchmarks, and industry reports."
    ),
    _TYPE_MARKET: (
        "Market analysis complete:\n"
        "- Market size: $12.4B (2024), projected $28.1B by 2028 (CAGR 22.7%).\n"
        "- 4 key players identified: A (35% share), B (25%), C (20%), Others (20%).\n"
        "- Key trend: shift from on-premise to cloud-native solutions.\n"
        "- Sources: 6 industry reports and analyst briefings."
    ),
    _TYPE_LITERATURE: (
        "Literature review complete:\n"
        "- 12 relevant papers identified (2020-2024).\n"
        "- 3 major themes: scalability, security, developer experience.\n"
        "- Consensus: hybrid approaches outperform pure solutions.\n"
        "- Research gap: limited real-world benchmarks at scale."
    ),
    _TYPE_FACT_CHECK: (
        "Fact check complete:\n"
        "- Claim: MOSTLY TRUE with caveats.\n"
        "- Verified against 3 authoritative sources.\n"
        "- The claim is accurate for the specific context (US, 2023 data).\n"
        "- Caveat: does not apply to international markets."
    ),
    _TYPE_TECHNOLOGY: (
        "Technology research complete:\n"
        "- Maturity: Early mainstream (past hype peak).\n"
        "- Community: 15K+ GitHub stars, 200+ contributors, active releases.\n"
        "- Strengths: performance, type safety, developer tooling.\n"
        "- Weaknesses: steep learning curve, smaller ecosystem."
    ),
    _TYPE_GENERAL: (
        "Research complete:\n"
        "- Findings synthesized from 5+ sources.\n"
        "- Key insight: the approach is viable with specific trade-offs.\n"
        "- Confidence: MEDIUM (limited data available).\n"
        "- Recommendation: proceed with a pilot, gather empirical data."
    ),
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def assess_source_credibility(
    authority: int,
    currency: int,
    objectivity: int,
    accuracy: int,
    coverage: int,
) -> dict[str, Any]:
    """Assess the credibility of a source based on five dimensions (1-5 scale).

    Returns a dict with overall_score, rating, and any flags.
    """
    scores = {
        "authority": authority,
        "currency": currency,
        "objectivity": objectivity,
        "accuracy": accuracy,
        "coverage": coverage,
    }
    overall = sum(scores.values()) / len(scores)
    flags: list[str] = []
    for dim, val in scores.items():
        if val < 3:
            flags.append(f"Low {dim} ({val}/5)")
    discard = authority < 2 or accuracy < 2

    if overall >= 4.0:
        rating = "HIGH"
    elif overall >= 3.0:
        rating = "MEDIUM"
    else:
        rating = "LOW"

    return {
        "scores": scores,
        "overall_score": round(overall, 1),
        "rating": rating,
        "flags": flags,
        "recommend_discard": discard,
    }


def format_citation(
    index: int,
    authors: str,
    title: str,
    publisher: str = "",
    date: str = "",
    url: str = "",
) -> str:
    """Format a single citation in the standard reference format."""
    parts = [f"[{index}] {authors}. \"{title}.\""]
    if publisher:
        parts.append(f" {publisher},")
    if date:
        parts.append(f" {date}.")
    if url:
        parts.append(f" {url}")
    return "".join(parts)


def build_comparison_table(
    criteria: list[str],
    options: list[str],
    scores: dict[str, dict[str, float]],
    weights: dict[str, float] | None = None,
) -> str:
    """Build a markdown comparison table.

    *scores* is keyed by option name, then by criterion name.
    *weights* is keyed by criterion name (default: equal weights).
    """
    if weights is None:
        w = 1.0 / len(criteria) if criteria else 1.0
        weights = {c: w for c in criteria}

    # Header
    header = "| Criterion | " + " | ".join(options) + " | Weight |"
    separator = "|" + "---|" * (len(options) + 2)
    rows = [header, separator]

    # Data rows
    weighted_totals: dict[str, float] = {opt: 0.0 for opt in options}
    for criterion in criteria:
        row_parts = [f"| {criterion}"]
        for opt in options:
            val = scores.get(opt, {}).get(criterion, 0.0)
            row_parts.append(f" {val:.1f}")
            weighted_totals[opt] += val * weights.get(criterion, 0.0)
        row_parts.append(f" {weights.get(criterion, 0.0):.0%}")
        rows.append(" | ".join(row_parts) + " |")

    # Total row
    total_parts = ["| **Weighted Total**"]
    for opt in options:
        total_parts.append(f" **{weighted_totals[opt]:.2f}**")
    total_parts.append(" -- |")
    rows.append(" | ".join(total_parts))

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# ResearchAgent
# ---------------------------------------------------------------------------

class ResearchAgent(BaseAgent):
    """Specialist agent for deep research and analysis tasks.

    Supports multiple research workflows:
    - **comparison**: structured comparative analysis with weighted scoring
    - **market**: market sizing, competitive landscape, trend analysis
    - **literature**: academic literature review with synthesis
    - **fact-check**: claim verification against authoritative sources
    - **technology**: tech landscape, maturity, community assessment
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="research-agent",
            description="Deep research, comparison reports, market analysis, and fact checking",
            skills=["deep-research", "comparison", "market-analysis", "literature-review", "fact-checking"],
            input_modes=["text"],
            output_modes=["text", "structured-data"],
            domain="research",
            can_delegate=True,
            tool_filter=["web_search", "read_file", "python_execute"],
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[ResearchAgent] Processing: %s", message[:80])

        task_type = self._classify(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=3,
            )
            if result.success:
                return result
            logger.warning("[ResearchAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[ResearchAgent] Task type: '{task_type}'. "
        output += _MOCK_OUTPUTS.get(task_type, _MOCK_OUTPUTS[_TYPE_GENERAL])

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "research", "调研", "investigate", "调查", "compare", "比较",
            "analysis", "分析", "market", "市场", "literature", "文献",
            "fact check", "核实", "deep dive", "深入", "survey", "综述",
            "trend", "趋势", "competitive", "竞争", "benchmark", "对标",
            "evaluate", "评估", "pros and cons", "优缺点",
            "technology", "framework", "landscape",
        ]
        msg = message.lower()
        hits = sum(1 for k in keywords if k in msg)
        return min(hits * 0.25, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _TYPE_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return _TYPE_GENERAL

    def _build_system_prompt(self, task_type: str) -> str:
        """Compose a task-specific system prompt."""
        parts = [RESEARCH_AGENT_SYSTEM_PROMPT]

        augmentation = _TYPE_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current research task: {task_type}\n{augmentation}")

        return "\n".join(parts)
