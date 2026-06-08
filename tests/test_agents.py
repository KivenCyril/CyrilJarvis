from __future__ import annotations

import pytest

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult, AgentStatus, MessageRole
from jarvis.agents.registry import AgentRegistry
from jarvis.agents.orchestrator import Orchestrator
from jarvis.agents.specialists.code_agent import CodeAgent
from jarvis.agents.specialists.calendar_agent import CalendarAgent
from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
from jarvis.agents.specialists.comms_agent import CommsAgent
from jarvis.agents.specialists.ops_agent import OpsAgent


class EchoAgent(BaseAgent):
    """Test agent that echoes back the message."""
    def __init__(self, name: str = "echo", skills: list[str] | None = None):
        super().__init__(AgentCard(
            name=name,
            description="Echo agent for testing",
            skills=skills or ["echo"],
            domain="test",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"Echo: {message}",
        )


class FailAgent(BaseAgent):
    """Test agent that always fails."""
    def __init__(self):
        super().__init__(AgentCard(name="fail", description="Fails always", skills=["fail"]))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        raise RuntimeError("Intentional failure")


class TestBaseAgent:
    @pytest.mark.asyncio
    async def test_run_success(self):
        agent = EchoAgent()
        result = await agent.run("hello")
        assert result.success
        assert "Echo: hello" in result.output
        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_run_failure(self):
        agent = FailAgent()
        result = await agent.run("trigger failure")
        assert not result.success
        assert "Intentional failure" in result.error
        assert agent.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_context_history(self):
        agent = EchoAgent()
        ctx = AgentContext()
        await agent.run("test message", ctx)
        assert len(ctx.history) == 2  # user + agent
        assert ctx.history[0].role == MessageRole.USER
        assert ctx.history[1].role == MessageRole.AGENT

    def test_can_handle(self):
        agent = EchoAgent(skills=["code", "review"])
        assert agent.can_handle("please review this code") > 0
        assert agent.can_handle("unrelated topic") == 0.0

    @pytest.mark.asyncio
    async def test_delegate_without_orchestrator(self):
        agent = EchoAgent()
        ctx = AgentContext()
        result = await agent.delegate("other-agent", "sub-task", ctx)
        assert not result.success
        assert "No orchestrator" in result.error


class TestAgentRegistry:
    @pytest.fixture
    def registry(self):
        return AgentRegistry()

    @pytest.mark.asyncio
    async def test_register_and_get(self, registry: AgentRegistry):
        agent = EchoAgent()
        await registry.register(agent)
        assert registry.get("echo") is agent
        assert len(registry) == 1

    @pytest.mark.asyncio
    async def test_deregister(self, registry: AgentRegistry):
        agent = EchoAgent()
        await registry.register(agent)
        await registry.deregister("echo")
        assert registry.get("echo") is None
        assert len(registry) == 0

    @pytest.mark.asyncio
    async def test_find_by_skill(self, registry: AgentRegistry):
        a1 = EchoAgent("a1", skills=["code", "review"])
        a2 = EchoAgent("a2", skills=["calendar", "meeting"])
        await registry.register(a1)
        await registry.register(a2)
        found = registry.find_by_skill("code")
        assert len(found) == 1
        assert found[0].name == "a1"

    @pytest.mark.asyncio
    async def test_route(self, registry: AgentRegistry):
        a1 = EchoAgent("coder", skills=["code", "review"])
        a2 = EchoAgent("scheduler", skills=["calendar", "meeting"])
        await registry.register(a1)
        await registry.register(a2)
        results = registry.route("review the code please")
        assert len(results) > 0
        assert results[0][0].name == "coder"

    @pytest.mark.asyncio
    async def test_list_cards(self, registry: AgentRegistry):
        await registry.register(EchoAgent("a1"))
        await registry.register(EchoAgent("a2"))
        cards = registry.list_cards()
        assert len(cards) == 2

    @pytest.mark.asyncio
    async def test_shutdown_all(self, registry: AgentRegistry):
        await registry.register(EchoAgent("a1"))
        await registry.register(EchoAgent("a2"))
        await registry.shutdown_all()
        assert len(registry) == 0


class TestOrchestrator:
    @pytest.fixture
    async def orchestrator(self):
        registry = AgentRegistry()
        await registry.register(CodeAgent())
        await registry.register(CalendarAgent())
        await registry.register(KnowledgeAgent())
        await registry.register(CommsAgent())
        await registry.register(OpsAgent())
        return Orchestrator(registry)

    @pytest.mark.asyncio
    async def test_route_to_code_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("请帮我 review 这段代码")
        assert result.success
        assert result.agent_name == "code-agent"

    @pytest.mark.asyncio
    async def test_route_to_calendar_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("帮我安排明天下午的会议")
        assert result.success
        assert result.agent_name == "calendar-agent"

    @pytest.mark.asyncio
    async def test_route_to_knowledge_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("搜索一下这个问题的解决方案")
        assert result.success
        assert result.agent_name == "knowledge-agent"

    @pytest.mark.asyncio
    async def test_route_to_comms_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("帮我整理收件箱里的邮件")
        assert result.success
        assert result.agent_name == "comms-agent"

    @pytest.mark.asyncio
    async def test_route_to_ops_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("集群告警了，帮我诊断一下")
        assert result.success
        assert result.agent_name == "ops-agent"

    @pytest.mark.asyncio
    async def test_no_matching_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("xyz123 random gibberish")
        assert not result.success

    @pytest.mark.asyncio
    async def test_explicit_delegation(self, orchestrator: Orchestrator):
        ctx = AgentContext(parent_agent="code-agent")
        result = await orchestrator.delegate("knowledge-agent", "查找相关文档", ctx)
        assert result.success
        assert result.agent_name == "knowledge-agent"

    @pytest.mark.asyncio
    async def test_delegation_to_nonexistent(self, orchestrator: Orchestrator):
        ctx = AgentContext()
        result = await orchestrator.delegate("nonexistent-agent", "task", ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_parallel_delegation(self, orchestrator: Orchestrator):
        ctx = AgentContext()
        tasks = [
            ("code-agent", "review code"),
            ("knowledge-agent", "search docs"),
        ]
        results = await orchestrator.parallel_delegate(tasks, ctx)
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_delegation_log(self, orchestrator: Orchestrator):
        ctx = AgentContext(parent_agent="test")
        await orchestrator.delegate("code-agent", "review", ctx)
        log = orchestrator.get_delegation_log()
        assert len(log) == 1
        assert log[0]["parent"] == "test"
        assert log[0]["child"] == "code-agent"


class TestSpecialistAgents:
    @pytest.mark.asyncio
    async def test_code_agent_classify(self):
        agent = CodeAgent()
        ctx = AgentContext()
        result = await agent.execute("review this pull request", ctx)
        assert "code-review" in result.output

    @pytest.mark.asyncio
    async def test_calendar_agent_conflict(self):
        agent = CalendarAgent()
        ctx = AgentContext()
        result = await agent.execute("check for schedule conflicts", ctx)
        assert "conflict" in result.output.lower()

    @pytest.mark.asyncio
    async def test_knowledge_agent_search(self):
        agent = KnowledgeAgent()
        ctx = AgentContext()
        result = await agent.execute("search for best practices", ctx)
        assert "search" in result.output.lower()

    @pytest.mark.asyncio
    async def test_comms_agent_triage(self):
        agent = CommsAgent()
        ctx = AgentContext()
        result = await agent.execute("triage my inbox", ctx)
        assert "triage" in result.output.lower()

    @pytest.mark.asyncio
    async def test_ops_agent_alert(self):
        agent = OpsAgent()
        ctx = AgentContext()
        result = await agent.execute("analyze this alert", ctx)
        assert "alert" in result.output.lower()
