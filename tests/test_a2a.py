from __future__ import annotations

import pytest

from jarvis.agents.a2a import (
    A2AAgentCard,
    A2AArtifact,
    A2AClient,
    A2AMessage,
    A2APart,
    A2AServer,
    A2ATask,
    TaskState,
)


class TestA2AAgentCard:
    def test_create_card_minimal(self):
        card = A2AAgentCard(name="test-agent", description="A test agent")
        assert card.name == "test-agent"
        assert card.description == "A test agent"
        assert card.version == "1.0"
        assert card.capabilities["streaming"] is True
        assert card.capabilities["pushNotifications"] is False
        assert card.input_modes == ["text"]
        assert card.output_modes == ["text"]

    def test_create_card_full(self):
        card = A2AAgentCard(
            name="code-agent",
            description="Code specialist",
            url="http://localhost:8080",
            version="2.0",
            capabilities={"streaming": True, "pushNotifications": True},
            skills=[
                {"name": "code-review", "tags": ["code", "review"]},
                {"name": "refactoring", "tags": ["code", "refactor"]},
            ],
            input_modes=["text", "code-diff"],
            output_modes=["text", "code"],
            authentication={"type": "bearer"},
        )
        assert card.url == "http://localhost:8080"
        assert card.version == "2.0"
        assert len(card.skills) == 2
        assert card.skills[0]["name"] == "code-review"
        assert card.authentication == {"type": "bearer"}

    def test_card_serialization(self):
        card = A2AAgentCard(name="agent-x", description="Agent X")
        data = card.model_dump(mode="json")
        assert data["name"] == "agent-x"
        assert isinstance(data["capabilities"], dict)
        restored = A2AAgentCard.model_validate(data)
        assert restored.name == card.name


class TestA2ATask:
    def test_task_defaults(self):
        task = A2ATask()
        assert len(task.id) == 12
        assert task.state == TaskState.SUBMITTED
        assert task.messages == []
        assert task.artifacts == []

    def test_task_state_values(self):
        assert TaskState.SUBMITTED == "submitted"
        assert TaskState.WORKING == "working"
        assert TaskState.INPUT_REQUIRED == "input-required"
        assert TaskState.COMPLETED == "completed"
        assert TaskState.FAILED == "failed"
        assert TaskState.CANCELED == "canceled"

    def test_task_with_message(self):
        msg = A2AMessage(
            role="user",
            parts=[A2APart(type="text", text="Hello")],
        )
        task = A2ATask(messages=[msg])
        assert len(task.messages) == 1
        assert task.messages[0].parts[0].text == "Hello"


class TestA2AServer:
    @pytest.fixture
    def server(self):
        card = A2AAgentCard(
            name="test-server",
            description="Test A2A server",
            skills=[{"name": "testing", "tags": ["test"]}],
        )
        return A2AServer(card)

    def test_get_agent_card(self, server: A2AServer):
        card_data = server.get_agent_card()
        assert card_data["name"] == "test-server"
        assert isinstance(card_data, dict)

    @pytest.mark.asyncio
    async def test_create_task(self, server: A2AServer):
        msg = A2AMessage(
            role="user",
            parts=[A2APart(type="text", text="Do something")],
        )
        task = await server.create_task(msg)
        assert task.state == TaskState.SUBMITTED
        assert len(task.messages) == 1
        assert task.id in server._tasks

    @pytest.mark.asyncio
    async def test_get_task(self, server: A2AServer):
        msg = A2AMessage(role="user", parts=[A2APart(text="task")])
        task = await server.create_task(msg)
        retrieved = await server.get_task(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, server: A2AServer):
        result = await server.get_task("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_task_lifecycle(self, server: A2AServer):
        """Test full lifecycle: create -> working -> completed."""
        msg = A2AMessage(role="user", parts=[A2APart(text="analyze data")])
        task = await server.create_task(msg)
        assert task.state == TaskState.SUBMITTED

        # Move to working
        updated = await server.update_task(task.id, TaskState.WORKING)
        assert updated.state == TaskState.WORKING

        # Add result and complete
        result_msg = A2AMessage(
            role="agent",
            parts=[A2APart(text="Analysis complete")],
        )
        artifact = A2AArtifact(
            name="report",
            parts=[A2APart(text="Data report contents")],
            description="Analysis report",
        )
        completed = await server.update_task(
            task.id, TaskState.COMPLETED,
            message=result_msg, artifact=artifact,
        )
        assert completed.state == TaskState.COMPLETED
        assert len(completed.messages) == 2
        assert len(completed.artifacts) == 1
        assert completed.artifacts[0].name == "report"

    @pytest.mark.asyncio
    async def test_cancel_task(self, server: A2AServer):
        msg = A2AMessage(role="user", parts=[A2APart(text="cancel me")])
        task = await server.create_task(msg)
        canceled = await server.cancel_task(task.id)
        assert canceled.state == TaskState.CANCELED

    @pytest.mark.asyncio
    async def test_update_nonexistent_task(self, server: A2AServer):
        result = await server.update_task("ghost", TaskState.WORKING)
        assert result is None

    @pytest.mark.asyncio
    async def test_task_failure_state(self, server: A2AServer):
        msg = A2AMessage(role="user", parts=[A2APart(text="fail")])
        task = await server.create_task(msg)
        failed = await server.update_task(
            task.id, TaskState.FAILED,
            message=A2AMessage(role="agent", parts=[A2APart(text="Error occurred")]),
        )
        assert failed.state == TaskState.FAILED
        assert len(failed.messages) == 2


class TestA2AClient:
    @pytest.fixture
    def client(self):
        c = A2AClient()
        c.register_agent(A2AAgentCard(
            name="code-agent",
            description="Code specialist",
            skills=[
                {"name": "code-review", "tags": ["code", "review"]},
                {"name": "refactoring", "tags": ["code", "refactor"]},
            ],
        ))
        c.register_agent(A2AAgentCard(
            name="data-agent",
            description="Data specialist",
            skills=[
                {"name": "analysis", "tags": ["data", "statistics"]},
            ],
        ))
        c.register_agent(A2AAgentCard(
            name="security-agent",
            description="Security specialist",
            skills=[
                {"name": "audit", "tags": ["security", "owasp"]},
            ],
        ))
        return c

    def test_register_and_list(self, client: A2AClient):
        agents = client.list_known_agents()
        assert len(agents) == 3
        names = {a["name"] for a in agents}
        assert "code-agent" in names
        assert "data-agent" in names
        assert "security-agent" in names

    def test_discover_all(self, client: A2AClient):
        all_agents = client.discover_agents()
        assert len(all_agents) == 3

    def test_discover_by_skill_tag(self, client: A2AClient):
        code_agents = client.discover_agents("code")
        assert len(code_agents) == 1
        assert code_agents[0].name == "code-agent"

    def test_discover_by_skill_tag_security(self, client: A2AClient):
        sec_agents = client.discover_agents("security")
        assert len(sec_agents) == 1
        assert sec_agents[0].name == "security-agent"

    def test_discover_no_match(self, client: A2AClient):
        results = client.discover_agents("nonexistent-skill-xyz")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_send_task(self, client: A2AClient):
        task = await client.send_task("code-agent", "Review this PR")
        assert task is not None
        assert task.state == TaskState.SUBMITTED
        assert len(task.messages) == 1
        assert task.messages[0].parts[0].text == "Review this PR"

    @pytest.mark.asyncio
    async def test_send_task_unknown_agent(self, client: A2AClient):
        task = await client.send_task("nonexistent-agent", "Hello")
        assert task is None


class TestA2AMessageAndParts:
    def test_text_part(self):
        part = A2APart(type="text", text="Hello world")
        assert part.type == "text"
        assert part.text == "Hello world"
        assert part.mime_type == "text/plain"

    def test_file_part(self):
        part = A2APart(type="file", file_uri="file:///tmp/data.csv", mime_type="text/csv")
        assert part.type == "file"
        assert part.file_uri == "file:///tmp/data.csv"

    def test_data_part(self):
        part = A2APart(type="data", data={"key": "value"}, mime_type="application/json")
        assert part.data == {"key": "value"}

    def test_message_with_metadata(self):
        msg = A2AMessage(
            role="user",
            parts=[A2APart(text="test")],
            metadata={"priority": "high", "source": "ui"},
        )
        assert msg.metadata["priority"] == "high"

    def test_artifact_creation(self):
        artifact = A2AArtifact(
            name="output.json",
            parts=[A2APart(type="data", data={"result": 42})],
            description="Computation result",
        )
        assert artifact.name == "output.json"
        assert artifact.parts[0].data["result"] == 42
