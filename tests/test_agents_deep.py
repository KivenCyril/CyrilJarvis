"""Tests for the deepened specialist agents: CalendarAgent, CommsAgent,
KnowledgeAgent, OpsAgent, WritingAgent.

Covers:
- can_handle scoring for relevant and irrelevant messages
- _classify for new task types
- system prompt key sections
- helper/detection methods
"""

from __future__ import annotations

import pytest

from jarvis.agents.base import AgentContext


# ============================================================================
# CalendarAgent
# ============================================================================

class TestCalendarAgentCanHandle:
    def test_high_relevance(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent.can_handle("schedule a meeting for tomorrow") > 0
        assert agent.can_handle("check my calendar for conflicts") > 0
        assert agent.can_handle("帮我安排下午的会议日程") > 0

    def test_low_relevance(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent.can_handle("deploy the kubernetes cluster") == 0.0
        assert agent.can_handle("analyze this CSV data") == 0.0

    def test_recurring_keywords(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent.can_handle("set up a recurring weekly meeting") > 0

    def test_timezone_keywords(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent.can_handle("schedule across timezone PST") > 0


class TestCalendarAgentClassify:
    def test_conflict(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("check for scheduling conflicts") == "conflict"

    def test_reminder(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("remind me at 3pm") == "reminder"

    def test_meeting_prep(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("prepare the agenda for tomorrow's meeting") == "meeting-prep"

    def test_recurring(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("set up a recurring weekly standup") == "recurring"

    def test_analytics(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("how many meetings do I have this week") == "analytics"

    def test_cancel(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("cancel the 3pm meeting") == "cancel"

    def test_modify(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("reschedule the standup to 10am") == "modify"

    def test_default_schedule(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        assert agent._classify("some unknown request") == "schedule"


class TestCalendarAgentHelpers:
    def test_detect_time_of_day(self):
        from jarvis.agents.specialists.calendar_agent import detect_time_of_day
        assert detect_time_of_day("schedule for the morning") == "morning"
        assert detect_time_of_day("let's meet in the afternoon") == "afternoon"
        assert detect_time_of_day("dinner in the evening") == "evening"
        assert detect_time_of_day("random text") is None

    def test_resolve_timezone(self):
        from jarvis.agents.specialists.calendar_agent import resolve_timezone
        assert resolve_timezone("meeting at 3pm PST") == "America/Los_Angeles"
        assert resolve_timezone("Beijing time") == "Asia/Shanghai"
        assert resolve_timezone("no timezone here") is None

    def test_parse_duration_minutes(self):
        from jarvis.agents.specialists.calendar_agent import parse_duration_minutes
        assert parse_duration_minutes("30 minutes meeting") == 30
        assert parse_duration_minutes("1 hour sync") == 60
        assert parse_duration_minutes("1.5 hours workshop") == 90
        assert parse_duration_minutes("no duration") is None


class TestCalendarAgentExecute:
    @pytest.mark.asyncio
    async def test_execute_schedule(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        ctx = AgentContext()
        result = await agent.execute("schedule a team sync meeting", ctx)
        assert result.success
        assert "schedule" in result.output.lower() or "event" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_conflict(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        ctx = AgentContext()
        result = await agent.execute("check for conflicts in my calendar", ctx)
        assert result.success
        assert "conflict" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_analytics(self):
        from jarvis.agents.specialists.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        ctx = AgentContext()
        result = await agent.execute("analyze my meeting load this week", ctx)
        assert result.success
        assert "analytics" in result.output.lower() or "meeting" in result.output.lower()


class TestCalendarAgentSystemPrompt:
    def test_prompt_has_key_sections(self):
        from jarvis.agents.specialists.calendar_agent import CALENDAR_AGENT_SYSTEM_PROMPT
        prompt = CALENDAR_AGENT_SYSTEM_PROMPT
        assert "Conflict detection" in prompt
        assert "Recurring event" in prompt
        assert "Timezone" in prompt
        assert "Meeting preparation" in prompt
        assert "Structured event output" in prompt


# ============================================================================
# CommsAgent
# ============================================================================

class TestCommsAgentCanHandle:
    def test_high_relevance(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent.can_handle("triage my email inbox") > 0
        assert agent.can_handle("draft a reply to the client") > 0
        assert agent.can_handle("帮我整理收件箱里的邮件") > 0

    def test_low_relevance(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent.can_handle("deploy kubernetes pods") == 0.0

    def test_multi_channel(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent.can_handle("send a slack message") > 0
        assert agent.can_handle("post an announcement") > 0


class TestCommsAgentClassify:
    def test_triage(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent._classify("triage my inbox and prioritize") == "triage"

    def test_reply(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent._classify("draft a reply to the manager") == "reply"

    def test_compose(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent._classify("compose a new email to the team") == "compose"

    def test_summarize(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent._classify("summarize the conversation thread") == "summarize"

    def test_digest(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent._classify("create a daily summary digest") == "digest"

    def test_template(self):
        from jarvis.agents.specialists.comms_agent import CommsAgent
        agent = CommsAgent()
        assert agent._classify("create a message template for onboarding") == "template"


class TestCommsAgentHelpers:
    def test_detect_channel_email(self):
        from jarvis.agents.specialists.comms_agent import detect_channel
        assert detect_channel("check my gmail inbox") == "email"

    def test_detect_channel_slack(self):
        from jarvis.agents.specialists.comms_agent import detect_channel
        assert detect_channel("post to the slack channel") == "slack"

    def test_detect_channel_dingtalk(self):
        from jarvis.agents.specialists.comms_agent import detect_channel
        assert detect_channel("发钉钉消息") == "dingtalk"

    def test_detect_channel_none(self):
        from jarvis.agents.specialists.comms_agent import detect_channel
        assert detect_channel("random unrelated text") is None

    def test_detect_urgency(self):
        from jarvis.agents.specialists.comms_agent import detect_urgency
        assert detect_urgency("this is urgent ASAP") == "P1-URGENT"
        assert detect_urgency("action required by Friday") == "P2-ACTION"
        assert detect_urgency("FYI just for your info") == "P3-FYI"

    def test_estimate_reading_time(self):
        from jarvis.agents.specialists.comms_agent import estimate_reading_time
        assert estimate_reading_time("short") == 1
        assert estimate_reading_time(" ".join(["word"] * 400)) == 2


class TestCommsAgentSystemPrompt:
    def test_prompt_has_key_sections(self):
        from jarvis.agents.specialists.comms_agent import COMMS_AGENT_SYSTEM_PROMPT
        prompt = COMMS_AGENT_SYSTEM_PROMPT
        assert "urgency classification" in prompt.lower() or "Urgency" in prompt
        assert "Multi-channel" in prompt
        assert "Draft quality checklist" in prompt
        assert "Thread summarization" in prompt
        assert "Notification digest" in prompt
        assert "Response time" in prompt


# ============================================================================
# KnowledgeAgent
# ============================================================================

class TestKnowledgeAgentCanHandle:
    def test_high_relevance(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent.can_handle("search for information about Python decorators") > 0
        assert agent.can_handle("what is the difference between REST and GraphQL") > 0
        assert agent.can_handle("fact check this claim") > 0

    def test_low_relevance(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent.can_handle("schedule a meeting") == 0.0

    def test_compare_keywords(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent.can_handle("compare React vs Vue for frontend") > 0


class TestKnowledgeAgentClassify:
    def test_search(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("search for best practices") == "search"

    def test_summarize(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("summarize this document") == "summarize"

    def test_graph_query(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("query the knowledge graph for entities") == "graph-query"

    def test_deep_research(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("do a deep dive research on this topic") == "deep-research"

    def test_fact_check(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("fact check: is this claim true") == "fact-check"

    def test_compare(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("compare Python vs Go") == "compare"

    def test_explain(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("explain how async/await works") == "explain"

    def test_default_qa(self):
        from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent()
        assert agent._classify("unknown request type") == "qa"


class TestKnowledgeAgentHelpers:
    def test_detect_domain_technical(self):
        from jarvis.agents.specialists.knowledge_agent import detect_domain
        assert detect_domain("how does this API endpoint work") == "technical"

    def test_detect_domain_business(self):
        from jarvis.agents.specialists.knowledge_agent import detect_domain
        assert detect_domain("market strategy for this customer segment") == "business"

    def test_detect_domain_none(self):
        from jarvis.agents.specialists.knowledge_agent import detect_domain
        assert detect_domain("hello") is None

    def test_assess_question_complexity(self):
        from jarvis.agents.specialists.knowledge_agent import assess_question_complexity
        assert assess_question_complexity("what is Python") == "simple"
        assert assess_question_complexity("compare and analyze these options") == "complex"
        assert assess_question_complexity("tell me about it") == "moderate"

    def test_estimate_confidence(self):
        from jarvis.agents.specialists.knowledge_agent import estimate_confidence
        assert estimate_confidence(5, 1.0) == 1.0
        assert estimate_confidence(0, 0.0) == 0.0
        assert 0.0 < estimate_confidence(3, 0.7) < 1.0


class TestKnowledgeAgentSystemPrompt:
    def test_prompt_has_key_sections(self):
        from jarvis.agents.specialists.knowledge_agent import KNOWLEDGE_AGENT_SYSTEM_PROMPT
        prompt = KNOWLEDGE_AGENT_SYSTEM_PROMPT
        assert "Multi-source synthesis" in prompt
        assert "Source credibility" in prompt
        assert "confidence scoring" in prompt.lower() or "Confidence" in prompt
        assert "Knowledge gap" in prompt
        assert "Follow-up question" in prompt
        assert "citation" in prompt.lower() or "Cite" in prompt


# ============================================================================
# OpsAgent
# ============================================================================

class TestOpsAgentCanHandle:
    def test_high_relevance(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent.can_handle("there's an alert on the kubernetes cluster") > 0
        assert agent.can_handle("deploy the new release to production") > 0
        assert agent.can_handle("集群告警了，帮我诊断一下") > 0

    def test_low_relevance(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent.can_handle("write a blog post") == 0.0

    def test_new_keywords(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent.can_handle("create a runbook for the deployment") > 0
        assert agent.can_handle("check the SLO compliance") > 0
        assert agent.can_handle("optimize infrastructure cost") > 0


class TestOpsAgentClassify:
    def test_alert(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("there's an alert firing") == "alert"

    def test_deploy(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("deploy the new release") == "deploy"

    def test_incident(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("we have a production outage incident") == "incident"

    def test_runbook(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("create a runbook for database failover") == "runbook"

    def test_capacity(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("plan capacity for the growth") == "capacity"

    def test_cost(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("optimize our cloud cost and billing") == "cost"

    def test_slo(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("check our SLA compliance") == "slo"

    def test_health_check(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("run a health check on all services") == "health-check"

    def test_default_monitoring(self):
        from jarvis.agents.specialists.ops_agent import OpsAgent
        agent = OpsAgent()
        assert agent._classify("unknown ops request") == "monitoring"


class TestOpsAgentHelpers:
    def test_detect_infrastructure_k8s(self):
        from jarvis.agents.specialists.ops_agent import detect_infrastructure
        assert detect_infrastructure("check the kubernetes pod status") == "kubernetes"

    def test_detect_infrastructure_docker(self):
        from jarvis.agents.specialists.ops_agent import detect_infrastructure
        assert detect_infrastructure("restart the docker container") == "docker"

    def test_detect_infrastructure_cloud(self):
        from jarvis.agents.specialists.ops_agent import detect_infrastructure
        assert detect_infrastructure("check the AWS EC2 instance") == "cloud"

    def test_detect_infrastructure_none(self):
        from jarvis.agents.specialists.ops_agent import detect_infrastructure
        assert detect_infrastructure("hello world") is None

    def test_classify_severity(self):
        from jarvis.agents.specialists.ops_agent import classify_severity
        assert classify_severity("the system is completely down and crashed") == "P0"
        assert classify_severity("service is degraded and slow") == "P1"
        assert classify_severity("intermittent errors") == "P2"
        assert classify_severity("minor cosmetic issue") == "P3"

    def test_calculate_error_budget(self):
        from jarvis.agents.specialists.ops_agent import calculate_error_budget
        # 99.99% actual against 99.9% target -> plenty of budget left
        result = calculate_error_budget(0.999, 0.9999, 30)
        assert result["status"] == "HEALTHY"
        assert result["remaining_pct"] > 0

        # 99.0% actual against 99.9% target -> way over budget
        result_breached = calculate_error_budget(0.999, 0.990, 30)
        assert result_breached["status"] == "BREACHED"


class TestOpsAgentSystemPrompt:
    def test_prompt_has_key_sections(self):
        from jarvis.agents.specialists.ops_agent import OPS_AGENT_SYSTEM_PROMPT
        prompt = OPS_AGENT_SYSTEM_PROMPT
        assert "Runbook" in prompt
        assert "P0" in prompt and "P4" in prompt
        assert "Health check" in prompt
        assert "Capacity planning" in prompt
        assert "Cost optimization" in prompt
        assert "SLA" in prompt or "SLO" in prompt


# ============================================================================
# WritingAgent
# ============================================================================

class TestWritingAgentCanHandle:
    def test_high_relevance(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent.can_handle("write technical documentation") > 0
        assert agent.can_handle("draft a README for the project") > 0
        assert agent.can_handle("write a blog article about microservices") > 0
        assert agent.can_handle("draft an email to the team") > 0

    def test_low_relevance(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent.can_handle("deploy kubernetes pods") == 0.0

    def test_new_doc_types(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent.can_handle("write an ADR for this decision") > 0
        assert agent.can_handle("draft an RFC proposal") > 0
        assert agent.can_handle("generate a changelog") > 0


class TestWritingAgentClassify:
    def test_readme(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("create a README.md for the project") == "readme"

    def test_api_docs(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("write API documentation with swagger") == "api-docs"

    def test_adr(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("write an ADR for this architecture decision") == "adr"

    def test_rfc(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("draft an RFC for the new proposal") == "rfc"

    def test_blog(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("write a blog post about AI") == "blog"

    def test_changelog(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("generate a changelog for this release") == "changelog"

    def test_email(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("draft an email to the client") == "email"

    def test_guide(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("write a step-by-step guide for onboarding") == "guide"

    def test_edit(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("proofread and edit this document") == "edit"

    def test_default_general(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        assert agent._classify("random unknown request") == "general"


class TestWritingAgentHelpers:
    def test_detect_document_type(self):
        from jarvis.agents.specialists.writing_agent import detect_document_type
        assert detect_document_type("create a README for the project") == "readme"
        assert detect_document_type("generate API documentation") == "api-docs"
        assert detect_document_type("write a blog article") == "blog"
        assert detect_document_type("random text") is None

    def test_detect_audience(self):
        from jarvis.agents.specialists.writing_agent import detect_audience
        assert detect_audience("write for developers and engineers") == "developers"
        assert detect_audience("executive summary for manager") == "executives"
        assert detect_audience("user guide for customer") == "end-users"
        assert detect_audience("random text") == "general"

    def test_detect_output_format(self):
        from jarvis.agents.specialists.writing_agent import detect_output_format
        assert detect_output_format("generate as html web page") == "html"
        assert detect_output_format("plain text output please") == "plain-text"
        assert detect_output_format("use rst for sphinx docs") == "rst"
        assert detect_output_format("default format") == "markdown"

    def test_estimate_readability(self):
        from jarvis.agents.specialists.writing_agent import estimate_readability
        result = estimate_readability("The quick brown fox jumps over the lazy dog.")
        assert result["word_count"] == 9
        assert result["sentence_count"] >= 1
        assert result["estimated_grade"] >= 0

        empty = estimate_readability("")
        assert empty["word_count"] == 0


class TestWritingAgentSystemPrompt:
    def test_prompt_has_key_sections(self):
        from jarvis.agents.specialists.writing_agent import WRITING_AGENT_SYSTEM_PROMPT
        prompt = WRITING_AGENT_SYSTEM_PROMPT
        assert "README" in prompt
        assert "ADR" in prompt
        assert "RFC" in prompt
        assert "Blog" in prompt or "blog" in prompt
        assert "Tone and audience" in prompt
        assert "SEO" in prompt
        assert "Technical accuracy" in prompt
        assert "Readability" in prompt or "Flesch-Kincaid" in prompt
        assert "Markdown" in prompt and "HTML" in prompt


class TestWritingAgentExecute:
    @pytest.mark.asyncio
    async def test_execute_documentation(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("generate project documentation for developers", ctx)
        assert result.success
        assert "WritingAgent" in result.output

    @pytest.mark.asyncio
    async def test_execute_readme(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("create a README.md for this project", ctx)
        assert result.success
        assert "readme" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_blog(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("write a blog post about microservices", ctx)
        assert result.success
        assert "blog" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_email(self):
        from jarvis.agents.specialists.writing_agent import WritingAgent
        agent = WritingAgent()
        ctx = AgentContext()
        result = await agent.execute("draft a professional email to the client", ctx)
        assert result.success
        assert "email" in result.output.lower()
