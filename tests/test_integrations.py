"""Tests for JARVIS external service integrations.

All tests run without real API calls -- they exercise models, formatters,
config defaults, dataclass construction, and local-only calendar logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------
from jarvis.integrations.github import (
    GitHubClient,
    GitHubConfig,
    GitHubIssue,
    GitHubPR,
    GitHubRepo,
    _parse_issue,
    _parse_pr,
    _parse_repo,
)


class TestGitHubConfig:
    def test_defaults(self):
        cfg = GitHubConfig()
        assert cfg.token == ""
        assert cfg.base_url == "https://api.github.com"
        assert cfg.default_owner == ""
        assert cfg.default_repo == ""

    def test_custom_values(self):
        cfg = GitHubConfig(
            token="ghp_test",
            base_url="https://ghe.example.com/api/v3",
            default_owner="acme",
            default_repo="widgets",
        )
        assert cfg.token == "ghp_test"
        assert cfg.default_owner == "acme"


class TestGitHubDataclasses:
    def test_issue_creation(self):
        issue = GitHubIssue(number=1, title="Bug")
        assert issue.number == 1
        assert issue.title == "Bug"
        assert issue.state == "open"
        assert issue.labels == []
        assert issue.assignees == []

    def test_issue_with_fields(self):
        issue = GitHubIssue(
            number=42,
            title="Feature request",
            body="Please add X",
            state="closed",
            labels=["enhancement"],
            assignees=["alice"],
            milestone="v1.0",
            html_url="https://github.com/o/r/issues/42",
        )
        assert issue.milestone == "v1.0"
        assert "alice" in issue.assignees

    def test_pr_creation(self):
        pr = GitHubPR(number=10, title="Add feature")
        assert pr.merged is False
        assert pr.draft is False
        assert pr.base == "main"

    def test_pr_with_stats(self):
        pr = GitHubPR(
            number=5,
            title="Refactor",
            additions=100,
            deletions=50,
            changed_files=8,
            merged=True,
        )
        assert pr.additions == 100
        assert pr.merged is True

    def test_repo_creation(self):
        repo = GitHubRepo(full_name="acme/widgets")
        assert repo.default_branch == "main"
        assert repo.topics == []


class TestGitHubParsers:
    def test_parse_issue(self):
        data = {
            "number": 7,
            "title": "Test issue",
            "body": "Description here",
            "state": "open",
            "labels": [{"name": "bug"}, {"name": "p1"}],
            "assignees": [{"login": "bob"}],
            "milestone": {"title": "Sprint 1"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "html_url": "https://github.com/o/r/issues/7",
        }
        issue = _parse_issue(data)
        assert issue.number == 7
        assert issue.labels == ["bug", "p1"]
        assert issue.assignees == ["bob"]
        assert issue.milestone == "Sprint 1"

    def test_parse_issue_minimal(self):
        data = {"number": 1, "title": "Minimal"}
        issue = _parse_issue(data)
        assert issue.labels == []
        assert issue.milestone == ""

    def test_parse_pr(self):
        data = {
            "number": 3,
            "title": "My PR",
            "body": "PR body",
            "state": "open",
            "head": {"ref": "feature-x"},
            "base": {"ref": "main"},
            "merged": False,
            "draft": True,
            "html_url": "https://github.com/o/r/pull/3",
            "additions": 20,
            "deletions": 5,
            "changed_files": 3,
        }
        pr = _parse_pr(data)
        assert pr.head == "feature-x"
        assert pr.draft is True
        assert pr.changed_files == 3

    def test_parse_repo(self):
        data = {
            "full_name": "acme/widgets",
            "description": "Widget library",
            "default_branch": "develop",
            "stargazers_count": 42,
            "forks_count": 10,
            "language": "Python",
            "topics": ["python", "widgets"],
            "html_url": "https://github.com/acme/widgets",
        }
        repo = _parse_repo(data)
        assert repo.stars == 42
        assert repo.language == "Python"
        assert "widgets" in repo.topics


class TestGitHubClient:
    def test_init_default(self):
        client = GitHubClient()
        assert client.config.token == ""
        assert "Accept" in client._headers

    def test_init_with_token(self):
        cfg = GitHubConfig(token="ghp_abc123")
        client = GitHubClient(cfg)
        assert client._headers["Authorization"] == "token ghp_abc123"

    def test_resolve_owner_repo_defaults(self):
        cfg = GitHubConfig(default_owner="acme", default_repo="widgets")
        client = GitHubClient(cfg)
        o, r = client._resolve_owner_repo("", "")
        assert o == "acme"
        assert r == "widgets"

    def test_resolve_owner_repo_override(self):
        cfg = GitHubConfig(default_owner="acme", default_repo="widgets")
        client = GitHubClient(cfg)
        o, r = client._resolve_owner_repo("other", "thing")
        assert o == "other"
        assert r == "thing"

    def test_resolve_owner_repo_missing_raises(self):
        client = GitHubClient()
        with pytest.raises(ValueError, match="owner and repo"):
            client._resolve_owner_repo("", "")

    def test_user_agent_header(self):
        client = GitHubClient()
        assert "JARVIS" in client._headers.get("User-Agent", "")


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
from jarvis.integrations.slack import SlackClient, SlackConfig, SlackMessage


class TestSlackConfig:
    def test_defaults(self):
        cfg = SlackConfig()
        assert cfg.bot_token == ""
        assert cfg.default_channel == "#general"

    def test_custom(self):
        cfg = SlackConfig(bot_token="xoxb-test", default_channel="#alerts")
        assert cfg.bot_token == "xoxb-test"


class TestSlackMessage:
    def test_creation(self):
        msg = SlackMessage(channel="#dev", text="Hello")
        assert msg.username == "JARVIS"
        assert msg.icon_emoji == ":robot_face:"
        assert msg.blocks == []

    def test_with_blocks(self):
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hi"}}]
        msg = SlackMessage(channel="#dev", text="fallback", blocks=blocks)
        assert len(msg.blocks) == 1


class TestSlackFormatting:
    def test_format_spec_update(self):
        spec = {
            "id": "spec-001",
            "title": "Deploy Service",
            "status": "running",
            "steps": [
                {"name": "Build", "status": "completed"},
                {"name": "Test", "status": "running"},
                {"name": "Deploy", "status": "pending"},
            ],
        }
        blocks = SlackClient.format_spec_update(spec)
        assert len(blocks) >= 2
        assert blocks[0]["type"] == "header"
        assert "Deploy Service" in blocks[0]["text"]["text"]
        # Steps block
        steps_block = blocks[-1]
        assert "Steps" in steps_block["text"]["text"]
        assert "Build" in steps_block["text"]["text"]

    def test_format_spec_update_no_steps(self):
        spec = {"id": "s1", "title": "Empty", "status": "pending"}
        blocks = SlackClient.format_spec_update(spec)
        assert len(blocks) == 2  # header + status, no steps block

    def test_format_agent_result_success(self):
        result = {
            "agent": "CodeGen",
            "status": "success",
            "output": "Generated 3 files",
            "duration_seconds": 12.5,
        }
        blocks = SlackClient.format_agent_result(result)
        assert blocks[0]["text"]["text"] == "Agent Result: CodeGen"
        assert any("12.5s" in str(b) for b in blocks)

    def test_format_agent_result_no_output(self):
        result = {"agent": "Lint", "status": "failed", "duration_seconds": 0.1}
        blocks = SlackClient.format_agent_result(result)
        # Should have header + fields but no output block
        assert len(blocks) == 2

    def test_format_notification(self):
        notif = {
            "title": "Build Complete",
            "message": "All tests passed",
            "level": "success",
            "url": "https://ci.example.com/build/42",
        }
        blocks = SlackClient.format_notification(notif)
        assert len(blocks) == 3  # header + message + link
        assert "View Details" in blocks[2]["text"]["text"]

    def test_format_notification_no_url(self):
        notif = {"title": "Info", "message": "FYI", "level": "info"}
        blocks = SlackClient.format_notification(notif)
        assert len(blocks) == 2


# ---------------------------------------------------------------------------
# Jira
# ---------------------------------------------------------------------------
from jarvis.integrations.jira import (
    JiraClient,
    JiraConfig,
    JiraIssue,
    _parse_issue as jira_parse_issue,
    build_jql,
)


class TestJiraConfig:
    def test_defaults(self):
        cfg = JiraConfig()
        assert cfg.base_url == ""
        assert cfg.default_project == ""

    def test_custom(self):
        cfg = JiraConfig(
            base_url="https://jira.example.com",
            email="user@example.com",
            api_token="token",
            default_project="PROJ",
        )
        assert cfg.default_project == "PROJ"


class TestJiraIssue:
    def test_defaults(self):
        issue = JiraIssue(summary="Task")
        assert issue.key == ""
        assert issue.issue_type == "Task"
        assert issue.status == "To Do"
        assert issue.priority == "Medium"
        assert issue.story_points is None

    def test_full(self):
        issue = JiraIssue(
            key="PROJ-42",
            summary="Fix login",
            description="Login is broken",
            issue_type="Bug",
            status="In Progress",
            priority="High",
            labels=["urgent"],
            story_points=3.0,
        )
        assert issue.key == "PROJ-42"
        assert issue.story_points == 3.0


class TestJiraParsing:
    def test_parse_issue(self):
        data = {
            "key": "TEST-1",
            "fields": {
                "summary": "Test task",
                "description": "Do the thing",
                "issuetype": {"name": "Story"},
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "Alice"},
                "labels": ["backend"],
                "story_points": 5,
            },
        }
        issue = jira_parse_issue(data)
        assert issue.key == "TEST-1"
        assert issue.issue_type == "Story"
        assert issue.assignee == "Alice"
        assert "backend" in issue.labels

    def test_parse_issue_minimal(self):
        data = {"key": "X-1", "fields": {"summary": "Minimal"}}
        issue = jira_parse_issue(data)
        assert issue.summary == "Minimal"
        assert issue.assignee == ""


class TestBuildJql:
    def test_empty(self):
        jql = build_jql()
        assert jql == "ORDER BY created DESC"

    def test_project_only(self):
        jql = build_jql(project="PROJ")
        assert jql == 'project = "PROJ"'

    def test_multiple_criteria(self):
        jql = build_jql(project="PROJ", status="In Progress", assignee="alice")
        assert 'project = "PROJ"' in jql
        assert 'status = "In Progress"' in jql
        assert 'assignee = "alice"' in jql
        assert " AND " in jql

    def test_labels(self):
        jql = build_jql(labels=["bug", "urgent"])
        assert 'labels = "bug"' in jql
        assert 'labels = "urgent"' in jql

    def test_text_search(self):
        jql = build_jql(text="login error")
        assert 'text ~ "login error"' in jql


class TestJiraClient:
    def test_init(self):
        client = JiraClient()
        assert client.config.base_url == ""

    def test_resolve_project_default(self):
        cfg = JiraConfig(default_project="DEV")
        client = JiraClient(cfg)
        assert client._resolve_project("") == "DEV"

    def test_resolve_project_override(self):
        cfg = JiraConfig(default_project="DEV")
        client = JiraClient(cfg)
        assert client._resolve_project("OPS") == "OPS"

    def test_resolve_project_missing_raises(self):
        client = JiraClient()
        with pytest.raises(ValueError, match="project must be provided"):
            client._resolve_project("")

    def test_url_building(self):
        cfg = JiraConfig(base_url="https://jira.example.com")
        client = JiraClient(cfg)
        assert client._url("/issue/X-1") == "https://jira.example.com/rest/api/3/issue/X-1"
        assert "/agile/1.0/" in client._agile_url("/board/1/sprint")


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
from jarvis.integrations.webhook import WebhookClient, WebhookConfig


class TestWebhookConfig:
    def test_defaults(self):
        cfg = WebhookConfig()
        assert cfg.method == "POST"
        assert cfg.retry_count == 3
        assert cfg.timeout_seconds == 10
        assert cfg.auth_type == ""

    def test_custom(self):
        cfg = WebhookConfig(
            url="https://hooks.example.com/x",
            auth_type="bearer",
            auth_token="tok",
        )
        assert cfg.url == "https://hooks.example.com/x"


class TestWebhookClient:
    def test_build_headers_no_auth(self):
        client = WebhookClient()
        headers = client._build_headers(WebhookConfig())
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_bearer(self):
        cfg = WebhookConfig(auth_type="bearer", auth_token="mytoken")
        client = WebhookClient()
        headers = client._build_headers(cfg)
        assert headers["Authorization"] == "Bearer mytoken"

    def test_build_headers_basic(self):
        cfg = WebhookConfig(auth_type="basic", auth_token="user:pass")
        client = WebhookClient()
        headers = client._build_headers(cfg)
        assert headers["Authorization"].startswith("Basic ")

    def test_build_headers_custom(self):
        cfg = WebhookConfig(headers={"X-Custom": "val"})
        client = WebhookClient()
        headers = client._build_headers(cfg)
        assert headers["X-Custom"] == "val"

    @pytest.mark.asyncio
    async def test_send_no_url_raises(self):
        client = WebhookClient()
        with pytest.raises(ValueError, match="URL is not configured"):
            await client.send({"key": "value"})


class TestWebhookFormatters:
    def test_format_for_discord(self):
        payload = WebhookClient.format_for_discord("Title", "Desc", color=0xFF0000)
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert embed["title"] == "Title"
        assert embed["description"] == "Desc"
        assert embed["color"] == 0xFF0000

    def test_format_for_discord_default_color(self):
        payload = WebhookClient.format_for_discord("T", "D")
        assert payload["embeds"][0]["color"] == 0x3B82F6

    def test_format_for_teams(self):
        payload = WebhookClient.format_for_teams("Alert", "Something happened")
        assert payload["@type"] == "MessageCard"
        assert payload["title"] == "Alert"
        assert payload["sections"][0]["text"] == "Something happened"

    def test_format_for_dingtalk(self):
        payload = WebhookClient.format_for_dingtalk("Deploy", "v2.0 released")
        assert payload["msgtype"] == "markdown"
        assert "Deploy" in payload["markdown"]["title"]
        assert "v2.0 released" in payload["markdown"]["text"]

    def test_format_for_feishu(self):
        payload = WebhookClient.format_for_feishu("Update", "New version")
        assert payload["msg_type"] == "interactive"
        card = payload["card"]
        assert card["header"]["title"]["content"] == "Update"
        assert card["elements"][0]["content"] == "New version"


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
from jarvis.integrations.calendar_service import CalendarEvent, CalendarService


class TestCalendarEvent:
    def test_defaults(self):
        ev = CalendarEvent(title="Meeting")
        assert ev.id == ""
        assert ev.attendees == []
        assert ev.all_day is False
        assert ev.reminders == []

    def test_full(self):
        now = datetime(2024, 6, 15, 10, 0)
        ev = CalendarEvent(
            id="evt-1",
            title="Sprint Planning",
            description="Plan the sprint",
            start_time=now,
            end_time=now + timedelta(hours=1),
            location="Room 42",
            attendees=["alice", "bob"],
            reminders=[15, 5],
            all_day=False,
        )
        assert ev.location == "Room 42"
        assert len(ev.attendees) == 2


class TestCalendarService:
    @pytest.fixture
    def service(self):
        return CalendarService()

    @pytest.fixture
    def base_time(self):
        return datetime(2024, 6, 15, 9, 0)

    @pytest.mark.asyncio
    async def test_create_event(self, service, base_time):
        ev = CalendarEvent(
            title="Standup",
            start_time=base_time,
            end_time=base_time + timedelta(minutes=15),
        )
        created = await service.create_event(ev)
        assert created.id != ""
        assert created.title == "Standup"
        assert len(service._events) == 1

    @pytest.mark.asyncio
    async def test_create_event_preserves_id(self, service, base_time):
        ev = CalendarEvent(
            id="custom-id",
            title="Custom",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
        )
        created = await service.create_event(ev)
        assert created.id == "custom-id"

    @pytest.mark.asyncio
    async def test_get_events(self, service, base_time):
        # Create events at 9:00, 11:00, 14:00
        for hour_offset in [0, 2, 5]:
            start = base_time + timedelta(hours=hour_offset)
            ev = CalendarEvent(
                title=f"Event at {start.hour}",
                start_time=start,
                end_time=start + timedelta(hours=1),
            )
            await service.create_event(ev)

        # Query 10:00-15:00 should find 11:00 and 14:00 events
        results = await service.get_events(
            base_time + timedelta(hours=1),
            base_time + timedelta(hours=6),
        )
        assert len(results) == 2
        assert results[0].title == "Event at 11"

    @pytest.mark.asyncio
    async def test_get_events_empty(self, service, base_time):
        results = await service.get_events(base_time, base_time + timedelta(hours=1))
        assert results == []

    @pytest.mark.asyncio
    async def test_update_event(self, service, base_time):
        ev = CalendarEvent(
            title="Original",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
        )
        created = await service.create_event(ev)
        updated = await service.update_event(
            created.id, title="Updated", location="Room A"
        )
        assert updated.title == "Updated"
        assert updated.location == "Room A"

    @pytest.mark.asyncio
    async def test_update_event_not_found(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.update_event("nonexistent", title="X")

    @pytest.mark.asyncio
    async def test_delete_event(self, service, base_time):
        ev = CalendarEvent(
            title="To delete",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
        )
        created = await service.create_event(ev)
        assert await service.delete_event(created.id) is True
        assert len(service._events) == 0

    @pytest.mark.asyncio
    async def test_delete_event_not_found(self, service):
        assert await service.delete_event("nope") is False

    @pytest.mark.asyncio
    async def test_find_conflicts(self, service, base_time):
        ev = CalendarEvent(
            title="Meeting",
            start_time=base_time,
            end_time=base_time + timedelta(hours=2),
        )
        await service.create_event(ev)

        # Overlapping
        conflicts = await service.find_conflicts(
            base_time + timedelta(hours=1),
            base_time + timedelta(hours=3),
        )
        assert len(conflicts) == 1

        # Non-overlapping
        conflicts = await service.find_conflicts(
            base_time + timedelta(hours=3),
            base_time + timedelta(hours=4),
        )
        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_find_free_slots_empty_day(self, service):
        day = datetime(2024, 6, 15, 12, 0)
        slots = await service.find_free_slots(day, duration_minutes=60)
        # Entire work day should be one big free slot (9-18)
        assert len(slots) == 1
        assert slots[0][0].hour == 9
        assert slots[0][1].hour == 18

    @pytest.mark.asyncio
    async def test_find_free_slots_with_events(self, service):
        day = datetime(2024, 6, 15, 12, 0)
        # Event from 10:00-11:00
        ev1 = CalendarEvent(
            title="Morning meeting",
            start_time=day.replace(hour=10, minute=0),
            end_time=day.replace(hour=11, minute=0),
        )
        # Event from 14:00-15:00
        ev2 = CalendarEvent(
            title="Afternoon meeting",
            start_time=day.replace(hour=14, minute=0),
            end_time=day.replace(hour=15, minute=0),
        )
        await service.create_event(ev1)
        await service.create_event(ev2)

        slots = await service.find_free_slots(day, duration_minutes=60)
        # Should have: 9-10, 11-14, 15-18
        assert len(slots) == 3
        assert slots[0][0].hour == 9
        assert slots[0][1].hour == 10
        assert slots[1][0].hour == 11
        assert slots[1][1].hour == 14
        assert slots[2][0].hour == 15
        assert slots[2][1].hour == 18

    @pytest.mark.asyncio
    async def test_find_free_slots_no_room(self, service):
        day = datetime(2024, 6, 15, 12, 0)
        # Block entire work day
        ev = CalendarEvent(
            title="All day",
            start_time=day.replace(hour=9),
            end_time=day.replace(hour=18),
        )
        await service.create_event(ev)
        slots = await service.find_free_slots(day, duration_minutes=60)
        assert len(slots) == 0

    @pytest.mark.asyncio
    async def test_search_events(self, service, base_time):
        ev1 = CalendarEvent(
            title="Sprint Planning",
            description="Plan work",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
        )
        ev2 = CalendarEvent(
            title="Code Review",
            description="Review sprint PRs",
            start_time=base_time + timedelta(hours=2),
            end_time=base_time + timedelta(hours=3),
        )
        await service.create_event(ev1)
        await service.create_event(ev2)

        # Search by title
        results = await service.search_events("sprint")
        assert len(results) == 2  # both contain "sprint"

        # Search by description
        results = await service.search_events("plan work")
        assert len(results) == 1
        assert results[0].title == "Sprint Planning"

        # No match
        results = await service.search_events("vacation")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, service, base_time):
        ev = CalendarEvent(
            title="IMPORTANT Meeting",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
        )
        await service.create_event(ev)
        results = await service.search_events("important")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Integration imports (smoke test)
# ---------------------------------------------------------------------------


class TestIntegrationExports:
    def test_all_exports(self):
        from jarvis.integrations import __all__

        expected = {
            "GitHubClient",
            "GitHubConfig",
            "GitHubIssue",
            "GitHubPR",
            "GitHubRepo",
            "SlackClient",
            "SlackConfig",
            "SlackMessage",
            "JiraClient",
            "JiraConfig",
            "JiraIssue",
            "build_jql",
            "WebhookClient",
            "WebhookConfig",
            "CalendarEvent",
            "CalendarService",
        }
        assert set(__all__) == expected

    def test_imports(self):
        from jarvis.integrations import (
            CalendarEvent,
            CalendarService,
            GitHubClient,
            GitHubConfig,
            JiraClient,
            SlackClient,
            WebhookClient,
            build_jql,
        )

        # Verify they are classes/functions
        assert callable(GitHubClient)
        assert callable(SlackClient)
        assert callable(JiraClient)
        assert callable(WebhookClient)
        assert callable(CalendarService)
        assert callable(build_jql)
