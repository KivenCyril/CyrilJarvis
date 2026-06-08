from __future__ import annotations

import logging
from typing import Any

from jarvis.agents.base import AgentCard, BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent discovery and lifecycle management.

    Responsibilities:
    - Register/deregister agents
    - Agent lookup by name or capability
    - Agent lifecycle management (init/shutdown)
    - Provide agent cards for discovery (A2A Agent Card pattern)
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    async def register(self, agent: BaseAgent) -> None:
        if agent.name in self._agents:
            logger.warning("Agent '%s' already registered, replacing", agent.name)
            await self._agents[agent.name].shutdown()

        self._agents[agent.name] = agent
        await agent.initialize()
        logger.info(
            "Registered agent '%s' (skills: %s)",
            agent.name,
            ", ".join(agent.card.skills),
        )

    async def deregister(self, name: str) -> None:
        agent = self._agents.pop(name, None)
        if agent:
            await agent.shutdown()
            logger.info("Deregistered agent '%s'", name)

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def list_cards(self) -> list[AgentCard]:
        return [a.card for a in self._agents.values()]

    def find_by_skill(self, skill: str) -> list[BaseAgent]:
        return [a for a in self._agents.values() if skill in a.card.skills]

    def find_by_domain(self, domain: str) -> list[BaseAgent]:
        return [a for a in self._agents.values() if a.card.domain == domain]

    def route(self, message: str) -> list[tuple[BaseAgent, float]]:
        """Score all agents against a message and return sorted by confidence."""
        scored = []
        for agent in self._agents.values():
            score = agent.can_handle(message)
            if score > 0:
                scored.append((agent, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    async def shutdown_all(self) -> None:
        for agent in list(self._agents.values()):
            await agent.shutdown()
        self._agents.clear()

    def set_orchestrator_for_all(self, orchestrator: Any) -> None:
        for agent in self._agents.values():
            agent.set_orchestrator(orchestrator)

    def set_llm_registry_for_all(self, llm_registry: Any) -> None:
        for agent in self._agents.values():
            agent.set_llm_registry(llm_registry)

    def set_tool_registry_for_all(self, tool_registry: Any) -> None:
        for agent in self._agents.values():
            agent.set_tool_registry(tool_registry)

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents
