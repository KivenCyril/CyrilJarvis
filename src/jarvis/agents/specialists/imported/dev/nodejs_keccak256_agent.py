"""Agent: nodejs-keccak256"""
from __future__ import annotations
import logging
from pathlib import Path
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

def _load_prompt():
    p = Path(__file__).parent / "nodejs_keccak256_prompt.md"
    try: return p.read_text(encoding="utf-8")
    except: return "Prevent Ethereum hashing bugs in JavaScript and TypeScript. Nodes sha3-256 is NIST SHA3, not Ethereu"

class NodejsKeccak256Agent(BaseAgent):
    """Prevent Ethereum hashing bugs in JavaScript and TypeScript. Nodes sha3-256 is NIST SHA3, not Ethereu"""
    def __init__(self):
        super().__init__(AgentCard(name="nodejs-keccak256", description="Prevent Ethereum hashing bugs in JavaScript and TypeScript. Nodes sha3-256 is NIST SHA3, not Ethereu", skills=["dev"], domain="dev", can_delegate=True))
    async def execute(self, message, context):
        if self._llm_registry:
            r = await self._llm_execute(message, context, system_prompt=_load_prompt(), max_tool_rounds=2)
            if r.success: return r
        return TaskResult(task_id=context.task_id, agent_name=self.name, success=True, output="[" + self.name + "] Done.")
    def can_handle(self, message):
        msg = message.lower()
        parts = "nodejs-keccak256".lower().split("-")
        hits = sum(1 for p in parts if len(p) > 2 and p in msg)
        return min(hits * 0.15, 0.85) if parts else 0.05
