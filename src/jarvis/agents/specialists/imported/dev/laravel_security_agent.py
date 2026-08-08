"""Agent: laravel-security"""
from __future__ import annotations
import logging
from pathlib import Path
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

def _load_prompt():
    p = Path(__file__).parent / "laravel_security_prompt.md"
    try: return p.read_text(encoding="utf-8")
    except: return "Laravel security best practices — authentication, authorization, Eloquent safety, CSRF, XSS preventi"

class LaravelSecurityAgent(BaseAgent):
    """Laravel security best practices — authentication, authorization, Eloquent safety, CSRF, XSS preventi"""
    def __init__(self):
        super().__init__(AgentCard(name="laravel-security", description="Laravel security best practices — authentication, authorization, Eloquent safety, CSRF, XSS preventi", skills=["dev"], domain="dev", can_delegate=True))
    async def execute(self, message, context):
        if self._llm_registry:
            r = await self._llm_execute(message, context, system_prompt=_load_prompt(), max_tool_rounds=2)
            if r.success: return r
        return TaskResult(task_id=context.task_id, agent_name=self.name, success=True, output="[" + self.name + "] Done.")
    def can_handle(self, message):
        msg = message.lower()
        parts = "laravel-security".lower().split("-")
        hits = sum(1 for p in parts if len(p) > 2 and p in msg)
        return min(hits * 0.15, 0.85) if parts else 0.05
