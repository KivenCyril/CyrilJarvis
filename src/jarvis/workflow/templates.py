"""Workflow templates for JARVIS.

Provides reusable workflow templates that can be instantiated with
specific parameters to create ready-to-run workflows.
"""

from __future__ import annotations

import copy
import logging
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from .models import (
    StepType,
    Workflow,
    WorkflowStep,
    WorkflowVariable,
)

logger = logging.getLogger(__name__)


class WorkflowTemplate(BaseModel):
    """Reusable workflow template.

    Templates define workflow structure with placeholders for customisation.
    When instantiated, placeholders are filled with actual values.

    Placeholder syntax inside step fields (action, description, etc.):
    - ``{{param_name}}`` -- replaced with the corresponding parameter value.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    description: str = ""
    category: str = ""
    parameters: list[WorkflowVariable] = Field(default_factory=list)
    workflow: Workflow = Field(default_factory=lambda: Workflow(name=""))

    def instantiate(self, params: dict[str, Any] | None = None) -> Workflow:
        """Create a workflow instance from this template with given parameters.

        Steps:
        1. Deep-copy the template workflow.
        2. Fill in parameter defaults for any missing keys.
        3. Validate required parameters.
        4. Replace ``{{placeholder}}`` tokens in string fields.
        5. Populate workflow variables from parameters.
        6. Assign a fresh workflow ID.

        Args:
            params: Mapping of parameter name -> value.

        Returns:
            A new ``Workflow`` ready for execution.

        Raises:
            ValueError: If a required parameter is missing.
        """
        params = dict(params) if params else {}

        # Fill defaults
        for pdef in self.parameters:
            if pdef.name not in params:
                if pdef.required:
                    raise ValueError(
                        f"Required parameter '{pdef.name}' not provided "
                        f"for template '{self.name}'"
                    )
                if pdef.default is not None:
                    params[pdef.name] = pdef.default

        # Deep-copy workflow so the template stays clean
        wf_data = self.workflow.model_dump(mode="json")
        wf = Workflow.model_validate(wf_data)

        # New identity
        wf.id = uuid.uuid4().hex[:12]

        # Replace placeholders in step string fields
        for step in wf.steps:
            step.action = self._replace_placeholders(step.action, params)
            step.description = self._replace_placeholders(step.description, params)
            step.condition = self._replace_placeholders(step.condition, params)
            step.agent = self._replace_placeholders(step.agent, params)
            step.tool = self._replace_placeholders(step.tool, params)
            step.approval_message = self._replace_placeholders(
                step.approval_message, params
            )
            step.transform_expression = self._replace_placeholders(
                step.transform_expression, params
            )

        # Set workflow variables from params
        for key, val in params.items():
            wf.set_variable(key, val)

        return wf

    @staticmethod
    def _replace_placeholders(text: str, params: dict[str, Any]) -> str:
        """Replace ``{{key}}`` placeholders in *text* with values from *params*."""
        if not text:
            return text

        def _sub(match: re.Match) -> str:
            key = match.group(1).strip()
            return str(params.get(key, match.group(0)))

        return re.sub(r"\{\{\s*(\w+)\s*\}\}", _sub, text)


class TemplateRegistry:
    """Registry for workflow templates.

    Provides lookup by name, category filtering, and keyword search.
    """

    def __init__(self) -> None:
        self._templates: dict[str, WorkflowTemplate] = {}

    def register(self, template: WorkflowTemplate) -> None:
        """Register a template (keyed by name)."""
        self._templates[template.name] = template
        logger.debug("Registered workflow template: %s", template.name)

    def get(self, name: str) -> WorkflowTemplate | None:
        """Retrieve a template by name."""
        return self._templates.get(name)

    def list_templates(
        self, category: str | None = None
    ) -> list[WorkflowTemplate]:
        """List all templates, optionally filtered by category."""
        if category is None:
            return list(self._templates.values())
        return [
            t
            for t in self._templates.values()
            if t.category == category
        ]

    def search(self, query: str) -> list[WorkflowTemplate]:
        """Search templates by keyword (matches name and description)."""
        q = query.lower()
        return [
            t
            for t in self._templates.values()
            if q in t.name.lower() or q in t.description.lower()
        ]

    def unregister(self, name: str) -> bool:
        """Remove a template by name. Returns True if removed."""
        return self._templates.pop(name, None) is not None

    def categories(self) -> list[str]:
        """Return a sorted list of unique categories."""
        cats = {t.category for t in self._templates.values() if t.category}
        return sorted(cats)

    # ------------------------------------------------------------------
    # Built-in templates
    # ------------------------------------------------------------------

    @staticmethod
    def builtin_templates() -> list[WorkflowTemplate]:
        """Return built-in workflow templates."""
        templates: list[WorkflowTemplate] = []

        # ---- CI/CD Pipeline ----
        ci_cd = WorkflowTemplate(
            name="ci-cd-pipeline",
            description="Standard CI/CD pipeline: lint -> test -> build -> deploy",
            category="devops",
            parameters=[
                WorkflowVariable(
                    name="project_path", var_type="string", required=True
                ),
                WorkflowVariable(
                    name="deploy_target",
                    var_type="string",
                    default="staging",
                ),
            ],
            workflow=Workflow(
                name="CI/CD Pipeline",
                steps=[
                    WorkflowStep(
                        name="Lint",
                        step_type=StepType.ACTION,
                        agent="code-agent",
                        action="Run linters on {{project_path}}",
                    ),
                    WorkflowStep(
                        name="Test",
                        step_type=StepType.ACTION,
                        agent="code-agent",
                        action="Run test suite",
                    ),
                    WorkflowStep(
                        name="Quality Gate",
                        step_type=StepType.CONDITION,
                        condition="steps.Test.output.pass_rate > 0.95",
                    ),
                    WorkflowStep(
                        name="Build",
                        step_type=StepType.ACTION,
                        agent="devops-agent",
                        action="Build artifacts",
                    ),
                    WorkflowStep(
                        name="Deploy",
                        step_type=StepType.ACTION,
                        agent="devops-agent",
                        action="Deploy to {{deploy_target}}",
                    ),
                    WorkflowStep(
                        name="Verify",
                        step_type=StepType.ACTION,
                        agent="ops-agent",
                        action="Run smoke tests",
                    ),
                ],
            ),
        )
        steps = ci_cd.workflow.steps
        steps[1].depends_on = [steps[0].id]
        steps[2].depends_on = [steps[1].id]
        steps[3].depends_on = [steps[2].id]
        steps[4].depends_on = [steps[3].id]
        steps[5].depends_on = [steps[4].id]
        templates.append(ci_cd)

        # ---- Code Review ----
        review = WorkflowTemplate(
            name="code-review",
            description="Comprehensive code review: security -> quality -> performance -> report",
            category="development",
            parameters=[
                WorkflowVariable(
                    name="file_paths", var_type="list", required=True
                ),
            ],
            workflow=Workflow(
                name="Code Review",
                steps=[
                    WorkflowStep(
                        name="Security Scan",
                        step_type=StepType.ACTION,
                        agent="security-agent",
                        action="Scan for vulnerabilities",
                    ),
                    WorkflowStep(
                        name="Quality Analysis",
                        step_type=StepType.ACTION,
                        agent="code-agent",
                        action="Analyze code quality",
                    ),
                    WorkflowStep(
                        name="Performance Check",
                        step_type=StepType.ACTION,
                        agent="code-agent",
                        action="Check performance patterns",
                    ),
                    WorkflowStep(
                        name="Generate Report",
                        step_type=StepType.ACTION,
                        agent="writing-agent",
                        action="Generate review report",
                    ),
                ],
            ),
        )
        r_steps = review.workflow.steps
        r_steps[3].depends_on = [r_steps[0].id, r_steps[1].id, r_steps[2].id]
        templates.append(review)

        # ---- Data Analysis ----
        data = WorkflowTemplate(
            name="data-analysis",
            description="Data analysis pipeline: ingest -> clean -> analyze -> visualize -> report",
            category="data",
            parameters=[
                WorkflowVariable(
                    name="data_source", var_type="string", required=True
                ),
            ],
            workflow=Workflow(
                name="Data Analysis",
                steps=[
                    WorkflowStep(
                        name="Ingest Data",
                        step_type=StepType.ACTION,
                        agent="data-agent",
                        action="Ingest from {{data_source}}",
                    ),
                    WorkflowStep(
                        name="Clean & Validate",
                        step_type=StepType.ACTION,
                        agent="data-agent",
                        action="Clean and validate data",
                    ),
                    WorkflowStep(
                        name="Statistical Analysis",
                        step_type=StepType.ACTION,
                        agent="data-agent",
                        action="Run statistical analysis",
                    ),
                    WorkflowStep(
                        name="Generate Insights",
                        step_type=StepType.ACTION,
                        agent="research-agent",
                        action="Generate insights from analysis",
                    ),
                    WorkflowStep(
                        name="Write Report",
                        step_type=StepType.ACTION,
                        agent="writing-agent",
                        action="Write final report",
                    ),
                ],
            ),
        )
        d_steps = data.workflow.steps
        d_steps[1].depends_on = [d_steps[0].id]
        d_steps[2].depends_on = [d_steps[1].id]
        d_steps[3].depends_on = [d_steps[2].id]
        d_steps[4].depends_on = [d_steps[3].id]
        templates.append(data)

        # ---- Incident Response ----
        incident = WorkflowTemplate(
            name="incident-response",
            description="Incident response: triage -> diagnose -> mitigate -> communicate -> postmortem",
            category="operations",
            workflow=Workflow(
                name="Incident Response",
                steps=[
                    WorkflowStep(
                        name="Triage",
                        step_type=StepType.ACTION,
                        agent="ops-agent",
                        action="Triage the incident",
                    ),
                    WorkflowStep(
                        name="Severity Check",
                        step_type=StepType.CONDITION,
                        condition="steps.Triage.output.severity in ['P0', 'P1']",
                    ),
                    WorkflowStep(
                        name="Escalate",
                        step_type=StepType.ACTION,
                        agent="comms-agent",
                        action="Page on-call",
                    ),
                    WorkflowStep(
                        name="Diagnose",
                        step_type=StepType.ACTION,
                        agent="ops-agent",
                        action="Diagnose root cause",
                    ),
                    WorkflowStep(
                        name="Mitigate",
                        step_type=StepType.ACTION,
                        agent="devops-agent",
                        action="Apply mitigation",
                    ),
                    WorkflowStep(
                        name="Approval Gate",
                        step_type=StepType.APPROVAL,
                        approval_message="Approve mitigation deployment?",
                    ),
                    WorkflowStep(
                        name="Deploy Fix",
                        step_type=StepType.ACTION,
                        agent="devops-agent",
                        action="Deploy fix to production",
                    ),
                    WorkflowStep(
                        name="Verify",
                        step_type=StepType.ACTION,
                        agent="ops-agent",
                        action="Verify fix in production",
                    ),
                    WorkflowStep(
                        name="Postmortem",
                        step_type=StepType.ACTION,
                        agent="writing-agent",
                        action="Write postmortem document",
                    ),
                ],
            ),
        )
        i_steps = incident.workflow.steps
        i_steps[1].depends_on = [i_steps[0].id]
        i_steps[2].depends_on = [i_steps[1].id]
        i_steps[3].depends_on = [i_steps[1].id]
        i_steps[4].depends_on = [i_steps[3].id]
        i_steps[5].depends_on = [i_steps[4].id]
        i_steps[6].depends_on = [i_steps[5].id]
        i_steps[7].depends_on = [i_steps[6].id]
        i_steps[8].depends_on = [i_steps[7].id]
        templates.append(incident)

        # ---- Research Report ----
        research = WorkflowTemplate(
            name="research-report",
            description="Deep research: gather sources -> analyze -> synthesize -> review -> publish",
            category="research",
            workflow=Workflow(
                name="Research Report",
                steps=[
                    WorkflowStep(
                        name="Define Questions",
                        step_type=StepType.ACTION,
                        agent="research-agent",
                        action="Define research questions",
                    ),
                    WorkflowStep(
                        name="Gather Sources",
                        step_type=StepType.ACTION,
                        agent="research-agent",
                        action="Gather sources",
                    ),
                    WorkflowStep(
                        name="Analyze Sources",
                        step_type=StepType.LOOP,
                        loop_over="sources",
                        agent="research-agent",
                        action="Analyze source",
                    ),
                    WorkflowStep(
                        name="Synthesize Findings",
                        step_type=StepType.ACTION,
                        agent="research-agent",
                        action="Synthesize findings",
                    ),
                    WorkflowStep(
                        name="Write Report",
                        step_type=StepType.ACTION,
                        agent="writing-agent",
                        action="Write research report",
                    ),
                    WorkflowStep(
                        name="Peer Review",
                        step_type=StepType.ACTION,
                        agent="research-agent",
                        action="Review report",
                    ),
                    WorkflowStep(
                        name="Final Edit",
                        step_type=StepType.ACTION,
                        agent="writing-agent",
                        action="Final editing pass",
                    ),
                ],
            ),
        )
        rs = research.workflow.steps
        rs[1].depends_on = [rs[0].id]
        rs[2].depends_on = [rs[1].id]
        rs[3].depends_on = [rs[2].id]
        rs[4].depends_on = [rs[3].id]
        rs[5].depends_on = [rs[4].id]
        rs[6].depends_on = [rs[5].id]
        templates.append(research)

        return templates
