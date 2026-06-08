"""GitHub integration for JARVIS.

Provides tools for interacting with GitHub repositories:
- List/create/update issues
- List/create pull requests
- Get repository information
- Search code
- Get file contents
- Manage labels and milestones
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GitHubConfig(BaseModel):
    """Configuration for GitHub API access."""

    token: str = ""
    base_url: str = "https://api.github.com"
    default_owner: str = ""
    default_repo: str = ""


@dataclass
class GitHubIssue:
    """Represents a GitHub issue."""

    number: int
    title: str
    body: str = ""
    state: str = "open"
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    milestone: str = ""
    created_at: str = ""
    updated_at: str = ""
    html_url: str = ""


@dataclass
class GitHubPR:
    """Represents a GitHub pull request."""

    number: int
    title: str
    body: str = ""
    state: str = "open"
    head: str = ""
    base: str = "main"
    merged: bool = False
    draft: bool = False
    html_url: str = ""
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0


@dataclass
class GitHubRepo:
    """Represents a GitHub repository."""

    full_name: str
    description: str = ""
    default_branch: str = "main"
    stars: int = 0
    forks: int = 0
    language: str = ""
    topics: list[str] = field(default_factory=list)
    html_url: str = ""


def _parse_issue(data: dict[str, Any]) -> GitHubIssue:
    """Parse a GitHub API issue response into a GitHubIssue."""
    return GitHubIssue(
        number=data.get("number", 0),
        title=data.get("title", ""),
        body=data.get("body", "") or "",
        state=data.get("state", "open"),
        labels=[lb["name"] for lb in data.get("labels", []) if isinstance(lb, dict)],
        assignees=[a["login"] for a in data.get("assignees", []) if isinstance(a, dict)],
        milestone=(data.get("milestone") or {}).get("title", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        html_url=data.get("html_url", ""),
    )


def _parse_pr(data: dict[str, Any]) -> GitHubPR:
    """Parse a GitHub API PR response into a GitHubPR."""
    return GitHubPR(
        number=data.get("number", 0),
        title=data.get("title", ""),
        body=data.get("body", "") or "",
        state=data.get("state", "open"),
        head=(data.get("head") or {}).get("ref", ""),
        base=(data.get("base") or {}).get("ref", "main"),
        merged=data.get("merged", False),
        draft=data.get("draft", False),
        html_url=data.get("html_url", ""),
        additions=data.get("additions", 0),
        deletions=data.get("deletions", 0),
        changed_files=data.get("changed_files", 0),
    )


def _parse_repo(data: dict[str, Any]) -> GitHubRepo:
    """Parse a GitHub API repo response into a GitHubRepo."""
    return GitHubRepo(
        full_name=data.get("full_name", ""),
        description=data.get("description", "") or "",
        default_branch=data.get("default_branch", "main"),
        stars=data.get("stargazers_count", 0),
        forks=data.get("forks_count", 0),
        language=data.get("language", "") or "",
        topics=data.get("topics", []),
        html_url=data.get("html_url", ""),
    )


class GitHubClient:
    """GitHub API client for JARVIS integrations.

    Supports all common GitHub operations: repos, issues, PRs, files,
    labels, and code search.  When *owner* or *repo* is omitted from a
    method call the values fall back to ``config.default_owner`` /
    ``config.default_repo``.
    """

    def __init__(self, config: GitHubConfig | None = None):
        self.config = config or GitHubConfig()
        self._headers: dict[str, str] = {}
        if self.config.token:
            self._headers["Authorization"] = f"token {self.config.token}"
        self._headers["Accept"] = "application/vnd.github.v3+json"
        self._headers["User-Agent"] = "JARVIS-GitHub-Integration"

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _resolve_owner_repo(self, owner: str, repo: str) -> tuple[str, str]:
        """Resolve owner/repo, falling back to defaults from config."""
        resolved_owner = owner or self.config.default_owner
        resolved_repo = repo or self.config.default_repo
        if not resolved_owner or not resolved_repo:
            raise ValueError(
                "owner and repo must be provided or set as defaults in config"
            )
        return resolved_owner, resolved_repo

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated request to the GitHub API."""
        import httpx

        url = f"{self.config.base_url}{path}"
        logger.debug("GitHub API %s %s", method, url)
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()

    # --------------------------------------------------------------------- #
    # Repository
    # --------------------------------------------------------------------- #

    async def get_repo(self, owner: str = "", repo: str = "") -> GitHubRepo:
        """Get repository information."""
        o, r = self._resolve_owner_repo(owner, repo)
        data = await self._request("GET", f"/repos/{o}/{r}")
        return _parse_repo(data)

    async def list_repos(
        self, owner: str = "", per_page: int = 30
    ) -> list[GitHubRepo]:
        """List repositories for an owner/org."""
        o = owner or self.config.default_owner
        if not o:
            raise ValueError("owner must be provided or set as default in config")
        data = await self._request(
            "GET", f"/users/{o}/repos", params={"per_page": per_page}
        )
        return [_parse_repo(r) for r in data]

    # --------------------------------------------------------------------- #
    # Issues
    # --------------------------------------------------------------------- #

    async def list_issues(
        self,
        owner: str = "",
        repo: str = "",
        state: str = "open",
        labels: str = "",
        per_page: int = 30,
    ) -> list[GitHubIssue]:
        """List issues for a repository."""
        o, r = self._resolve_owner_repo(owner, repo)
        params: dict[str, Any] = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = labels
        data = await self._request("GET", f"/repos/{o}/{r}/issues", params=params)
        return [_parse_issue(item) for item in data]

    async def create_issue(
        self,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        owner: str = "",
        repo: str = "",
    ) -> GitHubIssue:
        """Create a new issue."""
        o, r = self._resolve_owner_repo(owner, repo)
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        data = await self._request("POST", f"/repos/{o}/{r}/issues", json=payload)
        return _parse_issue(data)

    async def update_issue(
        self,
        number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
        owner: str = "",
        repo: str = "",
    ) -> GitHubIssue:
        """Update an existing issue."""
        o, r = self._resolve_owner_repo(owner, repo)
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels
        data = await self._request(
            "PATCH", f"/repos/{o}/{r}/issues/{number}", json=payload
        )
        return _parse_issue(data)

    async def get_issue(
        self, number: int, owner: str = "", repo: str = ""
    ) -> GitHubIssue:
        """Get a single issue by number."""
        o, r = self._resolve_owner_repo(owner, repo)
        data = await self._request("GET", f"/repos/{o}/{r}/issues/{number}")
        return _parse_issue(data)

    # --------------------------------------------------------------------- #
    # Pull Requests
    # --------------------------------------------------------------------- #

    async def list_prs(
        self,
        owner: str = "",
        repo: str = "",
        state: str = "open",
        per_page: int = 30,
    ) -> list[GitHubPR]:
        """List pull requests for a repository."""
        o, r = self._resolve_owner_repo(owner, repo)
        data = await self._request(
            "GET",
            f"/repos/{o}/{r}/pulls",
            params={"state": state, "per_page": per_page},
        )
        return [_parse_pr(pr) for pr in data]

    async def create_pr(
        self,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = False,
        owner: str = "",
        repo: str = "",
    ) -> GitHubPR:
        """Create a new pull request."""
        o, r = self._resolve_owner_repo(owner, repo)
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": draft,
        }
        data = await self._request("POST", f"/repos/{o}/{r}/pulls", json=payload)
        return _parse_pr(data)

    async def get_pr(
        self, number: int, owner: str = "", repo: str = ""
    ) -> GitHubPR:
        """Get a single pull request by number."""
        o, r = self._resolve_owner_repo(owner, repo)
        data = await self._request("GET", f"/repos/{o}/{r}/pulls/{number}")
        return _parse_pr(data)

    # --------------------------------------------------------------------- #
    # Files & Code Search
    # --------------------------------------------------------------------- #

    async def get_file_content(
        self,
        path: str,
        ref: str = "",
        owner: str = "",
        repo: str = "",
    ) -> str:
        """Get decoded file content from a repository."""
        o, r = self._resolve_owner_repo(owner, repo)
        params: dict[str, str] = {}
        if ref:
            params["ref"] = ref
        data = await self._request(
            "GET", f"/repos/{o}/{r}/contents/{path}", params=params
        )
        content_b64 = data.get("content", "")
        return base64.b64decode(content_b64).decode("utf-8")

    async def search_code(
        self,
        query: str,
        owner: str = "",
        repo: str = "",
    ) -> list[dict[str, Any]]:
        """Search code in a repository.

        Returns a list of dicts with ``path``, ``repository``, ``html_url``,
        and ``score`` keys.
        """
        o, r = self._resolve_owner_repo(owner, repo)
        full_query = f"{query} repo:{o}/{r}"
        data = await self._request(
            "GET", "/search/code", params={"q": full_query}
        )
        results: list[dict[str, Any]] = []
        for item in data.get("items", []):
            results.append(
                {
                    "path": item.get("path", ""),
                    "repository": item.get("repository", {}).get("full_name", ""),
                    "html_url": item.get("html_url", ""),
                    "score": item.get("score", 0),
                }
            )
        return results

    # --------------------------------------------------------------------- #
    # Labels
    # --------------------------------------------------------------------- #

    async def list_labels(
        self, owner: str = "", repo: str = ""
    ) -> list[dict[str, Any]]:
        """List labels for a repository."""
        o, r = self._resolve_owner_repo(owner, repo)
        data = await self._request("GET", f"/repos/{o}/{r}/labels")
        return [
            {
                "name": lb.get("name", ""),
                "color": lb.get("color", ""),
                "description": lb.get("description", "") or "",
            }
            for lb in data
        ]

    async def create_label(
        self,
        name: str,
        color: str = "ededed",
        description: str = "",
        owner: str = "",
        repo: str = "",
    ) -> dict[str, Any]:
        """Create a new label."""
        o, r = self._resolve_owner_repo(owner, repo)
        payload = {"name": name, "color": color.lstrip("#"), "description": description}
        data = await self._request("POST", f"/repos/{o}/{r}/labels", json=payload)
        return {
            "name": data.get("name", ""),
            "color": data.get("color", ""),
            "description": data.get("description", "") or "",
        }
