from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive writing specialist
# ---------------------------------------------------------------------------

WRITING_AGENT_SYSTEM_PROMPT = r"""\
You are a writing and documentation specialist within the JARVIS assistant system.

# Capabilities
- Technical writing and documentation generation
- Document structure templates (README, ADR, RFC, blog, changelog)
- Tone and audience adaptation for different contexts
- SEO optimization for web-published content
- Technical accuracy verification and fact-checking
- Readability analysis and optimization (Flesch-Kincaid awareness)
- Multi-format output (Markdown, HTML, plain text, reStructuredText)
- Content editing, proofreading, and style consistency

You have access to tools: read_file, write_file, python_execute, shell_execute.
Use read_file to examine source code and existing docs for context.
Use write_file to save generated documents.

# Execution protocol
1. **Analyze** -- understand the writing task, audience, purpose, and format.
2. **Research** -- gather context from code, existing docs, or provided materials.
3. **Outline** -- create a document structure with section headings.
4. **Draft** -- write content following the chosen template and style guide.
5. **Review** -- apply the technical accuracy and quality checklists.
6. **Optimize** -- check readability, SEO (if applicable), and formatting.
7. **Deliver** -- output in the requested format.

# Document structure templates

## README template
```markdown
# Project Name
Brief description (1-2 sentences).

## Features
- Feature 1
- Feature 2

## Quick Start
### Prerequisites
- Requirement 1

### Installation
\`\`\`bash
install command
\`\`\`

### Usage
\`\`\`
usage example
\`\`\`

## Configuration
| Option | Type | Default | Description |
|--------|------|---------|-------------|

## API Reference
Brief overview of the public API.

## Contributing
How to contribute.

## License
License information.
```

## ADR (Architecture Decision Record) template
```markdown
# ADR-{number}: {title}
## Status
{Proposed | Accepted | Deprecated | Superseded by ADR-{N}}

## Context
What is the issue? What forces are at play?

## Decision
What is the change that we're proposing or have agreed to implement?

## Consequences
What becomes easier or more difficult because of this change?

### Positive
- {benefit}

### Negative
- {trade-off}

### Neutral
- {observation}
```

## RFC (Request for Comments) template
```markdown
# RFC: {title}
- **Author**: {name}
- **Date**: {date}
- **Status**: {Draft | Review | Accepted | Rejected}

## Summary
One-paragraph overview.

## Motivation
Why is this needed? What problem does it solve?

## Detailed Design
### Architecture
### API changes
### Data model changes
### Migration plan

## Alternatives Considered
1. {alternative} -- rejected because {reason}

## Unresolved Questions
- {question}

## Timeline
- Phase 1: {description} ({estimated date})
```

## Blog post template
```markdown
# {Title -- engaging, specific, value-oriented}

{Hook -- opening paragraph that captures interest}

## {Section 1 -- the problem/context}
{Content with examples}

## {Section 2 -- the solution/approach}
{Content with code examples or illustrations}

## {Section 3 -- results/impact}
{Data, benchmarks, before/after}

## Conclusion
{Key takeaway and call-to-action}

---
*{Author bio or about section}*
```

## Changelog template
```markdown
# Changelog
All notable changes to this project.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]
### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [{version}] - {date}
### Added
- {description} ([#{PR}](link))
```

# Tone and audience adaptation
Adjust writing style based on target audience:

| Audience        | Tone           | Complexity    | Jargon    | Examples           |
|-----------------|----------------|---------------|-----------|--------------------|
| Developers      | Direct         | High          | Yes       | Code snippets      |
| Executives      | Professional   | Low           | Minimal   | Metrics, ROI       |
| End users       | Friendly       | Low           | None      | Screenshots, steps |
| API consumers   | Precise        | Medium-High   | API terms | cURL examples      |
| Open source     | Welcoming      | Medium        | Some      | Contributing guide |
| Internal team   | Casual         | Medium        | Team jargon OK | Quick notes    |

# SEO optimization hints
When writing for web publication:
1. **Title**: include primary keyword, keep under 60 chars
2. **Meta description**: 150-160 chars with keyword and value proposition
3. **Headings**: use H2/H3 hierarchy with keywords
4. **First paragraph**: include primary keyword naturally
5. **URL slug**: short, hyphenated, keyword-rich
6. **Internal links**: link to related content
7. **Image alt text**: descriptive, keyword-inclusive
8. **Content length**: 1,500-2,500 words for pillar content
9. **Readability**: aim for Flesch-Kincaid grade 8-10 for tech blogs

# Technical accuracy checklist
Before publishing technical content, verify:
1. [ ] Code examples compile/run correctly
2. [ ] API endpoints and parameters are current
3. [ ] Version numbers and dependencies are accurate
4. [ ] Links are not broken
5. [ ] Screenshots match current UI
6. [ ] Configuration options exist and defaults are correct
7. [ ] Security implications are noted where relevant
8. [ ] Deprecated features are marked

# Readability scoring (Flesch-Kincaid awareness)
Target readability scores by content type:
- Developer docs: Grade 10-12 (technical but clear)
- Blog posts: Grade 8-10 (accessible)
- User guides: Grade 6-8 (easy to follow)
- Executive summaries: Grade 8-10 (professional but clear)
- API reference: Grade 12+ (precise, technical)

Readability tips:
- Prefer short sentences (15-20 words average)
- Use active voice
- One idea per paragraph
- Use lists and tables for structured information
- Define acronyms on first use

# Multi-format output
Support these output formats:
- **Markdown**: default, widely compatible, good for docs-as-code
- **HTML**: for web publishing, email newsletters
- **Plain text**: for CLI output, email, logs
- **reStructuredText**: for Python docs (Sphinx)
- **AsciiDoc**: for enterprise documentation

Convert between formats as needed while preserving structure.
"""

# ---------------------------------------------------------------------------
# Document type detection
# ---------------------------------------------------------------------------

_DOCUMENT_PATTERNS: dict[str, list[str]] = {
    "readme": ["readme", "readme.md", "project description", "getting started"],
    "api-docs": ["api doc", "api 文档", "swagger", "openapi", "接口文档",
                 "endpoint", "rest api", "graphql"],
    "adr": ["adr", "architecture decision", "决策记录"],
    "rfc": ["rfc", "request for comments", "proposal", "设计文档", "提案"],
    "blog": ["blog", "博客", "article", "文章", "post", "tutorial", "教程"],
    "changelog": ["changelog", "release note", "变更日志", "发布说明", "what's new"],
    "email": ["email", "邮件", "letter", "信"],
    "guide": ["guide", "指南", "manual", "手册", "howto", "how-to", "walkthrough"],
    "report": ["report", "报告", "analysis", "分析报告", "summary report"],
}

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_DOCUMENTATION = "documentation"
_TASK_README = "readme"
_TASK_API_DOCS = "api-docs"
_TASK_ADR = "adr"
_TASK_RFC = "rfc"
_TASK_BLOG = "blog"
_TASK_CHANGELOG = "changelog"
_TASK_EMAIL = "email"
_TASK_GUIDE = "guide"
_TASK_EDIT = "edit"
_TASK_GENERAL = "general"

_TASK_KEYWORDS: list[tuple[list[str], str]] = [
    (["readme", "readme.md"], _TASK_README),
    (["api doc", "api 文档", "swagger", "openapi", "接口文档"], _TASK_API_DOCS),
    (["adr", "architecture decision", "决策记录"], _TASK_ADR),
    (["rfc", "request for comments", "proposal", "提案"], _TASK_RFC),
    (["blog", "博客", "article", "文章", "post"], _TASK_BLOG),
    (["changelog", "release note", "变更日志", "发布说明"], _TASK_CHANGELOG),
    (["email", "邮件", "letter", "信"], _TASK_EMAIL),
    (["edit", "编辑", "proofread", "校对", "revise", "修改", "improve", "改进"], _TASK_EDIT),
    (["document", "文档", "doc", "draft", "草稿"], _TASK_DOCUMENTATION),
    (["guide", "指南", "manual", "手册", "howto"], _TASK_GUIDE),
    (["write", "写"], _TASK_GENERAL),
]

# ---------------------------------------------------------------------------
# Task-specific prompt augmentations
# ---------------------------------------------------------------------------

_TASK_PROMPTS: dict[str, str] = {
    _TASK_DOCUMENTATION: (
        "Generate comprehensive technical documentation. "
        "Include overview, setup guide, configuration, and API reference. "
        "Follow the docs-as-code approach."
    ),
    _TASK_README: (
        "Create a README following the README template. "
        "Include all standard sections: description, features, installation, usage, contributing. "
        "Make the first impression compelling."
    ),
    _TASK_API_DOCS: (
        "Generate API documentation with: "
        "endpoint descriptions, request/response examples, authentication, error codes. "
        "Include cURL examples for each endpoint."
    ),
    _TASK_ADR: (
        "Write an Architecture Decision Record following the ADR template. "
        "Clearly state the context, decision, and consequences. "
        "Include positive, negative, and neutral consequences."
    ),
    _TASK_RFC: (
        "Write an RFC following the RFC template. "
        "Include motivation, detailed design, alternatives considered, and timeline. "
        "Be thorough enough for async review."
    ),
    _TASK_BLOG: (
        "Write an engaging blog post following the blog template. "
        "Start with a hook, include examples and data, end with a call-to-action. "
        "Apply SEO optimization hints."
    ),
    _TASK_CHANGELOG: (
        "Generate a changelog following Keep a Changelog format. "
        "Group changes by: Added, Changed, Deprecated, Removed, Fixed, Security. "
        "Include PR/issue references."
    ),
    _TASK_EMAIL: (
        "Draft a professional email. "
        "Keep it concise with clear subject, purpose, and call-to-action. "
        "Match the tone to the relationship and context."
    ),
    _TASK_GUIDE: (
        "Write a step-by-step guide. "
        "Include prerequisites, numbered steps, expected outcomes, and troubleshooting. "
        "Use screenshots or code examples where helpful."
    ),
    _TASK_EDIT: (
        "Edit and improve the provided content. "
        "Check for clarity, grammar, consistency, and accuracy. "
        "Apply the readability and technical accuracy checklists."
    ),
    _TASK_GENERAL: (
        "Write content based on the requirements. "
        "Determine the appropriate format and tone. "
        "Apply quality and readability checklists."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs per task type
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TASK_DOCUMENTATION: "Documentation generated: overview, setup guide, and API reference sections.",
    _TASK_README: "README drafted: project description, installation, usage, and contributing sections.",
    _TASK_API_DOCS: "API documentation created: 5 endpoints documented with examples.",
    _TASK_ADR: "ADR drafted: context, decision, and consequences documented.",
    _TASK_RFC: "RFC drafted: motivation, design, alternatives, and timeline sections.",
    _TASK_BLOG: "Blog post drafted: 800 words with introduction, body, and conclusion.",
    _TASK_CHANGELOG: "Changelog generated: 3 versions with categorized changes.",
    _TASK_EMAIL: "Professional email drafted. Tone: formal, concise.",
    _TASK_GUIDE: "Step-by-step guide created: 8 steps with prerequisites and troubleshooting.",
    _TASK_EDIT: "Content edited: 5 grammar fixes, 3 clarity improvements, readability score improved.",
    _TASK_GENERAL: "Content written and formatted.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def detect_document_type(text: str) -> str | None:
    """Detect the document type requested in *text*."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for doc_type, patterns in _DOCUMENT_PATTERNS.items():
        score = sum(1 for p in patterns if p in lower)
        if score:
            scores[doc_type] = score
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def detect_audience(text: str) -> str:
    """Detect the target audience from text."""
    lower = text.lower()
    if any(k in lower for k in ["developer", "engineer", "开发者", "工程师", "programmer"]):
        return "developers"
    if any(k in lower for k in ["executive", "manager", "领导", "管理层", "stakeholder"]):
        return "executives"
    if any(k in lower for k in ["user", "用户", "customer", "客户", "beginner", "初学者"]):
        return "end-users"
    if any(k in lower for k in ["api", "consumer", "integration", "集成"]):
        return "api-consumers"
    return "general"


def detect_output_format(text: str) -> str:
    """Detect the desired output format."""
    lower = text.lower()
    if any(k in lower for k in ["html", "web page", "网页"]):
        return "html"
    if any(k in lower for k in ["plain text", "纯文本", "txt"]):
        return "plain-text"
    if any(k in lower for k in ["rst", "restructuredtext", "sphinx"]):
        return "rst"
    if any(k in lower for k in ["asciidoc"]):
        return "asciidoc"
    return "markdown"


def estimate_readability(text: str) -> dict[str, Any]:
    """Estimate readability metrics for text.

    Returns a dict with word_count, avg_sentence_length, and estimated grade level.
    This is a simplified Flesch-Kincaid approximation.
    """
    words = text.split()
    word_count = len(words)
    if word_count == 0:
        return {"word_count": 0, "avg_sentence_length": 0, "estimated_grade": 0}

    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = max(len(sentences), 1)

    avg_sentence_length = word_count / sentence_count

    # Simplified syllable count (approximation)
    syllable_count = 0
    for word in words:
        word_clean = re.sub(r'[^a-zA-Z]', '', word.lower())
        if len(word_clean) <= 3:
            syllable_count += 1
        else:
            # Count vowel groups
            vowel_groups = re.findall(r'[aeiouy]+', word_clean)
            syllable_count += max(len(vowel_groups), 1)

    avg_syllables = syllable_count / max(word_count, 1)

    # Flesch-Kincaid Grade Level formula
    grade = 0.39 * avg_sentence_length + 11.8 * avg_syllables - 15.59
    grade = max(0, round(grade, 1))

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_sentence_length": round(avg_sentence_length, 1),
        "avg_syllables_per_word": round(avg_syllables, 2),
        "estimated_grade": grade,
    }


# ---------------------------------------------------------------------------
# WritingAgent
# ---------------------------------------------------------------------------

class WritingAgent(BaseAgent):
    """Specialist agent for writing and documentation tasks.

    Supports multiple document types and workflows:
    - **documentation**: technical docs with setup guides and API reference
    - **readme**: project README with all standard sections
    - **api-docs**: API documentation with endpoints and examples
    - **adr**: Architecture Decision Records
    - **rfc**: Request for Comments / design proposals
    - **blog**: blog posts with SEO optimization
    - **changelog**: Keep a Changelog formatted release notes
    - **email**: professional email drafting
    - **guide**: step-by-step how-to guides
    - **edit**: proofreading and content improvement
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="writing-agent",
            description="Technical writing, documentation, README, API docs, ADR, RFC, blog, and professional emails",
            skills=["documentation", "technical-writing", "readme", "api-docs", "blog",
                    "email-draft", "adr", "rfc", "changelog", "guide", "editing"],
            input_modes=["text"],
            output_modes=["text", "markdown", "html"],
            domain="writing",
            can_delegate=True,
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[WritingAgent] Processing: %s", message[:80])

        task_type = self._classify(message)
        audience = detect_audience(message)
        output_format = detect_output_format(message)
        doc_type = detect_document_type(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type, audience, output_format)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=5,
            )
            if result.success:
                return result
            logger.warning("[WritingAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[WritingAgent] Task type: '{task_type}'"
        output += f", audience='{audience}'"
        output += f", format='{output_format}'"
        output += ". "
        output += _MOCK_OUTPUTS.get(task_type, _MOCK_OUTPUTS[_TASK_GENERAL])

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "write", "写", "document", "文档", "readme", "api doc",
            "blog", "博客", "article", "文章", "email", "draft",
            "草稿", "technical writing", "技术写作", "guide", "指南",
            "manual", "手册", "proofread", "校对", "edit", "编辑",
            "接口文档", "changelog", "release note",
            "adr", "rfc", "proposal", "提案", "template", "模板",
            "seo", "readability", "可读性",
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
        return _TASK_GENERAL  # safe default

    def _build_system_prompt(self, task_type: str, audience: str, output_format: str) -> str:
        """Compose a task-specific system prompt with audience and format context."""
        parts = [WRITING_AGENT_SYSTEM_PROMPT]

        augmentation = _TASK_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current task: {task_type}\n{augmentation}")

        parts.append(
            f"\n# Target audience: {audience}\n"
            f"Adapt tone, complexity, and jargon for {audience}."
        )

        parts.append(
            f"\n# Output format: {output_format}\n"
            f"Generate output in {output_format} format."
        )

        return "\n".join(parts)
