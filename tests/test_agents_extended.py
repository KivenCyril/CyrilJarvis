from __future__ import annotations

import pytest

from jarvis.agents.base import AgentContext
from jarvis.agents.registry import AgentRegistry
from jarvis.agents.orchestrator import Orchestrator
from jarvis.agents.specialists.calendar_agent import CalendarAgent
from jarvis.agents.specialists.code_agent import CodeAgent
from jarvis.agents.specialists.comms_agent import CommsAgent
from jarvis.agents.specialists.data_agent import DataAgent
from jarvis.agents.specialists.devops_agent import DevOpsAgent
from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
from jarvis.agents.specialists.ops_agent import OpsAgent
from jarvis.agents.specialists.research_agent import ResearchAgent
from jarvis.agents.specialists.security_agent import SecurityAgent
from jarvis.agents.specialists.writing_agent import WritingAgent


# ── DataAgent ──

class TestDataAgent:
    def test_can_handle_data_keywords(self):
        agent = DataAgent()
        assert agent.can_handle("analyze this CSV data") > 0
        assert agent.can_handle("数据分析") > 0
        assert agent.can_handle("create a pandas dataframe") > 0
        assert agent.can_handle("show me a chart of the statistics") > 0

    def test_can_handle_no_match(self):
        agent = DataAgent()
        assert agent.can_handle("schedule a meeting") == 0.0

    @pytest.mark.asyncio
    async def test_execute_profiling(self):
        agent = DataAgent()
        ctx = AgentContext()
        result = await agent.execute("explore and profile this dataset", ctx)
        assert result.success
        assert "profiling" in result.output

    @pytest.mark.asyncio
    async def test_execute_statistics(self):
        agent = DataAgent()
        ctx = AgentContext()
        result = await agent.execute("calculate mean and median statistics", ctx)
        assert result.success
        assert "statistics" in result.output

    @pytest.mark.asyncio
    async def test_execute_transform(self):
        agent = DataAgent()
        ctx = AgentContext()
        result = await agent.execute("clean and transform the data", ctx)
        assert result.success
        assert "transform" in result.output

    @pytest.mark.asyncio
    async def test_execute_visualization(self):
        agent = DataAgent()
        ctx = AgentContext()
        result = await agent.execute("create a chart visualization", ctx)
        assert result.success
        assert "visualization" in result.output

    @pytest.mark.asyncio
    async def test_execute_general(self):
        agent = DataAgent()
        ctx = AgentContext()
        result = await agent.execute("process this", ctx)
        assert result.success
        assert "analysis" in result.output


# ── SecurityAgent ──

class TestSecurityAgent:
    def test_can_handle_security_keywords(self):
        agent = SecurityAgent()
        assert agent.can_handle("run a security audit") > 0
        assert agent.can_handle("check for vulnerabilities") > 0
        assert agent.can_handle("scan for secrets and passwords") > 0
        assert agent.can_handle("安全扫描") > 0

    def test_can_handle_no_match(self):
        agent = SecurityAgent()
        assert agent.can_handle("write a blog post") == 0.0

    @pytest.mark.asyncio
    async def test_execute_audit(self):
        agent = SecurityAgent()
        ctx = AgentContext()
        result = await agent.execute("perform a security audit of the codebase", ctx)
        assert result.success
        assert "audit" in result.output

    @pytest.mark.asyncio
    async def test_execute_vulnerability(self):
        agent = SecurityAgent()
        ctx = AgentContext()
        result = await agent.execute("scan dependencies for CVE vulnerabilities", ctx)
        assert result.success
        assert "vulnerability" in result.output

    @pytest.mark.asyncio
    async def test_execute_secrets(self):
        agent = SecurityAgent()
        ctx = AgentContext()
        result = await agent.execute("detect hardcoded secrets and credentials", ctx)
        assert result.success
        assert "secrets" in result.output

    @pytest.mark.asyncio
    async def test_execute_network(self):
        agent = SecurityAgent()
        ctx = AgentContext()
        result = await agent.execute("analyze network ports and TLS config", ctx)
        assert result.success
        assert "network" in result.output


# ── DevOpsAgent ──

class TestDevOpsAgent:
    def test_can_handle_devops_keywords(self):
        agent = DevOpsAgent()
        assert agent.can_handle("build a Docker container") > 0
        assert agent.can_handle("deploy to kubernetes cluster") > 0
        assert agent.can_handle("set up CI/CD pipeline") > 0
        assert agent.can_handle("write terraform config") > 0

    def test_can_handle_no_match(self):
        agent = DevOpsAgent()
        assert agent.can_handle("what is the meaning of life") == 0.0

    @pytest.mark.asyncio
    async def test_execute_docker(self):
        agent = DevOpsAgent()
        ctx = AgentContext()
        result = await agent.execute("optimize the Dockerfile for this container", ctx)
        assert result.success
        assert "docker" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_kubernetes(self):
        agent = DevOpsAgent()
        ctx = AgentContext()
        result = await agent.execute("configure kubernetes deployment", ctx)
        assert result.success
        assert "kubernetes" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_cicd(self):
        agent = DevOpsAgent()
        ctx = AgentContext()
        result = await agent.execute("create a CI/CD pipeline with github action", ctx)
        assert result.success
        assert "ci-cd" in result.output.lower() or "ci/cd" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_terraform(self):
        agent = DevOpsAgent()
        ctx = AgentContext()
        result = await agent.execute("write terraform infrastructure code", ctx)
        assert result.success
        assert "terraform" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_monitoring(self):
        agent = DevOpsAgent()
        ctx = AgentContext()
        result = await agent.execute("set up prometheus monitoring dashboard", ctx)
        assert result.success
        assert "monitoring" in result.output.lower()


# ── WritingAgent ──

class TestWritingAgent:
    def test_can_handle_writing_keywords(self):
        agent = WritingAgent()
        assert agent.can_handle("write technical documentation") > 0
        assert agent.can_handle("draft a README for the project") > 0
        assert agent.can_handle("write a blog article") > 0
        assert agent.can_handle("draft an email") > 0

    def test_can_handle_no_match(self):
        agent = WritingAgent()
        assert agent.can_handle("deploy kubernetes pods") == 0.0

    @pytest.mark.asyncio
    async def test_execute_documentation(self):
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("generate project documentation and guide", ctx)
        assert result.success
        assert "WritingAgent" in result.output

    @pytest.mark.asyncio
    async def test_execute_readme(self):
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("create a README.md for this project", ctx)
        assert result.success
        assert "readme" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_api_docs(self):
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("write API documentation with swagger", ctx)
        assert result.success
        assert "api" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_blog(self):
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("write a blog post about microservices", ctx)
        assert result.success
        assert "blog" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_email(self):
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("draft a professional email to the client", ctx)
        assert result.success
        assert "email" in result.output.lower()


# ── ResearchAgent ──

class TestResearchAgent:
    def test_can_handle_research_keywords(self):
        agent = ResearchAgent()
        assert agent.can_handle("research this topic deeply") > 0
        assert agent.can_handle("compare React vs Vue") > 0
        assert agent.can_handle("market analysis of AI startups") > 0
        assert agent.can_handle("fact check this claim") > 0

    def test_can_handle_no_match(self):
        agent = ResearchAgent()
        assert agent.can_handle("send an email") == 0.0

    @pytest.mark.asyncio
    async def test_execute_comparison(self):
        agent = ResearchAgent()
        ctx = AgentContext()
        result = await agent.execute("compare Python vs Go for backend development", ctx)
        assert result.success
        assert "comparison" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_market(self):
        agent = ResearchAgent()
        ctx = AgentContext()
        result = await agent.execute("market analysis of the AI industry trends", ctx)
        assert result.success
        assert "market" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_literature(self):
        agent = ResearchAgent()
        ctx = AgentContext()
        result = await agent.execute("literature review of recent transformer papers", ctx)
        assert result.success
        assert "literature" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_fact_check(self):
        agent = ResearchAgent()
        ctx = AgentContext()
        result = await agent.execute("fact check: is this claim true?", ctx)
        assert result.success
        assert "fact" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_general_research(self):
        agent = ResearchAgent()
        ctx = AgentContext()
        result = await agent.execute("investigate this topic", ctx)
        assert result.success
        assert "research" in result.output.lower()


# ── Agent routing with all 10 agents ──

class TestFullAgentRouting:
    @pytest.fixture
    async def orchestrator(self):
        registry = AgentRegistry()
        agents = [
            CodeAgent(),
            CalendarAgent(),
            KnowledgeAgent(),
            CommsAgent(),
            OpsAgent(),
            DataAgent(),
            SecurityAgent(),
            DevOpsAgent(),
            WritingAgent(),
            ResearchAgent(),
        ]
        for agent in agents:
            await registry.register(agent)
        return Orchestrator(registry)

    @pytest.mark.asyncio
    async def test_route_to_data_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("analyze this CSV data and compute statistics")
        assert result.success
        assert result.agent_name == "data-agent"

    @pytest.mark.asyncio
    async def test_route_to_security_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("run a security audit and scan for vulnerabilities")
        assert result.success
        assert result.agent_name == "security-agent"

    @pytest.mark.asyncio
    async def test_route_to_devops_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("build a Docker container and deploy to kubernetes")
        assert result.success
        assert result.agent_name == "devops-agent"

    @pytest.mark.asyncio
    async def test_route_to_writing_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("write a README document for the project")
        assert result.success
        assert result.agent_name == "writing-agent"

    @pytest.mark.asyncio
    async def test_route_to_research_agent(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("deep dive research and compare market trends")
        assert result.success
        assert result.agent_name == "research-agent"

    @pytest.mark.asyncio
    async def test_original_agents_still_route(self, orchestrator: Orchestrator):
        """Verify the original 5 agents still route correctly with 10 agents."""
        result = await orchestrator.handle("请帮我 review 这段代码")
        assert result.success
        assert result.agent_name == "code-agent"

        result = await orchestrator.handle("帮我安排明天下午的会议")
        assert result.success
        assert result.agent_name == "calendar-agent"

        result = await orchestrator.handle("帮我整理收件箱里的邮件")
        assert result.success
        assert result.agent_name == "comms-agent"

        result = await orchestrator.handle("集群告警了，帮我诊断一下")
        assert result.success
        assert result.agent_name == "ops-agent"

    @pytest.mark.asyncio
    async def test_ten_agents_registered(self, orchestrator: Orchestrator):
        cards = orchestrator.registry.list_cards()
        assert len(cards) == 10

    @pytest.mark.asyncio
    async def test_no_match_still_fails(self, orchestrator: Orchestrator):
        result = await orchestrator.handle("xyz123 random gibberish nothing")
        assert not result.success
