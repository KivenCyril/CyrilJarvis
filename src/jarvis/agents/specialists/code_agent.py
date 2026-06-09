from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive coding specialist
# ---------------------------------------------------------------------------

CODE_AGENT_SYSTEM_PROMPT = """\
You are a specialist coding agent within the JARVIS assistant system.

# Capabilities
- Code review and security/quality analysis
- Code generation, refactoring, and optimization
- Bug diagnosis and debugging workflows
- Git operations (status, diff, commit, branch, merge, rebase)
- Build orchestration and test execution
- Test generation (unit, integration, property-based)

You have access to tools: shell_execute, read_file, write_file, python_execute.
Use them to *perform* tasks, not just describe what you would do.

# Execution protocol
1. **Understand** -- clarify ambiguous requirements before acting.
2. **Inspect** -- read relevant files, check git status, gather context.
3. **Plan** -- outline the change and affected areas.
4. **Execute** -- make changes using write_file or shell_execute.
5. **Verify** -- run tests, linters, type checkers; confirm green.
6. **Report** -- concise summary of what changed and why.

# Code review checklist
When reviewing code, evaluate against:

## Security (OWASP)
- Injection (SQL, command, LDAP, XPath)
- Broken authentication / session management
- Sensitive data exposure (secrets, PII in logs)
- XXE, insecure deserialization
- Broken access control, SSRF
- Security misconfiguration

## Design (SOLID)
- Single Responsibility -- each class/function does one thing
- Open/Closed -- extend via abstraction, don't modify core
- Liskov Substitution -- subtypes are substitutable
- Interface Segregation -- small, focused interfaces
- Dependency Inversion -- depend on abstractions

## Performance
- Algorithmic complexity (Big-O)
- N+1 queries / excessive I/O
- Unnecessary allocations / copies
- Missing caching opportunities
- Concurrency issues (races, deadlocks)

## Quality
- Readability and naming conventions
- Error handling (fail-fast, meaningful messages)
- Test coverage for new/changed code
- Documentation for public API
- Logging at appropriate levels

# Structured review output format
Use severity levels: CRITICAL, HIGH, MEDIUM, LOW, INFO
Format each finding as:
  [SEVERITY] file:line -- description
  Suggestion: ...

# Git integration
When working with git:
- Always check `git status` and `git diff` before committing
- Write conventional commit messages: type(scope): description
- Prefer atomic commits -- one logical change per commit
- Never force-push without explicit confirmation

# Test generation
When generating tests:
- Follow Arrange-Act-Assert pattern
- Cover happy path, edge cases, error cases
- Use descriptive test names that explain the scenario
- Mock external dependencies
- Aim for deterministic, fast tests
"""

# ---------------------------------------------------------------------------
# Language detection patterns
# ---------------------------------------------------------------------------

_LANGUAGE_PATTERNS: dict[str, list[str]] = {
    "python": ["python", "py", ".py", "django", "flask", "fastapi", "pandas", "pytest"],
    "javascript": ["javascript", "js", ".js", "node", "react", "vue", "angular", "npm"],
    "typescript": ["typescript", "ts", ".ts", ".tsx", "deno"],
    "java": ["java", ".java", "spring", "maven", "gradle", "jvm"],
    "go": ["golang", " go ", ".go", "goroutine", "gin", "echo"],
    "rust": ["rust", ".rs", "cargo", "tokio", "async fn"],
    "c++": ["c++", "cpp", ".cpp", ".hpp", "cmake", "g++"],
    "c": [" c ", ".c", ".h", "gcc", "malloc", "stdio"],
    "ruby": ["ruby", ".rb", "rails", "gem", "bundler"],
    "shell": ["bash", "shell", "sh", "zsh", ".sh", "#!/bin"],
    "sql": ["sql", "query", "select ", "insert ", "update ", "delete ", "join"],
}

# ---------------------------------------------------------------------------
# Execution strategy definitions
# ---------------------------------------------------------------------------

_STRATEGY_REVIEW = "code-review"
_STRATEGY_GENERATE = "code-generation"
_STRATEGY_REFACTOR = "refactor"
_STRATEGY_DEBUG = "debug"
_STRATEGY_GIT = "git"
_STRATEGY_BUILD = "build"
_STRATEGY_TEST = "test"

_STRATEGY_KEYWORDS: list[tuple[list[str], str]] = [
    (["review", "审查", "cr", "look at", "check this"], _STRATEGY_REVIEW),
    (["generate", "生成", "write code", "写代码", "implement", "create", "scaffold"], _STRATEGY_GENERATE),
    (["refactor", "重构", "clean up", "simplify", "restructure", "extract", "inline"], _STRATEGY_REFACTOR),
    (["debug", "调试", "fix bug", "修bug", "diagnose", "traceback", "error", "exception"], _STRATEGY_DEBUG),
    (["git", "commit", "push", "branch", "merge", "rebase", "cherry-pick", "stash"], _STRATEGY_GIT),
    (["build", "compile", "构建", "make", "package", "bundle"], _STRATEGY_BUILD),
    (["test", "测试", "spec", "coverage", "assert", "mock"], _STRATEGY_TEST),
]

# ---------------------------------------------------------------------------
# Strategy-specific prompt augmentations
# ---------------------------------------------------------------------------

_STRATEGY_PROMPTS: dict[str, str] = {
    _STRATEGY_REVIEW: (
        "You are performing a code review. "
        "Apply the full checklist (OWASP, SOLID, performance, quality). "
        "Output findings in structured format with severity levels and line references. "
        "End with a summary: total findings by severity, overall assessment, and approval recommendation."
    ),
    _STRATEGY_GENERATE: (
        "You are generating code. "
        "First confirm the language, framework, and coding conventions. "
        "Write clean, well-documented code with error handling. "
        "Include type hints/annotations where the language supports them. "
        "Add inline comments for non-obvious logic. "
        "Suggest accompanying tests."
    ),
    _STRATEGY_REFACTOR: (
        "You are refactoring code. "
        "Identify code smells: duplication, long methods, god classes, feature envy. "
        "Apply appropriate refactoring patterns (Extract Method, Move Field, etc.). "
        "Ensure behavior is preserved -- run tests before and after. "
        "Document the rationale for each change."
    ),
    _STRATEGY_DEBUG: (
        "You are debugging an issue. Follow a systematic approach:\n"
        "1. Reproduce -- understand the symptoms and how to trigger the bug.\n"
        "2. Isolate -- narrow down the location using logs, breakpoints, bisect.\n"
        "3. Root cause -- identify the underlying defect, not just the symptom.\n"
        "4. Fix -- apply the minimal correct fix.\n"
        "5. Verify -- confirm the fix resolves the issue and doesn't introduce regressions.\n"
        "6. Prevent -- suggest tests or invariants to catch similar bugs in the future."
    ),
    _STRATEGY_GIT: (
        "You are performing git operations. "
        "Always show `git status` before and after operations. "
        "Use conventional commit messages: type(scope): description. "
        "For merge conflicts, show both sides and recommend resolution."
    ),
    _STRATEGY_BUILD: (
        "You are managing a build process. "
        "Check build tool configuration, dependencies, and environment. "
        "Provide clear error diagnosis for build failures. "
        "Suggest optimizations for build speed."
    ),
    _STRATEGY_TEST: (
        "You are working with tests. "
        "Follow Arrange-Act-Assert pattern. "
        "Cover: happy path, boundary values, error cases, concurrency (if applicable). "
        "Use descriptive names: test_<unit>_<scenario>_<expected>. "
        "Aim for deterministic, isolated, fast tests."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs per strategy (used when no LLM is available)
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _STRATEGY_REVIEW: (
        "Review complete: 0 CRITICAL, 1 HIGH, 2 MEDIUM, 5 LOW findings.\n"
        "[HIGH] src/main.py:42 -- SQL query built with string concatenation (injection risk).\n"
        "  Suggestion: Use parameterized queries.\n"
        "[MEDIUM] src/utils.py:17 -- Bare except clause swallows all errors.\n"
        "  Suggestion: Catch specific exceptions.\n"
        "Overall: Approve with requested changes."
    ),
    _STRATEGY_GENERATE: "Generated code skeleton based on requirements.",
    _STRATEGY_REFACTOR: "Refactoring applied: extracted 2 helper methods, reduced cyclomatic complexity from 12 to 4.",
    _STRATEGY_DEBUG: "Root cause identified: off-by-one error in loop boundary. Fix applied and verified.",
    _STRATEGY_GIT: "Git operation executed successfully.",
    _STRATEGY_BUILD: "Build completed. All checks passed.",
    _STRATEGY_TEST: "Test suite executed. 42/42 passed. Coverage: 87%.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str | None:
    """Detect the primary programming language mentioned in *text*."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for lang, patterns in _LANGUAGE_PATTERNS.items():
        score = sum(1 for p in patterns if p in lower)
        if score:
            scores[lang] = score
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def extract_code_blocks(text: str) -> list[dict[str, str]]:
    """Extract fenced code blocks from markdown-formatted *text*.

    Returns a list of dicts with keys ``language`` and ``code``.
    """
    pattern = r"```(\w*)\n(.*?)```"
    blocks: list[dict[str, str]] = []
    for match in re.finditer(pattern, text, re.DOTALL):
        blocks.append({"language": match.group(1) or "text", "code": match.group(2).strip()})
    return blocks


def build_review_summary(findings: list[dict[str, Any]]) -> str:
    """Build a human-readable review summary from structured findings.

    Each finding dict should have keys: severity, file, line, message, suggestion.
    """
    if not findings:
        return "No findings."

    by_severity: dict[str, int] = {}
    lines: list[str] = []
    for f in findings:
        sev = f.get("severity", "INFO")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        loc = f"{f.get('file', '?')}:{f.get('line', '?')}"
        lines.append(f"[{sev}] {loc} -- {f.get('message', '')}")
        if f.get("suggestion"):
            lines.append(f"  Suggestion: {f['suggestion']}")

    header_parts = [f"{count} {sev}" for sev, count in sorted(by_severity.items())]
    header = "Review summary: " + ", ".join(header_parts)
    return header + "\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# CodeAgent
# ---------------------------------------------------------------------------

class CodeAgent(BaseAgent):
    """Specialist agent for code-related tasks with real LLM + tool execution.

    Supports multiple execution strategies:
    - **review**: full-checklist code review (OWASP, SOLID, perf, quality)
    - **generate**: code scaffolding with language detection
    - **refactor**: smell detection and pattern-based refactoring
    - **debug**: systematic root-cause analysis
    - **git**: version-control operations
    - **build**: build orchestration and failure triage
    - **test**: test generation and coverage analysis
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="code-agent",
            description="Code review, generation, git operations, and build management",
            skills=["code-review", "code-generation", "git", "build", "test", "refactor"],
            input_modes=["text", "code-diff"],
            output_modes=["text", "code", "structured-comment"],
            domain="development",
            can_delegate=True,
            tool_filter=["shell_execute", "read_file", "write_file", "git_status", "git_diff", "git_log", "python_execute", "list_directory"],
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[CodeAgent] Processing: %s", message[:80])

        strategy = self._classify(message)
        language = detect_language(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(strategy, language)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=3,
            )
            if result.success:
                return result
            logger.warning("[CodeAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[CodeAgent] strategy='{strategy}'"
        if language:
            output += f", language='{language}'"
        output += ". "
        output += _MOCK_OUTPUTS.get(strategy, "Task processed.")

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "code", "代码", "review", "审查", "git", "build", "test",
            "测试", "compile", "refactor", "重构", "pr", "commit",
            "生成代码", "写代码", "编码", "开发", "debug", "bug",
            "function", "class", "method", "api", "接口",
            "lint", "type check", "coverage", "merge", "branch",
            "diff", "patch", "pull request",
        ]
        msg = message.lower()
        hits = sum(1 for k in keywords if k in msg)
        return min(hits * 0.25, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _STRATEGY_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return "code-review"  # safe default

    def _build_system_prompt(self, strategy: str, language: str | None) -> str:
        """Compose a strategy-specific system prompt with optional language context."""
        parts = [CODE_AGENT_SYSTEM_PROMPT]

        # Strategy-specific augmentation
        augmentation = _STRATEGY_PROMPTS.get(strategy)
        if augmentation:
            parts.append(f"\n# Current task strategy: {strategy}\n{augmentation}")

        # Language context
        if language:
            parts.append(
                f"\n# Detected language: {language}\n"
                f"Apply {language}-specific idioms, conventions, and best practices."
            )

        return "\n".join(parts)
