"""Agent: automation-audit-ops"""
from __future__ import annotations
import logging
from pathlib import Path
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

def _load_prompt():
    p = Path(__file__).parent / "automation_audit_ops_prompt.md"
    try: return p.read_text(encoding="utf-8")
    except: return "Evidence-first automation inventory and overlap audit workflow for ECC. Use when the user wants to k"

class AutomationAuditOpsAgent(BaseAgent):
    """Evidence-first automation inventory and overlap audit workflow for ECC. Use when the user wants to k"""
    def __init__(self):
        super().__init__(AgentCard(name="automation-audit-ops", description="Evidence-first automation inventory and overlap audit workflow for ECC. Use when the user wants to k", skills=["other"], domain="other", can_delegate=True))
    async def execute(self, message, context):
        if self._llm_registry:
            r = await self._llm_execute(message, context, system_prompt=_load_prompt(), max_tool_rounds=2)
            if r.success: return r
        return TaskResult(task_id=context.task_id, agent_name=self.name, success=True, output="[" + self.name + "] Done.")
    def can_handle(self, message):
        msg = message.lower()
        parts = "automation-audit-ops".lower().split("-")
        hits = sum(1 for p in parts if len(p) > 2 and p in msg)
        return min(hits * 0.15, 0.85) if parts else 0.05
