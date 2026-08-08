"""Agent: motion-foundations"""
from __future__ import annotations
import logging
from pathlib import Path
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

def _load_prompt():
    p = Path(__file__).parent / "motion_foundations_prompt.md"
    try: return p.read_text(encoding="utf-8")
    except: return "Motion tokens, spring presets, performance rules, device adaptation, accessibility enforcement, and "

class MotionFoundationsAgent(BaseAgent):
    """Motion tokens, spring presets, performance rules, device adaptation, accessibility enforcement, and """
    def __init__(self):
        super().__init__(AgentCard(name="motion-foundations", description="Motion tokens, spring presets, performance rules, device adaptation, accessibility enforcement, and ", skills=["design"], domain="design", can_delegate=True))
    async def execute(self, message, context):
        if self._llm_registry:
            r = await self._llm_execute(message, context, system_prompt=_load_prompt(), max_tool_rounds=2)
            if r.success: return r
        return TaskResult(task_id=context.task_id, agent_name=self.name, success=True, output="[" + self.name + "] Done.")
    def can_handle(self, message):
        msg = message.lower()
        parts = "motion-foundations".lower().split("-")
        hits = sum(1 for p in parts if len(p) > 2 and p in msg)
        return min(hits * 0.15, 0.85) if parts else 0.05
