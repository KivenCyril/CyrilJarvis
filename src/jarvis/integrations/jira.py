"""Jira integration for JARVIS project management.

Supports:
- Create, get, update, and search issues
- Add comments and transition issue statuses
- List projects and sprints
- Create Jira issues from Streaming Spec steps
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JiraConfig(BaseModel):
    """Configuration for Jira API access."""

    base_url: str = ""
    email: str = ""
    api_token: str = ""
    default_project: str = ""


class JiraIssue(BaseModel):
    """Represents a Jira issue."""

    key: str = ""
    summary: str = ""
    description: str = ""
    issue_type: str = "Task"
    status: str = "To Do"
    priority: str = "Medium"
    assignee: str = ""
    labels: list[str] = Field(default_factory=list)
    story_points: float | None = None


# Maps common status display names to Jira transition IDs.
# Real Jira instances vary; these serve as sensible defaults.
DEFAULT_TRANSITIONS: dict[str, str] = {
    "To Do": "11",
    "In Progress": "21",
    "In Review": "31",
    "Done": "41",
}

PRIORITY_MAP: dict[str, str] = {
    "highest": "1",
    "high": "2",
    "medium": "3",
    "low": "4",
    "lowest": "5",
}


def _parse_issue(data: dict[str, Any]) -> JiraIssue:
    """Parse a Jira REST API issue response into a JiraIssue."""
    fields = data.get("fields", {})
    return JiraIssue(
        key=data.get("key", ""),
        summary=fields.get("summary", ""),
        description=fields.get("description", "") or "",
        issue_type=(fields.get("issuetype") or {}).get("name", "Task"),
        status=(fields.get("status") or {}).get("name", "To Do"),
        priority=(fields.get("priority") or {}).get("name", "Medium"),
        assignee=(fields.get("assignee") or {}).get("displayName", ""),
        labels=fields.get("labels", []),
        story_points=fields.get("story_points"),
    )


class JiraClient:
    """Jira REST API client for JARVIS integrations."""

    def __init__(self, config: JiraConfig | None = None):
        self.config = config or JiraConfig()

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _auth(self) -> tuple[str, str]:
        return self.config.email, self.config.api_token

    def _url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        return f"{base}/rest/api/3{path}"

    def _agile_url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        return f"{base}/rest/agile/1.0{path}"

    async def _request(
        self, method: str, url: str, **kwargs: Any
    ) -> dict[str, Any]:
        import httpx

        logger.debug("Jira API %s %s", method, url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                url,
                auth=self._auth(),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                **kwargs,
            )
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()

    def _resolve_project(self, project: str) -> str:
        p = project or self.config.default_project
        if not p:
            raise ValueError(
                "project must be provided or set as default in config"
            )
        return p

    # --------------------------------------------------------------------- #
    # Issues
    # --------------------------------------------------------------------- #

    async def create_issue(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        project: str = "",
        labels: list[str] | None = None,
        priority: str = "Medium",
        assignee: str = "",
    ) -> JiraIssue:
        """Create a new Jira issue."""
        proj = self._resolve_project(project)
        fields: dict[str, Any] = {
            "project": {"key": proj},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description or ""}],
                    }
                ],
            },
            "issuetype": {"name": issue_type},
        }
        if labels:
            fields["labels"] = labels
        if priority:
            fields["priority"] = {"name": priority}
        data = await self._request("POST", self._url("/issue"), json={"fields": fields})
        # Fetch the full issue to return populated fields
        return await self.get_issue(data.get("key", ""))

    async def get_issue(self, key: str) -> JiraIssue:
        """Get a single issue by key (e.g. ``PROJ-123``)."""
        data = await self._request("GET", self._url(f"/issue/{key}"))
        return _parse_issue(data)

    async def update_issue(self, key: str, **fields: Any) -> JiraIssue:
        """Update an existing Jira issue.

        Accepted keyword arguments: ``summary``, ``description``, ``priority``,
        ``labels``, ``status``, ``assignee``.
        """
        update_fields: dict[str, Any] = {}
        if "summary" in fields:
            update_fields["summary"] = fields["summary"]
        if "description" in fields:
            update_fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": fields["description"]}],
                    }
                ],
            }
        if "priority" in fields:
            update_fields["priority"] = {"name": fields["priority"]}
        if "labels" in fields:
            update_fields["labels"] = fields["labels"]

        if update_fields:
            await self._request(
                "PUT", self._url(f"/issue/{key}"), json={"fields": update_fields}
            )

        # Handle status transition separately
        if "status" in fields:
            await self.transition_issue(key, fields["status"])

        return await self.get_issue(key)

    async def search_issues(
        self, jql: str, max_results: int = 50
    ) -> list[JiraIssue]:
        """Search issues using JQL (Jira Query Language)."""
        data = await self._request(
            "POST",
            self._url("/search"),
            json={"jql": jql, "maxResults": max_results},
        )
        return [_parse_issue(item) for item in data.get("issues", [])]

    # --------------------------------------------------------------------- #
    # Comments & Transitions
    # --------------------------------------------------------------------- #

    async def add_comment(self, key: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        data = await self._request(
            "POST", self._url(f"/issue/{key}/comment"), json=payload
        )
        return {
            "id": data.get("id", ""),
            "body": body,
            "created": data.get("created", ""),
        }

    async def transition_issue(self, key: str, transition_name: str) -> bool:
        """Transition an issue to a new status.

        First fetches available transitions to find the matching one.
        """
        data = await self._request("GET", self._url(f"/issue/{key}/transitions"))
        transitions = data.get("transitions", [])
        target = None
        for t in transitions:
            if t.get("name", "").lower() == transition_name.lower():
                target = t
                break
        if not target:
            logger.warning(
                "Transition '%s' not found for %s. Available: %s",
                transition_name,
                key,
                [t.get("name") for t in transitions],
            )
            return False
        await self._request(
            "POST",
            self._url(f"/issue/{key}/transitions"),
            json={"transition": {"id": target["id"]}},
        )
        return True

    # --------------------------------------------------------------------- #
    # Projects & Sprints
    # --------------------------------------------------------------------- #

    async def list_projects(self) -> list[dict[str, Any]]:
        """List all accessible projects."""
        data = await self._request("GET", self._url("/project"))
        return [
            {
                "key": p.get("key", ""),
                "name": p.get("name", ""),
                "id": p.get("id", ""),
            }
            for p in data
        ]

    async def get_sprint(self, board_id: int) -> dict[str, Any]:
        """Get the active sprint for a board."""
        data = await self._request(
            "GET",
            self._agile_url(f"/board/{board_id}/sprint"),
            params={"state": "active"},
        )
        sprints = data.get("values", [])
        if not sprints:
            return {}
        sprint = sprints[0]
        return {
            "id": sprint.get("id", 0),
            "name": sprint.get("name", ""),
            "state": sprint.get("state", ""),
            "start_date": sprint.get("startDate", ""),
            "end_date": sprint.get("endDate", ""),
        }

    # --------------------------------------------------------------------- #
    # Spec Integration
    # --------------------------------------------------------------------- #

    async def create_issues_from_spec(
        self, spec: dict[str, Any], project: str = ""
    ) -> list[JiraIssue]:
        """Create Jira issues from a Streaming Spec's steps.

        Each step in ``spec["steps"]`` becomes a Task issue.  The spec title
        is used as a prefix for each issue summary.  Returns the list of
        created ``JiraIssue`` objects.
        """
        proj = self._resolve_project(project)
        spec_title = spec.get("title", "Untitled Spec")
        steps = spec.get("steps", [])
        created: list[JiraIssue] = []
        for idx, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {idx}")
            step_desc = step.get("description", "")
            summary = f"[{spec_title}] {step_name}"
            issue = await self.create_issue(
                summary=summary,
                description=step_desc,
                issue_type="Task",
                project=proj,
                labels=["jarvis", "streaming-spec"],
            )
            created.append(issue)
        return created


def build_jql(
    project: str = "",
    status: str = "",
    assignee: str = "",
    labels: list[str] | None = None,
    text: str = "",
) -> str:
    """Build a JQL query string from common filter parameters.

    This is a helper for constructing JQL without manual string wrangling.
    """
    clauses: list[str] = []
    if project:
        clauses.append(f'project = "{project}"')
    if status:
        clauses.append(f'status = "{status}"')
    if assignee:
        clauses.append(f'assignee = "{assignee}"')
    if labels:
        for label in labels:
            clauses.append(f'labels = "{label}"')
    if text:
        clauses.append(f'text ~ "{text}"')
    return " AND ".join(clauses) if clauses else "ORDER BY created DESC"
