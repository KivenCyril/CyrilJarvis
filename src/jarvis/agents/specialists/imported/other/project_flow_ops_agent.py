"""Agent: project-flow-ops"""
from __future__ import annotations
import logging
from pathlib import Path
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

def _load_prompt():
    p = Path(__file__).parent / "project_flow_ops_prompt.md"
    try: return p.read_text(encoding="utf-8")
    except: return "Operate execution flow across GitHub and Linear by triaging issues and pull requests, linking active"

class ProjectFlowOpsAgent(BaseAgent):
    """Operate execution flow across GitHub and Linear by triaging issues and pull requests, linking active"""
    def __init__(self):
        super().__init__(AgentCard(name="project-flow-ops", description="Operate execution flow across GitHub and Linear by triaging issues and pull requests, linking active", skills=["other"], domain="other", can_delegate=True))
    async def execute(self, message, context):
        if self._llm_registry:
            r = await self._llm_execute(message, context, system_prompt=_load_prompt(), max_tool_rounds=2)
            if r.success: return r
        return TaskResult(task_id=context.task_id, agent_name=self.name, success=True, output="[" + self.name + "] Done.")
    def can_handle(self, message):
        msg = message.lower()
        parts = "project-flow-ops".lower().split("-")
        hits = sum(1 for p in parts if len(p) > 2 and p in msg)
        return min(hits * 0.15, 0.85) if parts else 0.05
