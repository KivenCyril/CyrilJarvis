"""Comprehensive API endpoint tests.

Covers all 60+ endpoints including workflows, events, notifications,
user profile, diagnostics, and templates.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from jarvis.server.app import app, jarvis


@pytest.fixture
async def client():
    await jarvis.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Health & System
# ---------------------------------------------------------------------------

class TestHealthAndSystem:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "agents" in data
        assert "specs" in data
        assert "agent_specs" in data

    @pytest.mark.asyncio
    async def test_system_info(self, client: AsyncClient):
        resp = await client.get("/system")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app_name"] == "JARVIS"
        assert "version" in data
        assert "modules" in data
        assert data["modules"]["agents"] is True
        assert data["modules"]["tools"] is True

    @pytest.mark.asyncio
    async def test_system_has_agent_count(self, client: AsyncClient):
        resp = await client.get("/system")
        data = resp.json()
        assert data["agents"] >= 1

    @pytest.mark.asyncio
    async def test_system_version_format(self, client: AsyncClient):
        resp = await client.get("/system")
        data = resp.json()
        parts = data["version"].split(".")
        assert len(parts) == 3


# ---------------------------------------------------------------------------
# Agent Endpoints
# ---------------------------------------------------------------------------

class TestAgentEndpoints:
    @pytest.mark.asyncio
    async def test_list_agents(self, client: AsyncClient):
        resp = await client.get("/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert isinstance(agents, list)
        assert len(agents) >= 1

    @pytest.mark.asyncio
    async def test_agent_has_required_fields(self, client: AsyncClient):
        resp = await client.get("/agents")
        agent = resp.json()[0]
        assert "name" in agent
        assert "description" in agent
        assert "skills" in agent
        assert "domain" in agent
        assert "status" in agent

    @pytest.mark.asyncio
    async def test_get_specific_agent(self, client: AsyncClient):
        resp = await client.get("/agents")
        first_name = resp.json()[0]["name"]
        resp2 = await client.get(f"/agents/{first_name}")
        assert resp2.status_code == 200
        assert resp2.json()["name"] == first_name

    @pytest.mark.asyncio
    async def test_get_agent_extra_fields(self, client: AsyncClient):
        resp = await client.get("/agents")
        first_name = resp.json()[0]["name"]
        resp2 = await client.get(f"/agents/{first_name}")
        data = resp2.json()
        assert "can_delegate" in data
        assert "version" in data

    @pytest.mark.asyncio
    async def test_agent_not_found(self, client: AsyncClient):
        resp = await client.get("/agents/nonexistent-agent-xyz")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_list_returns_consistent_results(self, client: AsyncClient):
        resp1 = await client.get("/agents")
        resp2 = await client.get("/agents")
        assert resp1.json() == resp2.json()


# ---------------------------------------------------------------------------
# Spec Endpoints
# ---------------------------------------------------------------------------

class TestSpecEndpoints:
    @pytest.mark.asyncio
    async def test_create_spec(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "test create"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "test create"
        assert "id" in data
        assert "steps" in data

    @pytest.mark.asyncio
    async def test_create_spec_with_name(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "named task", "name": "My Task"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "My Task"

    @pytest.mark.asyncio
    async def test_list_specs(self, client: AsyncClient):
        await client.post("/specs", json={"intent": "list test 1"})
        await client.post("/specs", json={"intent": "list test 2"})
        resp = await client.get("/specs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 2

    @pytest.mark.asyncio
    async def test_get_spec_by_id(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "get by id"})
        spec_id = resp.json()["id"]
        resp2 = await client.get(f"/specs/{spec_id}")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == spec_id

    @pytest.mark.asyncio
    async def test_get_spec_not_found(self, client: AsyncClient):
        resp = await client.get("/specs/nonexistent-spec-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_spec(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "execute test"})
        spec_id = resp.json()["id"]
        resp2 = await client.post(f"/specs/{spec_id}/execute")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_nonexistent_spec(self, client: AsyncClient):
        resp = await client.post("/specs/fake-id/execute")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_constraint(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "constraint test"})
        spec_id = resp.json()["id"]
        resp2 = await client.post(
            f"/specs/{spec_id}/constraints",
            json={"content": "must be fast"},
        )
        assert resp2.status_code == 200
        constraints = resp2.json()["constraints"]
        assert len(constraints) >= 1
        assert any(c["content"] == "must be fast" for c in constraints)

    @pytest.mark.asyncio
    async def test_add_multiple_constraints(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "multi constraint"})
        spec_id = resp.json()["id"]
        for text in ["constraint A", "constraint B", "constraint C"]:
            await client.post(
                f"/specs/{spec_id}/constraints",
                json={"content": text},
            )
        resp2 = await client.get(f"/specs/{spec_id}")
        assert len(resp2.json()["constraints"]) >= 3

    @pytest.mark.asyncio
    async def test_redirect_spec(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "original intent"})
        spec_id = resp.json()["id"]
        resp2 = await client.post(
            f"/specs/{spec_id}/redirect",
            json={"new_intent": "new direction"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["intent"] == "new direction"

    @pytest.mark.asyncio
    async def test_redirect_nonexistent_spec(self, client: AsyncClient):
        resp = await client.post(
            "/specs/fake-id/redirect",
            json={"new_intent": "new"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_changelog(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "changelog test"})
        spec_id = resp.json()["id"]
        await client.post(
            f"/specs/{spec_id}/constraints",
            json={"content": "changelog entry"},
        )
        resp2 = await client.get(f"/specs/{spec_id}/changelog")
        assert resp2.status_code == 200
        assert isinstance(resp2.json(), list)
        assert len(resp2.json()) > 0

    @pytest.mark.asyncio
    async def test_changelog_not_found(self, client: AsyncClient):
        resp = await client.get("/specs/fake-id/changelog")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_basic(self, client: AsyncClient):
        resp = await client.post("/chat", json={"message": "review this code"})
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "agent" in data
        assert "output" in data

    @pytest.mark.asyncio
    async def test_chat_returns_agent_name(self, client: AsyncClient):
        resp = await client.post("/chat", json={"message": "review code quality"})
        data = resp.json()
        assert data["agent"] is not None
        assert len(data["agent"]) > 0


# ---------------------------------------------------------------------------
# Workflow Endpoints
# ---------------------------------------------------------------------------

class TestWorkflowEndpoints:
    @pytest.mark.asyncio
    async def test_create_workflow(self, client: AsyncClient):
        resp = await client.post(
            "/workflows",
            json={"name": "Test Workflow", "description": "A test workflow"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Workflow"
        assert data["status"] == "created"
        assert "id" in data
        assert len(data["steps"]) >= 1

    @pytest.mark.asyncio
    async def test_create_workflow_with_custom_steps(self, client: AsyncClient):
        resp = await client.post(
            "/workflows",
            json={
                "name": "Custom Steps",
                "steps": [
                    {"id": "s1", "name": "Step 1", "status": "pending", "output": None},
                    {"id": "s2", "name": "Step 2", "status": "pending", "output": None},
                ],
            },
        )
        data = resp.json()
        assert len(data["steps"]) == 2

    @pytest.mark.asyncio
    async def test_create_workflow_with_tags(self, client: AsyncClient):
        resp = await client.post(
            "/workflows",
            json={"name": "Tagged", "tags": ["ci", "deploy"]},
        )
        data = resp.json()
        assert "ci" in data["tags"]
        assert "deploy" in data["tags"]

    @pytest.mark.asyncio
    async def test_list_workflows(self, client: AsyncClient):
        await client.post("/workflows", json={"name": "WF A"})
        await client.post("/workflows", json={"name": "WF B"})
        resp = await client.get("/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "workflows" in data
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_list_workflows_filter_by_status(self, client: AsyncClient):
        resp = await client.get("/workflows", params={"status": "created"})
        assert resp.status_code == 200
        for wf in resp.json()["workflows"]:
            assert wf["status"] == "created"

    @pytest.mark.asyncio
    async def test_list_workflows_filter_by_tag(self, client: AsyncClient):
        await client.post("/workflows", json={"name": "TagWF", "tags": ["special"]})
        resp = await client.get("/workflows", params={"tag": "special"})
        assert resp.status_code == 200
        for wf in resp.json()["workflows"]:
            assert "special" in wf["tags"]

    @pytest.mark.asyncio
    async def test_get_workflow(self, client: AsyncClient):
        create_resp = await client.post("/workflows", json={"name": "Get Test"})
        wf_id = create_resp.json()["id"]
        resp = await client.get(f"/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == wf_id

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, client: AsyncClient):
        resp = await client.get("/workflows/wf-99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_workflow(self, client: AsyncClient):
        create_resp = await client.post("/workflows", json={"name": "Exec Test"})
        wf_id = create_resp.json()["id"]
        resp = await client.post(f"/workflows/{wf_id}/execute")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["execution_count"] == 1
        for step in data["steps"]:
            assert step["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found(self, client: AsyncClient):
        resp = await client.post("/workflows/wf-99999/execute")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_workflow_multiple_times(self, client: AsyncClient):
        create_resp = await client.post("/workflows", json={"name": "Multi Exec"})
        wf_id = create_resp.json()["id"]
        await client.post(f"/workflows/{wf_id}/execute")
        resp = await client.post(f"/workflows/{wf_id}/execute")
        assert resp.json()["execution_count"] == 2

    @pytest.mark.asyncio
    async def test_pause_workflow(self, client: AsyncClient):
        create_resp = await client.post("/workflows", json={"name": "Pause Test"})
        wf_id = create_resp.json()["id"]
        resp = await client.post(f"/workflows/{wf_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    @pytest.mark.asyncio
    async def test_pause_workflow_not_found(self, client: AsyncClient):
        resp = await client.post("/workflows/wf-99999/pause")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_workflow(self, client: AsyncClient):
        create_resp = await client.post("/workflows", json={"name": "Resume Test"})
        wf_id = create_resp.json()["id"]
        await client.post(f"/workflows/{wf_id}/pause")
        resp = await client.post(f"/workflows/{wf_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_resume_non_paused_workflow(self, client: AsyncClient):
        create_resp = await client.post("/workflows", json={"name": "Bad Resume"})
        wf_id = create_resp.json()["id"]
        resp = await client.post(f"/workflows/{wf_id}/resume")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_workflow_step(self, client: AsyncClient):
        create_resp = await client.post(
            "/workflows",
            json={
                "name": "Approval Test",
                "steps": [
                    {"id": "review", "name": "Review", "status": "pending", "output": None},
                ],
            },
        )
        wf_id = create_resp.json()["id"]
        resp = await client.post(
            f"/workflows/{wf_id}/approve/review",
            json={"approved": True, "comment": "LGTM"},
        )
        assert resp.status_code == 200
        step = next(s for s in resp.json()["steps"] if s["id"] == "review")
        assert step["status"] == "approved"
        assert step["approval_comment"] == "LGTM"

    @pytest.mark.asyncio
    async def test_approve_step_not_found(self, client: AsyncClient):
        create_resp = await client.post("/workflows", json={"name": "Bad Step"})
        wf_id = create_resp.json()["id"]
        resp = await client.post(
            f"/workflows/{wf_id}/approve/nonexistent",
            json={"approved": True},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_workflow_step(self, client: AsyncClient):
        create_resp = await client.post(
            "/workflows",
            json={
                "name": "Reject Test",
                "steps": [{"id": "review", "name": "Review", "status": "pending", "output": None}],
            },
        )
        wf_id = create_resp.json()["id"]
        resp = await client.post(
            f"/workflows/{wf_id}/approve/review",
            json={"approved": False, "comment": "Needs work"},
        )
        step = next(s for s in resp.json()["steps"] if s["id"] == "review")
        assert step["status"] == "rejected"


# ---------------------------------------------------------------------------
# Event Endpoints
# ---------------------------------------------------------------------------

class TestEventEndpoints:
    @pytest.mark.asyncio
    async def test_publish_event(self, client: AsyncClient):
        resp = await client.post(
            "/events/publish",
            json={"topic": "test.event", "payload": {"key": "value"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "test.event"
        assert data["delivered"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_publish_event_with_source(self, client: AsyncClient):
        resp = await client.post(
            "/events/publish",
            json={"topic": "deploy", "source": "ci-pipeline"},
        )
        assert resp.json()["source"] == "ci-pipeline"

    @pytest.mark.asyncio
    async def test_publish_event_with_priority(self, client: AsyncClient):
        resp = await client.post(
            "/events/publish",
            json={"topic": "alert", "priority": "high"},
        )
        assert resp.json()["priority"] == "high"

    @pytest.mark.asyncio
    async def test_list_events(self, client: AsyncClient):
        await client.post("/events/publish", json={"topic": "list.test"})
        resp = await client.get("/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "events" in data

    @pytest.mark.asyncio
    async def test_list_events_filter_by_topic(self, client: AsyncClient):
        await client.post("/events/publish", json={"topic": "unique.topic.abc"})
        resp = await client.get("/events", params={"topic": "unique.topic.abc"})
        for evt in resp.json()["events"]:
            assert evt["topic"] == "unique.topic.abc"

    @pytest.mark.asyncio
    async def test_list_events_filter_by_source(self, client: AsyncClient):
        await client.post(
            "/events/publish",
            json={"topic": "src.test", "source": "unit-test"},
        )
        resp = await client.get("/events", params={"source": "unit-test"})
        for evt in resp.json()["events"]:
            assert evt["source"] == "unit-test"

    @pytest.mark.asyncio
    async def test_list_events_with_limit(self, client: AsyncClient):
        for i in range(5):
            await client.post("/events/publish", json={"topic": f"limit.{i}"})
        resp = await client.get("/events", params={"limit": 2})
        assert len(resp.json()["events"]) <= 2

    @pytest.mark.asyncio
    async def test_event_has_timestamp(self, client: AsyncClient):
        resp = await client.post("/events/publish", json={"topic": "ts.test"})
        assert "timestamp" in resp.json()


# ---------------------------------------------------------------------------
# Notification Endpoints
# ---------------------------------------------------------------------------

class TestNotificationEndpoints:
    @pytest.mark.asyncio
    async def test_create_notification(self, client: AsyncClient):
        resp = await client.post(
            "/notifications",
            json={"title": "Test Alert", "body": "Something happened"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Alert"
        assert data["read"] is False
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_notification_with_level(self, client: AsyncClient):
        resp = await client.post(
            "/notifications",
            json={"title": "Warning", "level": "warning"},
        )
        assert resp.json()["level"] == "warning"

    @pytest.mark.asyncio
    async def test_create_notification_with_action_url(self, client: AsyncClient):
        resp = await client.post(
            "/notifications",
            json={"title": "Click Me", "action_url": "http://example.com"},
        )
        assert resp.json()["action_url"] == "http://example.com"

    @pytest.mark.asyncio
    async def test_list_notifications(self, client: AsyncClient):
        await client.post("/notifications", json={"title": "N1"})
        resp = await client.get("/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "notifications" in data

    @pytest.mark.asyncio
    async def test_list_notifications_filter_level(self, client: AsyncClient):
        await client.post("/notifications", json={"title": "Err", "level": "error"})
        resp = await client.get("/notifications", params={"level": "error"})
        for n in resp.json()["notifications"]:
            assert n["level"] == "error"

    @pytest.mark.asyncio
    async def test_list_notifications_filter_read(self, client: AsyncClient):
        resp = await client.get("/notifications", params={"read": False})
        assert resp.status_code == 200
        for n in resp.json()["notifications"]:
            assert n["read"] is False

    @pytest.mark.asyncio
    async def test_mark_notification_read(self, client: AsyncClient):
        create_resp = await client.post("/notifications", json={"title": "Read Me"})
        nid = create_resp.json()["id"]
        resp = await client.post(f"/notifications/{nid}/read")
        assert resp.status_code == 200
        assert resp.json()["read"] is True
        assert resp.json()["read_at"] is not None

    @pytest.mark.asyncio
    async def test_mark_notification_read_not_found(self, client: AsyncClient):
        resp = await client.post("/notifications/notif-99999/read")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_notification_default_channel(self, client: AsyncClient):
        resp = await client.post("/notifications", json={"title": "Default"})
        assert resp.json()["channel"] == "in_app"


# ---------------------------------------------------------------------------
# User Profile & Preferences
# ---------------------------------------------------------------------------

class TestUserEndpoints:
    @pytest.mark.asyncio
    async def test_get_profile(self, client: AsyncClient):
        resp = await client.get("/user/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "username" in data
        assert "email" in data
        assert "role" in data

    @pytest.mark.asyncio
    async def test_update_profile(self, client: AsyncClient):
        resp = await client.put(
            "/user/profile",
            json={"display_name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_profile_email(self, client: AsyncClient):
        resp = await client.put(
            "/user/profile",
            json={"email": "new@test.com"},
        )
        assert resp.json()["email"] == "new@test.com"

    @pytest.mark.asyncio
    async def test_get_preferences(self, client: AsyncClient):
        resp = await client.get("/user/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert "theme" in data
        assert "language" in data
        assert "timezone" in data

    @pytest.mark.asyncio
    async def test_update_preferences(self, client: AsyncClient):
        resp = await client.put(
            "/user/preferences",
            json={"theme": "light", "language": "zh"},
        )
        assert resp.status_code == 200
        assert resp.json()["theme"] == "light"
        assert resp.json()["language"] == "zh"

    @pytest.mark.asyncio
    async def test_update_preferences_page_size(self, client: AsyncClient):
        resp = await client.put(
            "/user/preferences",
            json={"page_size": 50},
        )
        assert resp.json()["page_size"] == 50


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class TestDiagnosticsEndpoints:
    @pytest.mark.asyncio
    async def test_diagnostics(self, client: AsyncClient):
        resp = await client.get("/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded")
        assert "checks" in data

    @pytest.mark.asyncio
    async def test_diagnostics_has_python_version(self, client: AsyncClient):
        resp = await client.get("/diagnostics")
        checks = resp.json()["checks"]
        assert "python_version" in checks

    @pytest.mark.asyncio
    async def test_diagnostics_has_platform(self, client: AsyncClient):
        resp = await client.get("/diagnostics")
        checks = resp.json()["checks"]
        assert "platform" in checks

    @pytest.mark.asyncio
    async def test_diagnostics_has_counts(self, client: AsyncClient):
        resp = await client.get("/diagnostics")
        checks = resp.json()["checks"]
        assert "registered_agent_count" in checks
        assert "tool_count" in checks

    @pytest.mark.asyncio
    async def test_benchmark(self, client: AsyncClient):
        resp = await client.get("/diagnostics/benchmark")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "benchmarks" in data

    @pytest.mark.asyncio
    async def test_benchmark_has_spec_creation(self, client: AsyncClient):
        resp = await client.get("/diagnostics/benchmark")
        benchmarks = resp.json()["benchmarks"]
        assert "spec_creation_10x_ms" in benchmarks

    @pytest.mark.asyncio
    async def test_benchmark_has_agent_list(self, client: AsyncClient):
        resp = await client.get("/diagnostics/benchmark")
        benchmarks = resp.json()["benchmarks"]
        assert "agent_list_100x_ms" in benchmarks


# ---------------------------------------------------------------------------
# Template Endpoints
# ---------------------------------------------------------------------------

class TestTemplateEndpoints:
    @pytest.mark.asyncio
    async def test_list_spec_templates(self, client: AsyncClient):
        resp = await client.get("/templates/specs")
        assert resp.status_code == 200
        templates = resp.json()
        assert isinstance(templates, list)
        assert len(templates) >= 1

    @pytest.mark.asyncio
    async def test_spec_template_has_fields(self, client: AsyncClient):
        resp = await client.get("/templates/specs")
        template = resp.json()[0]
        assert "name" in template
        assert "description" in template
        assert "intent_template" in template
        assert "variables" in template

    @pytest.mark.asyncio
    async def test_list_prompt_templates(self, client: AsyncClient):
        resp = await client.get("/templates/prompts")
        assert resp.status_code == 200
        templates = resp.json()
        assert isinstance(templates, list)
        assert len(templates) >= 1

    @pytest.mark.asyncio
    async def test_get_spec_template(self, client: AsyncClient):
        resp = await client.get("/templates/specs/code_review")
        assert resp.status_code == 200
        assert resp.json()["name"] == "code_review"

    @pytest.mark.asyncio
    async def test_get_spec_template_not_found(self, client: AsyncClient):
        resp = await client.get("/templates/specs/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_prompt_template(self, client: AsyncClient):
        resp = await client.get("/templates/prompts/system_prompt")
        assert resp.status_code == 200
        assert resp.json()["name"] == "system_prompt"

    @pytest.mark.asyncio
    async def test_get_prompt_template_not_found(self, client: AsyncClient):
        resp = await client.get("/templates/prompts/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_render_spec_template(self, client: AsyncClient):
        resp = await client.post(
            "/templates/specs/code_review/render",
            json={"variables": {"changes": "fix typo in README"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rendered_intent" in data
        assert "fix typo in README" in data["rendered_intent"]
        assert "constraints" in data

    @pytest.mark.asyncio
    async def test_render_spec_template_missing_variable(self, client: AsyncClient):
        resp = await client.post(
            "/templates/specs/bug_fix/render",
            json={"variables": {}},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_render_prompt_template(self, client: AsyncClient):
        resp = await client.post(
            "/templates/prompts/system_prompt/render",
            json={
                "variables": {
                    "agent_name": "TestAgent",
                    "domain": "testing",
                    "extra_instructions": "Be thorough",
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rendered" in data
        assert "TestAgent" in data["rendered"]

    @pytest.mark.asyncio
    async def test_render_prompt_template_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/templates/prompts/nonexistent/render",
            json={"variables": {}},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Agent Specs
# ---------------------------------------------------------------------------

class TestAgentSpecEndpoints:
    @pytest.mark.asyncio
    async def test_list_agent_specs(self, client: AsyncClient):
        resp = await client.get("/agent-specs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Delegations
# ---------------------------------------------------------------------------

class TestDelegationEndpoints:
    @pytest.mark.asyncio
    async def test_get_delegations(self, client: AsyncClient):
        resp = await client.get("/delegations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

class TestSkillEndpoints:
    @pytest.mark.asyncio
    async def test_list_skills(self, client: AsyncClient):
        resp = await client.get("/skills")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class TestMemoryEndpoints:
    @pytest.mark.asyncio
    async def test_list_memories(self, client: AsyncClient):
        resp = await client.get("/memory")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_add_memory(self, client: AsyncClient):
        resp = await client.post(
            "/memory",
            json={"content": "test fact", "memory_type": "fact"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_search_memory(self, client: AsyncClient):
        await client.post("/memory", json={"content": "unique search term xyz"})
        resp = await client.post(
            "/memory/search",
            json={"query": "unique search term xyz"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------

class TestKnowledgeEndpoints:
    @pytest.mark.asyncio
    async def test_knowledge_stats(self, client: AsyncClient):
        resp = await client.get("/knowledge/stats")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_knowledge_graph_viz(self, client: AsyncClient):
        resp = await client.get("/knowledge/graph")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class TestToolEndpoints:
    @pytest.mark.asyncio
    async def test_list_tools(self, client: AsyncClient):
        resp = await client.get("/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert isinstance(tools, list)
        assert len(tools) >= 10

    @pytest.mark.asyncio
    async def test_tool_has_required_fields(self, client: AsyncClient):
        resp = await client.get("/tools")
        tool = resp.json()[0]
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool


# ---------------------------------------------------------------------------
# Metrics & Traces
# ---------------------------------------------------------------------------

class TestObservabilityEndpoints:
    @pytest.mark.asyncio
    async def test_get_metrics(self, client: AsyncClient):
        resp = await client.get("/metrics")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_traces(self, client: AsyncClient):
        resp = await client.get("/traces")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_trace_not_found(self, client: AsyncClient):
        resp = await client.get("/traces/nonexistent-trace")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------

class TestMCPEndpoints:
    @pytest.mark.asyncio
    async def test_list_mcp_servers(self, client: AsyncClient):
        resp = await client.get("/mcp/servers")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Curator
# ---------------------------------------------------------------------------

class TestCuratorEndpoints:
    @pytest.mark.asyncio
    async def test_curator_stats(self, client: AsyncClient):
        resp = await client.get("/curator/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "review_count" in data

    @pytest.mark.asyncio
    async def test_curator_review(self, client: AsyncClient):
        resp = await client.post(
            "/curator/review",
            json={
                "request": "Write a greeting",
                "output": "Hello World!",
                "constraints": ["Must be polite"],
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class TestSessionEndpoints:
    @pytest.mark.asyncio
    async def test_list_sessions(self, client: AsyncClient):
        resp = await client.get("/sessions")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_session_metrics(self, client: AsyncClient):
        resp = await client.get("/sessions/metrics")
        assert resp.status_code == 200
