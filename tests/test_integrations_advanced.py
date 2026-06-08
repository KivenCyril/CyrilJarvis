"""Advanced integration tests for external service clients.

Tests GitHub, Slack, Jira, Calendar, and Webhook integrations
using mock data and dataclass validation.
"""

from __future__ import annotations

import json
import datetime
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# GitHub Integration Dataclasses & Tests
# ---------------------------------------------------------------------------

@dataclass
class GitHubRepository:
    owner: str
    name: str
    full_name: str = ""
    description: str = ""
    language: str = ""
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    is_private: bool = False
    default_branch: str = "main"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.full_name:
            self.full_name = f"{self.owner}/{self.name}"


@dataclass
class GitHubPullRequest:
    number: int
    title: str
    body: str = ""
    state: str = "open"
    author: str = ""
    base_branch: str = "main"
    head_branch: str = ""
    labels: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    is_draft: bool = False
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    mergeable: bool = True
    created_at: str = ""

    @property
    def is_large(self) -> bool:
        return self.additions + self.deletions > 500

    @property
    def summary(self) -> str:
        return f"PR #{self.number}: {self.title} ({self.state})"


@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str = ""
    state: str = "open"
    author: str = ""
    assignees: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    milestone: str | None = None
    comments_count: int = 0
    is_pull_request: bool = False


@dataclass
class GitHubCommit:
    sha: str
    message: str
    author: str = ""
    date: str = ""
    additions: int = 0
    deletions: int = 0
    files_changed: list[str] = field(default_factory=list)

    @property
    def short_sha(self) -> str:
        return self.sha[:7]


class TestGitHubRepository:
    def test_create_repo(self):
        repo = GitHubRepository(owner="test", name="project")
        assert repo.full_name == "test/project"
        assert repo.default_branch == "main"
        assert repo.stars == 0

    def test_repo_auto_full_name(self):
        repo = GitHubRepository(owner="org", name="lib")
        assert repo.full_name == "org/lib"

    def test_repo_with_all_fields(self):
        repo = GitHubRepository(
            owner="org", name="api", description="REST API",
            language="Python", stars=100, forks=20, open_issues=5,
            is_private=True, default_branch="develop",
        )
        assert repo.is_private is True
        assert repo.language == "Python"
        assert repo.stars == 100

    def test_repo_custom_full_name(self):
        repo = GitHubRepository(owner="a", name="b", full_name="custom/name")
        assert repo.full_name == "custom/name"


class TestGitHubPullRequest:
    def test_create_pr(self):
        pr = GitHubPullRequest(number=42, title="Fix bug")
        assert pr.summary == "PR #42: Fix bug (open)"
        assert pr.is_large is False

    def test_large_pr(self):
        pr = GitHubPullRequest(number=1, title="Refactor", additions=300, deletions=250)
        assert pr.is_large is True

    def test_small_pr(self):
        pr = GitHubPullRequest(number=2, title="Typo", additions=1, deletions=1)
        assert pr.is_large is False

    def test_pr_with_reviewers(self):
        pr = GitHubPullRequest(
            number=10, title="Feature",
            reviewers=["alice", "bob"],
            labels=["enhancement"],
        )
        assert len(pr.reviewers) == 2
        assert "enhancement" in pr.labels

    def test_pr_draft(self):
        pr = GitHubPullRequest(number=5, title="WIP", is_draft=True)
        assert pr.is_draft is True

    def test_pr_closed(self):
        pr = GitHubPullRequest(number=99, title="Done", state="closed")
        assert pr.summary == "PR #99: Done (closed)"

    def test_pr_mergeable(self):
        pr = GitHubPullRequest(number=3, title="Merge", mergeable=True)
        assert pr.mergeable is True


class TestGitHubIssue:
    def test_create_issue(self):
        issue = GitHubIssue(number=1, title="Bug report")
        assert issue.state == "open"
        assert issue.comments_count == 0

    def test_issue_with_labels(self):
        issue = GitHubIssue(
            number=2, title="Feature", labels=["enhancement", "v2"],
        )
        assert len(issue.labels) == 2

    def test_issue_with_assignees(self):
        issue = GitHubIssue(
            number=3, title="Task",
            assignees=["alice", "bob", "charlie"],
        )
        assert len(issue.assignees) == 3

    def test_issue_with_milestone(self):
        issue = GitHubIssue(number=4, title="Milestone", milestone="v1.0")
        assert issue.milestone == "v1.0"


class TestGitHubCommit:
    def test_short_sha(self):
        commit = GitHubCommit(sha="abc1234567890", message="Fix bug")
        assert commit.short_sha == "abc1234"

    def test_commit_with_stats(self):
        commit = GitHubCommit(
            sha="def456", message="Refactor",
            additions=50, deletions=30,
            files_changed=["a.py", "b.py"],
        )
        assert len(commit.files_changed) == 2
        assert commit.additions == 50


# ---------------------------------------------------------------------------
# Slack Message Formatting
# ---------------------------------------------------------------------------

@dataclass
class SlackMessage:
    channel: str
    text: str
    blocks: list[dict] = field(default_factory=list)
    thread_ts: str | None = None
    username: str = "JARVIS"
    icon_emoji: str = ":robot_face:"
    unfurl_links: bool = False

    def to_payload(self) -> dict:
        payload = {
            "channel": self.channel,
            "text": self.text,
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "unfurl_links": self.unfurl_links,
        }
        if self.blocks:
            payload["blocks"] = self.blocks
        if self.thread_ts:
            payload["thread_ts"] = self.thread_ts
        return payload

    @staticmethod
    def format_code_block(code: str, language: str = "") -> str:
        return f"```{language}\n{code}\n```"

    @staticmethod
    def format_mention(user_id: str) -> str:
        return f"<@{user_id}>"

    @staticmethod
    def format_link(url: str, text: str = "") -> str:
        if text:
            return f"<{url}|{text}>"
        return f"<{url}>"

    def add_section(self, text: str) -> None:
        self.blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        })

    def add_divider(self) -> None:
        self.blocks.append({"type": "divider"})

    def add_header(self, text: str) -> None:
        self.blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": text},
        })


class TestSlackMessage:
    def test_basic_message(self):
        msg = SlackMessage(channel="#general", text="Hello")
        payload = msg.to_payload()
        assert payload["channel"] == "#general"
        assert payload["text"] == "Hello"
        assert payload["username"] == "JARVIS"

    def test_message_with_blocks(self):
        msg = SlackMessage(channel="#dev", text="Update")
        msg.add_header("Status Report")
        msg.add_section("All systems operational")
        msg.add_divider()
        msg.add_section("No issues found")
        payload = msg.to_payload()
        assert len(payload["blocks"]) == 4

    def test_thread_reply(self):
        msg = SlackMessage(
            channel="#dev", text="Reply",
            thread_ts="1234567890.123456",
        )
        payload = msg.to_payload()
        assert payload["thread_ts"] == "1234567890.123456"

    def test_code_block_formatting(self):
        code = SlackMessage.format_code_block("print('hello')", "python")
        assert code == "```python\nprint('hello')\n```"

    def test_mention_formatting(self):
        mention = SlackMessage.format_mention("U12345")
        assert mention == "<@U12345>"

    def test_link_formatting(self):
        link = SlackMessage.format_link("https://example.com", "Example")
        assert link == "<https://example.com|Example>"

    def test_link_without_text(self):
        link = SlackMessage.format_link("https://example.com")
        assert link == "<https://example.com>"

    def test_custom_icon(self):
        msg = SlackMessage(
            channel="#alerts", text="Alert",
            icon_emoji=":warning:",
        )
        assert msg.to_payload()["icon_emoji"] == ":warning:"


# ---------------------------------------------------------------------------
# Jira Issue Lifecycle
# ---------------------------------------------------------------------------

@dataclass
class JiraIssue:
    key: str
    summary: str
    description: str = ""
    issue_type: str = "Task"
    status: str = "To Do"
    priority: str = "Medium"
    assignee: str | None = None
    reporter: str = ""
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    story_points: float | None = None
    sprint: str | None = None
    epic_key: str | None = None
    created_at: str = ""
    updated_at: str = ""
    transitions: list[str] = field(default_factory=list)

    def transition_to(self, new_status: str) -> None:
        self.transitions.append(f"{self.status} -> {new_status}")
        self.status = new_status

    @property
    def is_done(self) -> bool:
        return self.status.lower() in ("done", "closed", "resolved")

    @property
    def is_blocked(self) -> bool:
        return self.status.lower() in ("blocked", "on hold")

    def add_label(self, label: str) -> None:
        if label not in self.labels:
            self.labels.append(label)

    def assign_to(self, user: str) -> None:
        self.assignee = user


class TestJiraIssue:
    def test_create_issue(self):
        issue = JiraIssue(key="PROJ-1", summary="Fix login bug")
        assert issue.status == "To Do"
        assert issue.is_done is False

    def test_transition(self):
        issue = JiraIssue(key="PROJ-2", summary="Feature X")
        issue.transition_to("In Progress")
        assert issue.status == "In Progress"
        issue.transition_to("Done")
        assert issue.is_done is True
        assert len(issue.transitions) == 2

    def test_transition_history(self):
        issue = JiraIssue(key="PROJ-3", summary="Task")
        issue.transition_to("In Progress")
        issue.transition_to("In Review")
        issue.transition_to("Done")
        assert issue.transitions == [
            "To Do -> In Progress",
            "In Progress -> In Review",
            "In Review -> Done",
        ]

    def test_blocked(self):
        issue = JiraIssue(key="PROJ-4", summary="Blocked")
        issue.transition_to("Blocked")
        assert issue.is_blocked is True

    def test_add_labels(self):
        issue = JiraIssue(key="PROJ-5", summary="Labels")
        issue.add_label("frontend")
        issue.add_label("urgent")
        issue.add_label("frontend")  # duplicate
        assert issue.labels == ["frontend", "urgent"]

    def test_assign(self):
        issue = JiraIssue(key="PROJ-6", summary="Assign")
        issue.assign_to("alice")
        assert issue.assignee == "alice"

    def test_story_points(self):
        issue = JiraIssue(key="PROJ-7", summary="Points", story_points=5)
        assert issue.story_points == 5

    def test_epic_link(self):
        issue = JiraIssue(key="PROJ-8", summary="Sub", epic_key="PROJ-EPIC-1")
        assert issue.epic_key == "PROJ-EPIC-1"


# ---------------------------------------------------------------------------
# Calendar Conflict Detection
# ---------------------------------------------------------------------------

@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime.datetime
    end: datetime.datetime
    attendees: list[str] = field(default_factory=list)
    location: str = ""
    is_all_day: bool = False
    recurrence: str | None = None  # daily, weekly, monthly
    organizer: str = ""
    status: str = "confirmed"  # confirmed, tentative, cancelled

    @property
    def duration_minutes(self) -> int:
        delta = self.end - self.start
        return int(delta.total_seconds() / 60)

    def conflicts_with(self, other: "CalendarEvent") -> bool:
        if self.status == "cancelled" or other.status == "cancelled":
            return False
        return self.start < other.end and other.start < self.end

    def overlapping_attendees(self, other: "CalendarEvent") -> list[str]:
        return list(set(self.attendees) & set(other.attendees))


def find_conflicts(events: list[CalendarEvent]) -> list[tuple[CalendarEvent, CalendarEvent]]:
    conflicts = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if events[i].conflicts_with(events[j]):
                conflicts.append((events[i], events[j]))
    return conflicts


def find_free_slots(
    events: list[CalendarEvent],
    day_start: datetime.datetime,
    day_end: datetime.datetime,
    min_duration_minutes: int = 30,
) -> list[tuple[datetime.datetime, datetime.datetime]]:
    sorted_events = sorted(
        [e for e in events if e.status != "cancelled"],
        key=lambda e: e.start,
    )
    free_slots = []
    current = day_start
    for event in sorted_events:
        if event.start > current:
            gap = (event.start - current).total_seconds() / 60
            if gap >= min_duration_minutes:
                free_slots.append((current, event.start))
        if event.end > current:
            current = event.end
    if day_end > current:
        gap = (day_end - current).total_seconds() / 60
        if gap >= min_duration_minutes:
            free_slots.append((current, day_end))
    return free_slots


class TestCalendarEvent:
    def test_duration(self):
        event = CalendarEvent(
            id="1", title="Meeting",
            start=datetime.datetime(2025, 6, 1, 10, 0),
            end=datetime.datetime(2025, 6, 1, 11, 0),
        )
        assert event.duration_minutes == 60

    def test_conflict_detection(self):
        e1 = CalendarEvent(
            id="1", title="A",
            start=datetime.datetime(2025, 6, 1, 10, 0),
            end=datetime.datetime(2025, 6, 1, 11, 0),
        )
        e2 = CalendarEvent(
            id="2", title="B",
            start=datetime.datetime(2025, 6, 1, 10, 30),
            end=datetime.datetime(2025, 6, 1, 11, 30),
        )
        assert e1.conflicts_with(e2) is True

    def test_no_conflict(self):
        e1 = CalendarEvent(
            id="1", title="A",
            start=datetime.datetime(2025, 6, 1, 10, 0),
            end=datetime.datetime(2025, 6, 1, 11, 0),
        )
        e2 = CalendarEvent(
            id="2", title="B",
            start=datetime.datetime(2025, 6, 1, 11, 0),
            end=datetime.datetime(2025, 6, 1, 12, 0),
        )
        assert e1.conflicts_with(e2) is False

    def test_cancelled_no_conflict(self):
        e1 = CalendarEvent(
            id="1", title="A",
            start=datetime.datetime(2025, 6, 1, 10, 0),
            end=datetime.datetime(2025, 6, 1, 11, 0),
            status="cancelled",
        )
        e2 = CalendarEvent(
            id="2", title="B",
            start=datetime.datetime(2025, 6, 1, 10, 0),
            end=datetime.datetime(2025, 6, 1, 11, 0),
        )
        assert e1.conflicts_with(e2) is False

    def test_overlapping_attendees(self):
        e1 = CalendarEvent(
            id="1", title="A",
            start=datetime.datetime(2025, 6, 1, 10, 0),
            end=datetime.datetime(2025, 6, 1, 11, 0),
            attendees=["alice", "bob"],
        )
        e2 = CalendarEvent(
            id="2", title="B",
            start=datetime.datetime(2025, 6, 1, 10, 0),
            end=datetime.datetime(2025, 6, 1, 11, 0),
            attendees=["bob", "charlie"],
        )
        assert e1.overlapping_attendees(e2) == ["bob"]

    def test_find_conflicts(self):
        events = [
            CalendarEvent(
                id="1", title="A",
                start=datetime.datetime(2025, 6, 1, 9, 0),
                end=datetime.datetime(2025, 6, 1, 10, 0),
            ),
            CalendarEvent(
                id="2", title="B",
                start=datetime.datetime(2025, 6, 1, 9, 30),
                end=datetime.datetime(2025, 6, 1, 10, 30),
            ),
            CalendarEvent(
                id="3", title="C",
                start=datetime.datetime(2025, 6, 1, 11, 0),
                end=datetime.datetime(2025, 6, 1, 12, 0),
            ),
        ]
        conflicts = find_conflicts(events)
        assert len(conflicts) == 1
        assert conflicts[0][0].title == "A"
        assert conflicts[0][1].title == "B"

    def test_find_free_slots(self):
        events = [
            CalendarEvent(
                id="1", title="A",
                start=datetime.datetime(2025, 6, 1, 9, 0),
                end=datetime.datetime(2025, 6, 1, 10, 0),
            ),
            CalendarEvent(
                id="2", title="B",
                start=datetime.datetime(2025, 6, 1, 11, 0),
                end=datetime.datetime(2025, 6, 1, 12, 0),
            ),
        ]
        day_start = datetime.datetime(2025, 6, 1, 8, 0)
        day_end = datetime.datetime(2025, 6, 1, 17, 0)
        slots = find_free_slots(events, day_start, day_end)
        assert len(slots) == 3  # 8-9, 10-11, 12-17

    def test_find_free_slots_min_duration(self):
        events = [
            CalendarEvent(
                id="1", title="A",
                start=datetime.datetime(2025, 6, 1, 9, 0),
                end=datetime.datetime(2025, 6, 1, 9, 50),
            ),
            CalendarEvent(
                id="2", title="B",
                start=datetime.datetime(2025, 6, 1, 10, 0),
                end=datetime.datetime(2025, 6, 1, 11, 0),
            ),
        ]
        day_start = datetime.datetime(2025, 6, 1, 8, 0)
        day_end = datetime.datetime(2025, 6, 1, 12, 0)
        # 10 min gap between A and B should be excluded with 30 min minimum
        slots = find_free_slots(events, day_start, day_end, min_duration_minutes=30)
        assert len(slots) == 2  # 8-9, 11-12


# ---------------------------------------------------------------------------
# Webhook Formatting
# ---------------------------------------------------------------------------

@dataclass
class WebhookPayload:
    event_type: str
    source: str
    timestamp: str
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
        }, indent=2)

    @staticmethod
    def for_github(event: str, repo: str, data: dict) -> "WebhookPayload":
        return WebhookPayload(
            event_type=f"github.{event}",
            source="github",
            timestamp=datetime.datetime.utcnow().isoformat(),
            data={"repository": repo, **data},
        )

    @staticmethod
    def for_slack(event: str, channel: str, data: dict) -> "WebhookPayload":
        return WebhookPayload(
            event_type=f"slack.{event}",
            source="slack",
            timestamp=datetime.datetime.utcnow().isoformat(),
            data={"channel": channel, **data},
        )

    @staticmethod
    def for_jira(event: str, project: str, data: dict) -> "WebhookPayload":
        return WebhookPayload(
            event_type=f"jira.{event}",
            source="jira",
            timestamp=datetime.datetime.utcnow().isoformat(),
            data={"project": project, **data},
        )

    @staticmethod
    def for_generic(event: str, source: str, data: dict) -> "WebhookPayload":
        return WebhookPayload(
            event_type=event,
            source=source,
            timestamp=datetime.datetime.utcnow().isoformat(),
            data=data,
        )


class TestWebhookPayload:
    def test_basic_payload(self):
        p = WebhookPayload(
            event_type="test", source="unit-test",
            timestamp="2025-06-01T00:00:00Z",
        )
        result = json.loads(p.to_json())
        assert result["event_type"] == "test"

    def test_github_webhook(self):
        p = WebhookPayload.for_github(
            "push", "org/repo", {"ref": "refs/heads/main"},
        )
        assert p.event_type == "github.push"
        assert p.source == "github"
        assert p.data["repository"] == "org/repo"

    def test_slack_webhook(self):
        p = WebhookPayload.for_slack(
            "message", "#general", {"text": "Hello"},
        )
        assert p.event_type == "slack.message"
        assert p.data["channel"] == "#general"

    def test_jira_webhook(self):
        p = WebhookPayload.for_jira(
            "issue_created", "PROJ",
            {"key": "PROJ-1", "summary": "New task"},
        )
        assert p.event_type == "jira.issue_created"
        assert p.data["project"] == "PROJ"

    def test_generic_webhook(self):
        p = WebhookPayload.for_generic(
            "custom.event", "my-service",
            {"action": "deploy", "version": "1.0"},
        )
        assert p.event_type == "custom.event"
        assert p.source == "my-service"

    def test_payload_serialization(self):
        p = WebhookPayload(
            event_type="test", source="test",
            timestamp="2025-01-01T00:00:00Z",
            data={"key": "value"},
            metadata={"attempt": 1},
        )
        result = json.loads(p.to_json())
        assert result["data"]["key"] == "value"
        assert result["metadata"]["attempt"] == 1

    def test_payload_with_nested_data(self):
        p = WebhookPayload.for_github(
            "pull_request", "org/repo",
            {
                "action": "opened",
                "pull_request": {
                    "number": 1,
                    "title": "Feature",
                    "labels": ["enhancement"],
                },
            },
        )
        assert p.data["pull_request"]["number"] == 1
