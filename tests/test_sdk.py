"""Tests for the JARVIS Python SDK (jarvis.sdk)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.sdk.client import (
    AgentInfo,
    AsyncJarvisClient,
    ChatResponse,
    JarvisClient,
    MemoryInfo,
    SkillInfo,
    SpecInfo,
    ToolInfo,
)


# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------

class TestAgentInfo:
    def test_fields(self):
        a = AgentInfo(
            name="coder",
            description="Code generation agent",
            domain="engineering",
            skills=["python", "review"],
            status="active",
        )
        assert a.name == "coder"
        assert a.description == "Code generation agent"
        assert a.domain == "engineering"
        assert a.skills == ["python", "review"]
        assert a.status == "active"

    def test_equality(self):
        kwargs = dict(
            name="a", description="d", domain="dom",
            skills=["s"], status="ok",
        )
        assert AgentInfo(**kwargs) == AgentInfo(**kwargs)


class TestSpecInfo:
    def test_fields(self):
        s = SpecInfo(
            id="spec-1",
            name="Deploy",
            intent="deploy to prod",
            status="running",
            progress="50%",
            steps=[{"name": "build", "status": "done"}],
            constraints=[{"id": "c1", "content": "use docker"}],
        )
        assert s.id == "spec-1"
        assert s.name == "Deploy"
        assert s.intent == "deploy to prod"
        assert s.status == "running"
        assert s.progress == "50%"
        assert len(s.steps) == 1
        assert len(s.constraints) == 1
        assert s.changelog == []  # default

    def test_changelog_default(self):
        s = SpecInfo(
            id="x", name="n", intent="i",
            status="s", progress="p",
            steps=[], constraints=[],
        )
        assert s.changelog == []

    def test_changelog_provided(self):
        cl = [{"change": "added step"}]
        s = SpecInfo(
            id="x", name="n", intent="i",
            status="s", progress="p",
            steps=[], constraints=[], changelog=cl,
        )
        assert s.changelog == cl


class TestToolInfo:
    def test_fields(self):
        t = ToolInfo(
            name="search",
            description="Search the web",
            parameters={"query": {"type": "string"}},
        )
        assert t.name == "search"
        assert t.description == "Search the web"
        assert t.parameters == {"query": {"type": "string"}}


class TestChatResponse:
    def test_success(self):
        r = ChatResponse(success=True, agent="coder", output="done")
        assert r.success is True
        assert r.agent == "coder"
        assert r.output == "done"
        assert r.error is None

    def test_error(self):
        r = ChatResponse(
            success=False, agent="coder", output="", error="timeout",
        )
        assert r.success is False
        assert r.error == "timeout"


class TestMemoryInfo:
    def test_fields(self):
        m = MemoryInfo(
            id="mem-1",
            memory_type="fact",
            content="Python is great",
            importance=0.9,
            created_at="2024-01-01T00:00:00",
        )
        assert m.id == "mem-1"
        assert m.memory_type == "fact"
        assert m.content == "Python is great"
        assert m.importance == 0.9
        assert m.created_at == "2024-01-01T00:00:00"


class TestSkillInfo:
    def test_fields(self):
        s = SkillInfo(
            name="code-review",
            version="1.0.0",
            description="Automated code review",
            domain="engineering",
            tags=["code", "quality"],
            status="active",
            use_count=42,
            success_rate=0.95,
        )
        assert s.name == "code-review"
        assert s.version == "1.0.0"
        assert s.domain == "engineering"
        assert s.tags == ["code", "quality"]
        assert s.use_count == 42
        assert s.success_rate == 0.95


# ---------------------------------------------------------------------------
# _parse_spec helper
# ---------------------------------------------------------------------------

class TestParseSpec:
    def test_full_data(self):
        data = {
            "id": "spec-42",
            "name": "CI Setup",
            "intent": "set up CI",
            "status": "pending",
            "progress": "0%",
            "steps": [{"name": "init", "status": "pending"}],
            "constraints": [{"id": "c1", "content": "use GHA"}],
            "changelog": [{"ts": "now", "msg": "created"}],
        }
        spec = AsyncJarvisClient._parse_spec(data)
        assert isinstance(spec, SpecInfo)
        assert spec.id == "spec-42"
        assert spec.name == "CI Setup"
        assert spec.intent == "set up CI"
        assert spec.status == "pending"
        assert spec.progress == "0%"
        assert spec.steps == [{"name": "init", "status": "pending"}]
        assert spec.constraints == [{"id": "c1", "content": "use GHA"}]
        assert spec.changelog == [{"ts": "now", "msg": "created"}]

    def test_missing_optional_fields(self):
        data = {
            "id": "s1",
            "name": "n",
            "intent": "i",
            "status": "s",
        }
        spec = AsyncJarvisClient._parse_spec(data)
        assert spec.progress == ""
        assert spec.steps == []
        assert spec.constraints == []
        assert spec.changelog == []


# ---------------------------------------------------------------------------
# AsyncJarvisClient initialisation
# ---------------------------------------------------------------------------

class TestAsyncClientInit:
    def test_defaults(self):
        c = AsyncJarvisClient()
        assert c._base_url == "http://localhost:8000"
        assert c._timeout == 30.0
        assert c._client is None

    def test_custom_url(self):
        c = AsyncJarvisClient("http://myhost:9000/", timeout=60.0)
        assert c._base_url == "http://myhost:9000"  # trailing slash stripped
        assert c._timeout == 60.0

    def test_trailing_slash_stripped(self):
        c = AsyncJarvisClient("http://host:1234///")
        assert c._base_url == "http://host:1234"


# ---------------------------------------------------------------------------
# AsyncJarvisClient context manager
# ---------------------------------------------------------------------------

class TestAsyncClientContextManager:
    @pytest.mark.asyncio
    async def test_aenter_aexit(self):
        client = AsyncJarvisClient()
        result = await client.__aenter__()
        assert result is client
        assert client._client is not None
        await client.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# AsyncJarvisClient HTTP helpers (mocked)
# ---------------------------------------------------------------------------

def _make_mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestAsyncClientChat:
    @pytest.mark.asyncio
    async def test_chat(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response({
            "success": True,
            "agent": "coder",
            "output": "Hello!",
            "error": None,
        })

        resp = await client.chat("hi")
        assert isinstance(resp, ChatResponse)
        assert resp.success is True
        assert resp.agent == "coder"
        assert resp.output == "Hello!"
        assert resp.error is None


class TestAsyncClientAgents:
    @pytest.mark.asyncio
    async def test_list_agents(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([
            {
                "name": "coder",
                "description": "Codes",
                "domain": "eng",
                "skills": ["py"],
                "status": "active",
            },
        ])

        agents = await client.list_agents()
        assert len(agents) == 1
        assert agents[0].name == "coder"

    @pytest.mark.asyncio
    async def test_get_agent(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response({
            "name": "reviewer",
            "description": "Reviews code",
            "domain": "quality",
            "skills": ["review"],
            "status": "active",
        })

        agent = await client.get_agent("reviewer")
        assert isinstance(agent, AgentInfo)
        assert agent.name == "reviewer"


class TestAsyncClientSpecs:
    @pytest.mark.asyncio
    async def test_create_spec(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response({
            "id": "spec-new",
            "name": "New Spec",
            "intent": "do something",
            "status": "created",
            "progress": "0%",
            "steps": [],
            "constraints": [],
        })

        spec = await client.create_spec("do something")
        assert isinstance(spec, SpecInfo)
        assert spec.id == "spec-new"
        assert spec.status == "created"

    @pytest.mark.asyncio
    async def test_get_spec(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response({
            "id": "spec-1",
            "name": "S",
            "intent": "i",
            "status": "running",
            "progress": "50%",
            "steps": [{"name": "a", "status": "done"}],
            "constraints": [],
        })

        spec = await client.get_spec("spec-1")
        assert spec.progress == "50%"
        assert len(spec.steps) == 1

    @pytest.mark.asyncio
    async def test_list_specs(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([
            {
                "id": "s1", "name": "A", "intent": "i",
                "status": "done", "progress": "100%",
                "steps": [], "constraints": [],
            },
            {
                "id": "s2", "name": "B", "intent": "j",
                "status": "pending", "progress": "0%",
                "steps": [], "constraints": [],
            },
        ])

        specs = await client.list_specs()
        assert len(specs) == 2

    @pytest.mark.asyncio
    async def test_execute_spec(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response({
            "id": "s1", "name": "A", "intent": "i",
            "status": "running", "progress": "10%",
            "steps": [], "constraints": [],
        })

        spec = await client.execute_spec("s1")
        assert spec.status == "running"

    @pytest.mark.asyncio
    async def test_add_constraint(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response({
            "id": "s1", "name": "A", "intent": "i",
            "status": "pending", "progress": "0%",
            "steps": [],
            "constraints": [{"id": "c1", "content": "use docker"}],
        })

        spec = await client.add_constraint("s1", "use docker")
        assert len(spec.constraints) == 1

    @pytest.mark.asyncio
    async def test_remove_constraint(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.delete.return_value = _make_mock_response({
            "id": "s1", "name": "A", "intent": "i",
            "status": "pending", "progress": "0%",
            "steps": [], "constraints": [],
        })

        spec = await client.remove_constraint("s1", "c1")
        assert len(spec.constraints) == 0

    @pytest.mark.asyncio
    async def test_edit_step(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.patch.return_value = _make_mock_response({
            "id": "s1", "name": "A", "intent": "i",
            "status": "pending", "progress": "0%",
            "steps": [{"id": "st1", "name": "renamed"}],
            "constraints": [],
        })

        spec = await client.edit_step("s1", "st1", name="renamed")
        assert spec.steps[0]["name"] == "renamed"

    @pytest.mark.asyncio
    async def test_redirect_spec(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response({
            "id": "s1", "name": "A", "intent": "new intent",
            "status": "pending", "progress": "0%",
            "steps": [], "constraints": [],
        })

        spec = await client.redirect_spec("s1", "new intent")
        assert spec.intent == "new intent"

    @pytest.mark.asyncio
    async def test_get_changelog(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([
            {"ts": "2024-01-01", "msg": "created"},
        ])

        changelog = await client.get_changelog("s1")
        assert len(changelog) == 1


class TestAsyncClientTools:
    @pytest.mark.asyncio
    async def test_list_tools(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([
            {
                "name": "search",
                "description": "Search",
                "parameters": {"q": {"type": "str"}},
            },
        ])

        tools = await client.list_tools()
        assert len(tools) == 1
        assert isinstance(tools[0], ToolInfo)
        assert tools[0].name == "search"


class TestAsyncClientMemory:
    @pytest.mark.asyncio
    async def test_add_memory(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response(
            {"id": "mem-1", "status": "stored"},
        )

        result = await client.add_memory("test content", "fact")
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_search_memory(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response([
            {"content": "Python is great", "memory_type": "fact"},
        ])

        results = await client.search_memory("Python")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_memories(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([])

        memories = await client.list_memories()
        assert memories == []


class TestAsyncClientKnowledge:
    @pytest.mark.asyncio
    async def test_knowledge_stats(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response(
            {"nodes": 10, "edges": 15},
        )

        stats = await client.knowledge_stats()
        assert stats["nodes"] == 10

    @pytest.mark.asyncio
    async def test_knowledge_graph(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response(
            {"nodes": [], "edges": []},
        )

        graph = await client.knowledge_graph()
        assert "nodes" in graph

    @pytest.mark.asyncio
    async def test_extract_knowledge(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response(
            {"extracted_nodes": 3},
        )

        result = await client.extract_knowledge("some text")
        assert result["extracted_nodes"] == 3


class TestAsyncClientSkills:
    @pytest.mark.asyncio
    async def test_list_skills(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([
            {
                "name": "review",
                "version": "1.0",
                "description": "Review code",
                "domain": "eng",
                "tags": ["code"],
                "status": "active",
                "use_count": 10,
                "success_rate": 0.9,
            },
        ])

        skills = await client.list_skills()
        assert len(skills) == 1
        assert isinstance(skills[0], SkillInfo)
        assert skills[0].name == "review"


class TestAsyncClientCurator:
    @pytest.mark.asyncio
    async def test_review(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.post.return_value = _make_mock_response(
            {"verdict": "fail", "score": 20},
        )

        result = await client.review(
            request="write secure code",
            output="password = '123'",
            constraints=["OWASP"],
        )
        assert result["verdict"] == "fail"
        assert result["score"] == 20


class TestAsyncClientObservability:
    @pytest.mark.asyncio
    async def test_get_metrics(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response(
            {"requests": 100},
        )

        metrics = await client.get_metrics()
        assert metrics["requests"] == 100

    @pytest.mark.asyncio
    async def test_list_traces(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([])

        traces = await client.list_traces()
        assert traces == []


class TestAsyncClientSessions:
    @pytest.mark.asyncio
    async def test_list_sessions(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([])

        sessions = await client.list_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_session_metrics(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response(
            {"active": 5},
        )

        metrics = await client.session_metrics()
        assert metrics["active"] == 5


class TestAsyncClientDelegations:
    @pytest.mark.asyncio
    async def test_get_delegations(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([])

        delegations = await client.get_delegations()
        assert delegations == []


class TestAsyncClientMCP:
    @pytest.mark.asyncio
    async def test_list_mcp_servers(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response([])

        servers = await client.list_mcp_servers()
        assert servers == []


class TestAsyncClientHealth:
    @pytest.mark.asyncio
    async def test_health(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response(
            {"status": "healthy", "agents": 3},
        )

        health = await client.health()
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_system_info(self):
        client = AsyncJarvisClient()
        client._client = AsyncMock()
        client._client.get.return_value = _make_mock_response(
            {"version": "0.1.0"},
        )

        info = await client.system_info()
        assert info["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# JarvisClient (sync wrapper)
# ---------------------------------------------------------------------------

class TestJarvisClientInit:
    def test_defaults(self):
        c = JarvisClient()
        assert c._base_url == "http://localhost:8000"

    def test_custom_url(self):
        c = JarvisClient("http://other:9999")
        assert c._base_url == "http://other:9999"


class TestJarvisClientRun:
    def test_run_raises_in_running_loop(self):
        """_run should raise when there's already a running event loop."""
        client = JarvisClient()

        async def _inner():
            async def dummy():
                return 42
            client._run(dummy())

        with pytest.raises(RuntimeError, match="running"):
            asyncio.run(_inner())


# ---------------------------------------------------------------------------
# Module-level imports via __init__
# ---------------------------------------------------------------------------

class TestSDKExports:
    def test_top_level_imports(self):
        from jarvis.sdk import (
            Agent,
            AsyncJarvisClient,
            JarvisClient,
            Memory,
            Skill,
            Spec,
            Tool,
        )
        assert Spec is SpecInfo
        assert Agent is AgentInfo
        assert Tool is ToolInfo
        assert Memory is MemoryInfo
        assert Skill is SkillInfo
