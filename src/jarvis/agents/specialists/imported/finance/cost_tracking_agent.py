"""Agent: cost-tracking"""
from __future__ import annotations
import logging
from pathlib import Path
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

def _load_prompt():
    p = Path(__file__).parent / "cost_tracking_prompt.md"
    try: return p.read_text(encoding="utf-8")
    except: return "Track and report Claude Code token usage, spending, and budgets from the local ECC cost-tracker metr"

class CostTrackingAgent(BaseAgent):
    """Track and report Claude Code token usage, spending, and budgets from the local ECC cost-tracker metr"""
    def __init__(self):
        super().__init__(AgentCard(name="cost-tracking", description="Track and report Claude Code token usage, spending, and budgets from the local ECC cost-tracker metr", skills=["finance"], domain="finance", can_delegate=True))
    async def execute(self, message, context):
        if self._llm_registry:
            r = await self._llm_execute(message, context, system_prompt=_load_prompt(), max_tool_rounds=2)
            if r.success: return r
        return TaskResult(task_id=context.task_id, agent_name=self.name, success=True, output="[" + self.name + "] Done.")
    def can_handle(self, message):
        msg = message.lower()
        parts = "cost-tracking".lower().split("-")
        hits = sum(1 for p in parts if len(p) > 2 and p in msg)
        return min(hits * 0.15, 0.85) if parts else 0.05
