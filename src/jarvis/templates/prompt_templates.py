"""Prompt templates for agent tasks, reviews, analysis, and more."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class PromptTemplate(BaseModel):
    """Reusable prompt template with {variable} substitution."""

    name: str
    description: str = ""
    template: str
    variables: list[str] = Field(default_factory=list)
    category: str = ""  # agent_system, task, review, analysis, code, etc.

    def render(self, **kwargs: Any) -> str:
        """Render the template, substituting provided variables.

        Unknown placeholders are left intact.
        """
        result = self.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    def missing_variables(self, **kwargs: Any) -> list[str]:
        """Return variable names that are required but not supplied."""
        return [v for v in self.variables if v not in kwargs]


class PromptLibrary:
    """Library of reusable prompt templates.

    Categories:
    - code        -- Code review, bug analysis, refactoring
    - documentation -- API docs, technical writing
    - data        -- Data analysis, ETL
    - operations  -- Incident summaries, runbooks
    - productivity -- Meeting agendas, status reports
    - security    -- Security assessments
    """

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}
        self._load_builtins()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str) -> PromptTemplate | None:
        """Retrieve a template by exact name."""
        return self._templates.get(name)

    def list_templates(self, category: str | None = None) -> list[PromptTemplate]:
        """List all templates, optionally filtered by category."""
        templates = list(self._templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return sorted(templates, key=lambda t: t.name)

    def search(self, query: str) -> list[PromptTemplate]:
        """Simple case-insensitive search across name, description, category."""
        q = query.lower()
        results: list[PromptTemplate] = []
        for t in self._templates.values():
            haystack = f"{t.name} {t.description} {t.category}".lower()
            if q in haystack:
                results.append(t)
        return sorted(results, key=lambda t: t.name)

    def add(self, template: PromptTemplate) -> None:
        """Register a new template (or overwrite an existing one)."""
        self._templates[template.name] = template

    def remove(self, name: str) -> bool:
        """Remove a template by name. Returns True if it existed."""
        return self._templates.pop(name, None) is not None

    def render(self, name: str, **kwargs: Any) -> str:
        """Shorthand: look up a template and render it.

        Raises ``KeyError`` if the template is not found.
        """
        tpl = self._templates.get(name)
        if tpl is None:
            raise KeyError(f"Prompt template not found: {name}")
        return tpl.render(**kwargs)

    @property
    def categories(self) -> list[str]:
        """Return sorted unique categories."""
        return sorted({t.category for t in self._templates.values() if t.category})

    def __len__(self) -> int:
        return len(self._templates)

    # ------------------------------------------------------------------
    # Built-in templates
    # ------------------------------------------------------------------

    def _load_builtins(self) -> None:
        """Load all built-in prompt templates."""
        builtins = [
            # -- code --
            PromptTemplate(
                name="code_review_detailed",
                description="Comprehensive code review with multi-level feedback.",
                category="code",
                template=(
                    "Review the following code with focus on {focus_areas}.\n\n"
                    "Code language: {language}\n"
                    "Context: {context}\n\n"
                    "Review criteria:\n"
                    "1. Correctness: Logic errors, edge cases, null handling\n"
                    "2. Security: {security_level} level review\n"
                    "3. Performance: Identify O(n^2) or worse, unnecessary allocations\n"
                    "4. Maintainability: Naming, structure, SOLID principles\n"
                    "5. Testing: Testability, missing test cases\n\n"
                    "Code:\n```\n{code}\n```\n\n"
                    "Provide feedback as:\n"
                    "- CRITICAL (must fix)\n"
                    "- WARNING (should fix)\n"
                    "- SUGGESTION (nice to have)\n"
                    "- GOOD (positive reinforcement)"
                ),
                variables=["focus_areas", "language", "context", "security_level", "code"],
            ),
            PromptTemplate(
                name="bug_analysis",
                description="Diagnose a bug from a report and suggest fixes.",
                category="code",
                template=(
                    "Analyze the following bug report and provide a diagnosis.\n\n"
                    "Bug description: {description}\n"
                    "Expected behavior: {expected}\n"
                    "Actual behavior: {actual}\n"
                    "Steps to reproduce: {steps}\n"
                    "Error logs:\n```\n{logs}\n```\n\n"
                    "Provide:\n"
                    "1. Root cause analysis\n"
                    "2. Affected components\n"
                    "3. Fix recommendation (with code if possible)\n"
                    "4. Regression risk assessment\n"
                    "5. Test cases to add"
                ),
                variables=["description", "expected", "actual", "steps", "logs"],
            ),
            PromptTemplate(
                name="refactoring_plan",
                description="Create a detailed refactoring plan.",
                category="code",
                template=(
                    "Create a refactoring plan for the following code.\n\n"
                    "Current code structure:\n{code_structure}\n\n"
                    "Issues identified:\n{issues}\n\n"
                    "Refactoring goals: {goals}\n"
                    "Constraints: {constraints}\n\n"
                    "Generate:\n"
                    "1. Refactoring strategy (pattern to apply)\n"
                    "2. Step-by-step migration plan\n"
                    "3. Files to modify\n"
                    "4. Breaking changes and migration guide\n"
                    "5. Testing strategy\n"
                    "6. Rollback plan"
                ),
                variables=["code_structure", "issues", "goals", "constraints"],
            ),
            # -- documentation --
            PromptTemplate(
                name="api_documentation",
                description="Generate API endpoint documentation.",
                category="documentation",
                template=(
                    "Generate comprehensive API documentation for the following endpoint.\n\n"
                    "Method: {method}\n"
                    "Path: {path}\n"
                    "Description: {description}\n\n"
                    "Request body: {request_schema}\n"
                    "Response: {response_schema}\n\n"
                    "Generate:\n"
                    "1. Endpoint description\n"
                    "2. Request parameters with types and validation rules\n"
                    "3. Request/response examples (JSON)\n"
                    "4. Error responses (400, 401, 404, 500)\n"
                    "5. Rate limiting information\n"
                    "6. Authentication requirements"
                ),
                variables=["method", "path", "description", "request_schema", "response_schema"],
            ),
            # -- data --
            PromptTemplate(
                name="data_analysis",
                description="Analyze a dataset and provide insights.",
                category="data",
                template=(
                    "Analyze the following dataset and provide insights.\n\n"
                    "Dataset: {dataset_description}\n"
                    "Columns: {columns}\n"
                    "Sample data: {sample}\n"
                    "Analysis goals: {goals}\n\n"
                    "Provide:\n"
                    "1. Data quality assessment (missing values, outliers, inconsistencies)\n"
                    "2. Descriptive statistics\n"
                    "3. Key patterns and correlations\n"
                    "4. Actionable insights\n"
                    "5. Recommended visualizations\n"
                    "6. Next steps for deeper analysis"
                ),
                variables=["dataset_description", "columns", "sample", "goals"],
            ),
            # -- operations --
            PromptTemplate(
                name="incident_summary",
                description="Summarize an incident for stakeholder communication.",
                category="operations",
                template=(
                    "Summarize the following incident for stakeholder communication.\n\n"
                    "Incident ID: {incident_id}\n"
                    "Severity: {severity}\n"
                    "Start time: {start_time}\n"
                    "Duration: {duration}\n"
                    "Affected services: {services}\n"
                    "Root cause: {root_cause}\n"
                    "Resolution: {resolution}\n\n"
                    "Generate:\n"
                    "1. Executive summary (2-3 sentences)\n"
                    "2. Timeline of events\n"
                    "3. Impact assessment\n"
                    "4. Resolution steps taken\n"
                    "5. Prevention measures\n"
                    "6. Action items with owners"
                ),
                variables=[
                    "incident_id", "severity", "start_time", "duration",
                    "services", "root_cause", "resolution",
                ],
            ),
            # -- productivity --
            PromptTemplate(
                name="meeting_agenda",
                description="Create a structured meeting agenda.",
                category="productivity",
                template=(
                    "Create a structured meeting agenda.\n\n"
                    "Meeting title: {title}\n"
                    "Duration: {duration}\n"
                    "Attendees: {attendees}\n"
                    "Purpose: {purpose}\n"
                    "Previous action items: {action_items}\n\n"
                    "Generate:\n"
                    "1. Opening (2 min) - Welcome and objectives\n"
                    "2. Status updates from each attendee\n"
                    "3. Discussion topics with time allocation\n"
                    "4. Decision items requiring votes\n"
                    "5. Action items and owners\n"
                    "6. Next meeting date/topics"
                ),
                variables=["title", "duration", "attendees", "purpose", "action_items"],
            ),
            # -- security --
            PromptTemplate(
                name="security_report",
                description="Generate a security assessment report.",
                category="security",
                template=(
                    "Generate a security assessment report.\n\n"
                    "Target: {target}\n"
                    "Scope: {scope}\n"
                    "Assessment type: {assessment_type}\n\n"
                    "Findings:\n{findings}\n\n"
                    "Generate:\n"
                    "1. Executive summary\n"
                    "2. Risk rating (Critical/High/Medium/Low/Info counts)\n"
                    "3. Detailed findings with:\n"
                    "   - Description\n"
                    "   - CVSS score (if applicable)\n"
                    "   - Evidence\n"
                    "   - Impact\n"
                    "   - Remediation\n"
                    "4. Compliance implications\n"
                    "5. Remediation priority matrix\n"
                    "6. Timeline recommendation"
                ),
                variables=["target", "scope", "assessment_type", "findings"],
            ),
            # -- agent system prompts --
            PromptTemplate(
                name="agent_system_base",
                description="Base system prompt for JARVIS agents.",
                category="agent_system",
                template=(
                    "You are a {role} agent within the JARVIS system.\n\n"
                    "Your capabilities:\n{capabilities}\n\n"
                    "Current task: {task}\n\n"
                    "Guidelines:\n"
                    "- Stay within your defined role\n"
                    "- Report progress through Streaming Spec updates\n"
                    "- Escalate blockers immediately\n"
                    "- Follow the constraints specified in the spec"
                ),
                variables=["role", "capabilities", "task"],
            ),
        ]

        for tpl in builtins:
            self._templates[tpl.name] = tpl
