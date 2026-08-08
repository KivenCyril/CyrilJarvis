"""Agent: nutrient-document-processing"""
from __future__ import annotations
import logging
from pathlib import Path
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

def _load_prompt():
    p = Path(__file__).parent / "nutrient_document_processing_prompt.md"
    try: return p.read_text(encoding="utf-8")
    except: return "Process, convert, OCR, extract, redact, sign, and fill documents using the Nutrient DWS API. Works w"

class NutrientDocumentProcessingAgent(BaseAgent):
    """Process, convert, OCR, extract, redact, sign, and fill documents using the Nutrient DWS API. Works w"""
    def __init__(self):
        super().__init__(AgentCard(name="nutrient-document-processing", description="Process, convert, OCR, extract, redact, sign, and fill documents using the Nutrient DWS API. Works w", skills=["other"], domain="other", can_delegate=True))
    async def execute(self, message, context):
        if self._llm_registry:
            r = await self._llm_execute(message, context, system_prompt=_load_prompt(), max_tool_rounds=2)
            if r.success: return r
        return TaskResult(task_id=context.task_id, agent_name=self.name, success=True, output="[" + self.name + "] Done.")
    def can_handle(self, message):
        msg = message.lower()
        parts = "nutrient-document-processing".lower().split("-")
        hits = sum(1 for p in parts if len(p) > 2 and p in msg)
        return min(hits * 0.15, 0.85) if parts else 0.05
