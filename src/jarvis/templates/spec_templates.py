"""Reusable Streaming Spec templates."""

from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field


class TemplateParameter(BaseModel):
    """A parameter placeholder within a template."""

    name: str
    description: str = ""
    param_type: str = "string"  # string, number, boolean, choice, list
    required: bool = True
    default: Any = None
    choices: list[str] = Field(default_factory=list)

    def validate_value(self, value: Any) -> bool:
        """Check whether *value* satisfies this parameter's constraints."""
        if value is None:
            return not self.required
        if self.choices and str(value) not in self.choices:
            return False
        return True


class StepTemplate(BaseModel):
    """A step template that can be rendered with parameters."""

    order: int
    name_template: str  # e.g. "Deploy {service}"
    description_template: str = ""
    agent: str = ""
    depends_on_indices: list[int] = Field(default_factory=list)

    def render(self, params: dict[str, Any]) -> dict[str, Any]:
        """Render this step template with the given parameters."""
        return {
            "order": self.order,
            "name": _substitute(self.name_template, params),
            "description": _substitute(self.description_template, params),
            "agent": self.agent,
            "depends_on_indices": list(self.depends_on_indices),
        }


class SpecTemplate(BaseModel):
    """Reusable template for creating Streaming Specs.

    Templates define a common pattern that can be instantiated
    with different parameters each time.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    description: str = ""
    category: str = ""  # development, devops, data, communication, etc.
    parameters: list[TemplateParameter] = Field(default_factory=list)

    # Template content
    intent_template: str = ""  # e.g. "Deploy {service} to {environment}"
    steps_template: list[StepTemplate] = Field(default_factory=list)
    constraints_template: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    def render(self, params: dict[str, Any]) -> dict[str, Any]:
        """Render template with given parameters into a Spec creation dict.

        Raises ``ValueError`` if a required parameter is missing or invalid.
        """
        self._validate_params(params)
        merged = self._merge_defaults(params)

        return {
            "intent": _substitute(self.intent_template, merged),
            "steps": [s.render(merged) for s in self.steps_template],
            "constraints": [_substitute(c, merged) for c in self.constraints_template],
            "tags": list(self.tags),
            "template_id": self.id,
            "template_name": self.name,
        }

    def list_parameters(self) -> list[dict[str, Any]]:
        """Return a user-friendly list of parameter metadata."""
        return [
            {
                "name": p.name,
                "description": p.description,
                "type": p.param_type,
                "required": p.required,
                "default": p.default,
                "choices": p.choices,
            }
            for p in self.parameters
        ]

    # ------------------------------------------------------------------

    def _validate_params(self, params: dict[str, Any]) -> None:
        for p in self.parameters:
            if p.required and p.name not in params and p.default is None:
                raise ValueError(f"Missing required parameter: {p.name}")
            value = params.get(p.name, p.default)
            if not p.validate_value(value):
                raise ValueError(
                    f"Invalid value for {p.name}: {value!r} "
                    f"(choices: {p.choices})"
                )

    def _merge_defaults(self, params: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for p in self.parameters:
            merged[p.name] = params.get(p.name, p.default)
        # Also pass through any extra keys the caller provides
        for k, v in params.items():
            if k not in merged:
                merged[k] = v
        return merged


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _substitute(template: str, params: dict[str, Any]) -> str:
    """Simple {key} substitution, leaving unknown placeholders intact."""

    def _replacer(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in params and params[key] is not None:
            return str(params[key])
        return m.group(0)

    return _PLACEHOLDER_RE.sub(_replacer, template)


# ------------------------------------------------------------------
# Built-in spec templates
# ------------------------------------------------------------------


def _builtin_spec_templates() -> list[SpecTemplate]:
    """Return the set of built-in spec templates shipped with JARVIS."""

    templates: list[SpecTemplate] = []

    # 1. API Development
    templates.append(
        SpecTemplate(
            name="api-development",
            description="Build a new API endpoint or service.",
            category="development",
            intent_template="Build {name} API with {framework}",
            parameters=[
                TemplateParameter(name="name", description="API / service name"),
                TemplateParameter(
                    name="framework",
                    description="Web framework",
                    default="FastAPI",
                    choices=["FastAPI", "Flask", "Django", "Express", "Spring"],
                ),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Design API schema for {name}",
                             description_template="Define request/response models", agent="planner"),
                StepTemplate(order=2, name_template="Implement endpoints",
                             description_template="Build routes using {framework}", agent="coder",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Write tests",
                             description_template="Unit + integration tests for {name}", agent="coder",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Write documentation",
                             description_template="OpenAPI docs for {name}", agent="writer",
                             depends_on_indices=[1]),
            ],
            constraints_template=[
                "Follow REST conventions",
                "Include input validation",
                "Use {framework} best practices",
            ],
            tags=["api", "development", "backend"],
        )
    )

    # 2. Bug Fix
    templates.append(
        SpecTemplate(
            name="bug-fix",
            description="Diagnose and fix a reported bug.",
            category="development",
            intent_template="Fix bug: {description}",
            parameters=[
                TemplateParameter(name="description", description="Bug description"),
                TemplateParameter(name="severity", description="Bug severity",
                                  default="medium", choices=["low", "medium", "high", "critical"]),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Reproduce the bug",
                             description_template="Reproduce: {description}", agent="tester"),
                StepTemplate(order=2, name_template="Root cause analysis",
                             description_template="Identify root cause", agent="coder",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Implement fix",
                             description_template="Fix the issue", agent="coder",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Add regression tests",
                             description_template="Prevent recurrence", agent="coder",
                             depends_on_indices=[2]),
            ],
            constraints_template=[
                "Severity: {severity}",
                "Must include regression test",
                "No unrelated changes in the fix",
            ],
            tags=["bugfix", "maintenance"],
        )
    )

    # 3. Code Refactor
    templates.append(
        SpecTemplate(
            name="code-refactor",
            description="Refactor a component for a specific goal.",
            category="development",
            intent_template="Refactor {component} for {goal}",
            parameters=[
                TemplateParameter(name="component", description="Component or module to refactor"),
                TemplateParameter(name="goal", description="Refactoring goal (readability, performance, etc.)"),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Analyze {component}",
                             description_template="Identify areas to improve for {goal}", agent="planner"),
                StepTemplate(order=2, name_template="Plan refactoring",
                             description_template="Create step-by-step plan", agent="planner",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Apply refactoring",
                             description_template="Refactor {component}", agent="coder",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Verify behaviour unchanged",
                             description_template="Run tests, compare outputs", agent="tester",
                             depends_on_indices=[2]),
            ],
            constraints_template=[
                "No behaviour changes unless explicitly intended",
                "All existing tests must pass",
                "Optimise for {goal}",
            ],
            tags=["refactor", "maintenance", "quality"],
        )
    )

    # 4. Deploy
    templates.append(
        SpecTemplate(
            name="deploy",
            description="Deploy a service to a target environment.",
            category="devops",
            intent_template="Deploy {service} to {environment}",
            parameters=[
                TemplateParameter(name="service", description="Service name"),
                TemplateParameter(name="environment", description="Target environment",
                                  choices=["staging", "production", "dev"]),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Pre-deploy checks for {service}",
                             description_template="Run tests and linting", agent="tester"),
                StepTemplate(order=2, name_template="Build {service} artefacts",
                             description_template="Build Docker image / package", agent="coder",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Deploy to {environment}",
                             description_template="Push and deploy {service}", agent="deployer",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Verify deployment",
                             description_template="Health checks + smoke tests", agent="tester",
                             depends_on_indices=[2]),
            ],
            constraints_template=[
                "Zero-downtime deployment",
                "Rollback plan required for {environment}",
            ],
            tags=["deploy", "devops", "ci-cd"],
        )
    )

    # 5. Data Pipeline
    templates.append(
        SpecTemplate(
            name="data-pipeline",
            description="Build a data pipeline between two systems.",
            category="data",
            intent_template="Build data pipeline from {source} to {destination}",
            parameters=[
                TemplateParameter(name="source", description="Data source"),
                TemplateParameter(name="destination", description="Data destination"),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Analyse {source} schema",
                             description_template="Understand source data", agent="planner"),
                StepTemplate(order=2, name_template="Design transformation",
                             description_template="Map {source} to {destination}", agent="planner",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Implement pipeline",
                             description_template="ETL code from {source} to {destination}", agent="coder",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Test with sample data",
                             description_template="Validate transformations", agent="tester",
                             depends_on_indices=[2]),
            ],
            constraints_template=[
                "Handle schema evolution gracefully",
                "Include data validation at each stage",
            ],
            tags=["data", "etl", "pipeline"],
        )
    )

    # 6. Documentation
    templates.append(
        SpecTemplate(
            name="documentation",
            description="Write documentation for a project.",
            category="documentation",
            intent_template="Write documentation for {project}",
            parameters=[
                TemplateParameter(name="project", description="Project or component name"),
                TemplateParameter(name="audience", description="Target audience",
                                  default="developers"),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Audit existing docs for {project}",
                             description_template="Identify gaps", agent="writer"),
                StepTemplate(order=2, name_template="Outline documentation",
                             description_template="Structure for {audience}", agent="writer",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Write content",
                             description_template="Draft all sections", agent="writer",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Review and polish",
                             description_template="Technical review + copy editing", agent="reviewer",
                             depends_on_indices=[2]),
            ],
            constraints_template=[
                "Target audience: {audience}",
                "Include examples and diagrams where helpful",
            ],
            tags=["documentation", "writing"],
        )
    )

    # 7. Security Review
    templates.append(
        SpecTemplate(
            name="security-review",
            description="Security audit of a target system.",
            category="security",
            intent_template="Security audit of {target}",
            parameters=[
                TemplateParameter(name="target", description="System or component to audit"),
                TemplateParameter(name="scope", description="Audit scope",
                                  default="full"),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Threat modelling for {target}",
                             description_template="Identify attack surfaces", agent="security"),
                StepTemplate(order=2, name_template="Code scan",
                             description_template="Static analysis and dependency check", agent="security",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Manual review",
                             description_template="Review critical paths", agent="security",
                             depends_on_indices=[0]),
                StepTemplate(order=4, name_template="Write report",
                             description_template="Findings + remediation plan", agent="writer",
                             depends_on_indices=[1, 2]),
            ],
            constraints_template=[
                "Scope: {scope}",
                "Follow OWASP guidelines",
            ],
            tags=["security", "audit", "review"],
        )
    )

    # 8. Migration
    templates.append(
        SpecTemplate(
            name="migration",
            description="Migrate a system/component from one tech to another.",
            category="development",
            intent_template="Migrate {what} from {source} to {target}",
            parameters=[
                TemplateParameter(name="what", description="What is being migrated"),
                TemplateParameter(name="source", description="Source technology or system"),
                TemplateParameter(name="target", description="Target technology or system"),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Assess {what} in {source}",
                             description_template="Inventory and dependency analysis", agent="planner"),
                StepTemplate(order=2, name_template="Plan migration path",
                             description_template="Map {source} -> {target}", agent="planner",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Implement migration",
                             description_template="Migrate {what} to {target}", agent="coder",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Validate migration",
                             description_template="Verify parity between {source} and {target}",
                             agent="tester", depends_on_indices=[2]),
            ],
            constraints_template=[
                "Maintain backward compatibility during transition",
                "Include rollback procedure",
            ],
            tags=["migration", "modernisation"],
        )
    )

    # 9. Monitoring Setup
    templates.append(
        SpecTemplate(
            name="monitoring-setup",
            description="Set up monitoring and alerting for a service.",
            category="devops",
            intent_template="Set up monitoring for {service}",
            parameters=[
                TemplateParameter(name="service", description="Service to monitor"),
                TemplateParameter(name="stack", description="Monitoring stack",
                                  default="Prometheus+Grafana"),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Define SLIs/SLOs for {service}",
                             description_template="Key metrics and targets", agent="planner"),
                StepTemplate(order=2, name_template="Instrument {service}",
                             description_template="Add metrics and traces", agent="coder",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Build dashboards",
                             description_template="Dashboards using {stack}", agent="coder",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Configure alerts",
                             description_template="Alert rules for {service}", agent="coder",
                             depends_on_indices=[0]),
            ],
            constraints_template=[
                "Use {stack} for observability",
                "Follow the RED method (Rate, Errors, Duration)",
            ],
            tags=["monitoring", "devops", "observability"],
        )
    )

    # 10. Performance Test
    templates.append(
        SpecTemplate(
            name="performance-test",
            description="Performance and load testing for an endpoint or service.",
            category="testing",
            intent_template="Performance test {endpoint} under {load}",
            parameters=[
                TemplateParameter(name="endpoint", description="Endpoint or service to test"),
                TemplateParameter(name="load", description="Load profile (e.g. 1000 rps)"),
                TemplateParameter(name="duration", description="Test duration",
                                  default="5 minutes"),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Design test scenarios for {endpoint}",
                             description_template="Define load profiles", agent="tester"),
                StepTemplate(order=2, name_template="Set up test environment",
                             description_template="Provision infra for {load}", agent="deployer",
                             depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Execute load test",
                             description_template="Run {load} for {duration}", agent="tester",
                             depends_on_indices=[1]),
                StepTemplate(order=4, name_template="Analyse results",
                             description_template="Latency, throughput, error rates", agent="planner",
                             depends_on_indices=[2]),
            ],
            constraints_template=[
                "Test duration: {duration}",
                "Target load: {load}",
                "Record p50, p95, p99 latencies",
            ],
            tags=["performance", "testing", "load-test"],
        )
    )

    return templates


BUILTIN_SPEC_TEMPLATES: list[SpecTemplate] = _builtin_spec_templates()
