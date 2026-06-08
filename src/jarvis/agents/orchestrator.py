from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from jarvis.agents.base import (
    AgentContext,
    AgentMessage,
    BaseAgent,
    MessageRole,
    TaskResult,
)
from jarvis.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class DelegationRecord:
    """Tracks a delegation from parent to child agent."""
    parent: str
    child: str
    task_id: str
    message: str
    result: TaskResult | None = None


class Orchestrator:
    """Central orchestrator that routes tasks to specialist agents.

    Responsibilities:
    - Understand user intent and route to the best agent
    - Support explicit delegation (agent A asks agent B)
    - Support parallel execution of independent sub-tasks
    - Track delegation history for observability
    - Enforce constraints from Streaming Spec
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self.delegation_log: list[DelegationRecord] = []
        registry.set_orchestrator_for_all(self)

    async def handle(self, message: str, context: AgentContext | None = None) -> TaskResult:
        """Main entry: route a user message to the best agent."""
        if context is None:
            context = AgentContext()

        candidates = self.registry.route(message)

        if not candidates:
            logger.warning("No agent can handle: %s", message[:80])
            return TaskResult(
                task_id=context.task_id,
                agent_name="orchestrator",
                success=False,
                error=f"No agent found for: {message[:100]}",
            )

        best_agent, score = candidates[0]
        logger.info(
            "Routing to '%s' (score=%.2f, %d candidates)",
            best_agent.name, score, len(candidates),
        )

        context.add_message(MessageRole.SYSTEM, f"Routed to {best_agent.name} (score={score:.2f})")
        return await best_agent.run(message, context)

    async def delegate(self, agent_name: str, message: str, context: AgentContext) -> TaskResult:
        """Explicit delegation: one agent asks another to do a sub-task."""
        agent = self.registry.get(agent_name)
        if not agent:
            return TaskResult(
                task_id=context.task_id,
                agent_name=agent_name,
                success=False,
                error=f"Agent '{agent_name}' not found",
            )

        record = DelegationRecord(
            parent=context.parent_agent or "orchestrator",
            child=agent_name,
            task_id=context.task_id,
            message=message,
        )

        start = time.monotonic()
        result = await agent.run(message, context)
        result.duration_ms = int((time.monotonic() - start) * 1000)

        record.result = result
        self.delegation_log.append(record)

        logger.info(
            "Delegation %s → %s: %s (%dms)",
            record.parent, agent_name,
            "success" if result.success else "failed",
            result.duration_ms,
        )
        return result

    async def parallel_delegate(
        self,
        tasks: list[tuple[str, str]],
        context: AgentContext,
    ) -> list[TaskResult]:
        """Execute multiple delegations in parallel.

        Args:
            tasks: list of (agent_name, message) tuples
            context: shared parent context
        """
        async def _run_one(agent_name: str, message: str) -> TaskResult:
            child_ctx = AgentContext(
                parent_agent=context.parent_agent or "orchestrator",
                spec_id=context.spec_id,
                constraints=context.constraints.copy(),
            )
            return await self.delegate(agent_name, message, child_ctx)

        results = await asyncio.gather(
            *[_run_one(name, msg) for name, msg in tasks],
            return_exceptions=True,
        )

        processed: list[TaskResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                agent_name = tasks[i][0]
                processed.append(TaskResult(
                    task_id=context.task_id,
                    agent_name=agent_name,
                    success=False,
                    error=str(r),
                ))
            else:
                processed.append(r)
        return processed

    def get_delegation_log(self) -> list[dict]:
        return [
            {
                "parent": r.parent,
                "child": r.child,
                "task_id": r.task_id,
                "message": r.message[:100],
                "success": r.result.success if r.result else None,
                "duration_ms": r.result.duration_ms if r.result else None,
            }
            for r in self.delegation_log
        ]
