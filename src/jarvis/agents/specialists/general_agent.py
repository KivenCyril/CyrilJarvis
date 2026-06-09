from __future__ import annotations

import logging

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

GENERAL_AGENT_SYSTEM_PROMPT = """\
You are JARVIS, a personal AI assistant. You handle general conversations, \
greetings, self-introduction, and any question that doesn't require \
specialized tools or domain expertise.

Be concise, friendly, and helpful. Answer in the same language as the user. \
If a question clearly needs a specialist (code review, security audit, etc.), \
say so and suggest the user ask directly.
"""


class GeneralAgent(BaseAgent):
    """Fallback agent for general conversation and simple Q&A.

    Always returns a base score of 0.1 so the orchestrator never
    has zero candidates. Specialist agents score higher when their
    keywords match, so they still win for domain-specific queries.
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="general-agent",
            description="General conversation, greetings, and simple Q&A",
            skills=["chat", "greeting", "general"],
            domain="general",
            tool_filter=[],
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        if self._llm_registry:
            result = await self._llm_execute(
                message, context,
                system_prompt=GENERAL_AGENT_SYSTEM_PROMPT,
                max_tool_rounds=1,
            )
            if result.success:
                return result

        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output="Hello! I'm JARVIS, your AI assistant. How can I help you today?",
        )

    def can_handle(self, message: str) -> float:
        return 0.1
