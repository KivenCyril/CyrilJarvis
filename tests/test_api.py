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


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["agents"] >= 5


class TestAgentEndpoints:
    @pytest.mark.asyncio
    async def test_list_agents(self, client: AsyncClient):
        resp = await client.get("/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) >= 5
        names = [a["name"] for a in agents]
        assert "code-agent" in names
        assert "knowledge-agent" in names

    @pytest.mark.asyncio
    async def test_get_agent(self, client: AsyncClient):
        resp = await client.get("/agents/code-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "code-agent"
        assert "skills" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, client: AsyncClient):
        resp = await client.get("/agents/nonexistent")
        assert resp.status_code == 404


class TestSpecEndpoints:
    @pytest.mark.asyncio
    async def test_create_and_get_spec(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "test task"})
        assert resp.status_code == 200
        spec = resp.json()
        assert spec["intent"] == "test task"
        assert len(spec["steps"]) >= 1

        spec_id = spec["id"]
        resp2 = await client.get(f"/specs/{spec_id}")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == spec_id

    @pytest.mark.asyncio
    async def test_list_specs(self, client: AsyncClient):
        await client.post("/specs", json={"intent": "task A"})
        await client.post("/specs", json={"intent": "task B"})
        resp = await client.get("/specs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    @pytest.mark.asyncio
    async def test_execute_spec(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "review code"})
        spec_id = resp.json()["id"]

        resp2 = await client.post(f"/specs/{spec_id}/execute")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_add_constraint(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "test"})
        spec_id = resp.json()["id"]

        resp2 = await client.post(
            f"/specs/{spec_id}/constraints",
            json={"content": "no breaking changes"},
        )
        assert resp2.status_code == 200
        assert len(resp2.json()["constraints"]) == 1

    @pytest.mark.asyncio
    async def test_redirect_spec(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "original"})
        spec_id = resp.json()["id"]

        resp2 = await client.post(
            f"/specs/{spec_id}/redirect",
            json={"new_intent": "redirected task"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["intent"] == "redirected task"

    @pytest.mark.asyncio
    async def test_get_changelog(self, client: AsyncClient):
        resp = await client.post("/specs", json={"intent": "test"})
        spec_id = resp.json()["id"]
        await client.post(f"/specs/{spec_id}/constraints", json={"content": "rule"})

        resp2 = await client.get(f"/specs/{spec_id}/changelog")
        assert resp2.status_code == 200
        assert len(resp2.json()) > 0

    @pytest.mark.asyncio
    async def test_chat(self, client: AsyncClient):
        resp = await client.post("/chat", json={"message": "review this code"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["agent"] == "code-agent"
