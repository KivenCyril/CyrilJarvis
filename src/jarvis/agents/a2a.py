from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class A2APart(BaseModel):
    """Content part in an A2A message."""
    type: str = "text"  # text, file, data
    text: str = ""
    file_uri: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    mime_type: str = "text/plain"


class A2AMessage(BaseModel):
    """Message in A2A protocol."""
    role: str  # "user" or "agent"
    parts: list[A2APart] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2AArtifact(BaseModel):
    """Agent output artifact."""
    name: str
    parts: list[A2APart] = Field(default_factory=list)
    description: str = ""


class A2ATask(BaseModel):
    """A2A Task: the unit of work between agents."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: TaskState = TaskState.SUBMITTED
    messages: list[A2AMessage] = Field(default_factory=list)
    artifacts: list[A2AArtifact] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2AAgentCard(BaseModel):
    """Agent Card: an agent's identity and capabilities advertisement.

    Following the A2A spec (Linux Foundation v1.0):
    - name, description, url
    - capabilities (streaming, push notifications)
    - skills with tags
    - supported input/output modes
    """
    name: str
    description: str
    url: str = ""
    version: str = "1.0"
    capabilities: dict[str, bool] = Field(default_factory=lambda: {
        "streaming": True,
        "pushNotifications": False,
    })
    skills: list[dict[str, Any]] = Field(default_factory=list)
    input_modes: list[str] = Field(default_factory=lambda: ["text"])
    output_modes: list[str] = Field(default_factory=lambda: ["text"])
    authentication: dict[str, Any] = Field(default_factory=dict)


class A2AServer:
    """A2A Server endpoint for receiving tasks from other agents.

    Each JARVIS agent can be exposed as an A2A-compatible server.
    """

    def __init__(self, agent_card: A2AAgentCard):
        self.agent_card = agent_card
        self._tasks: dict[str, A2ATask] = {}

    def get_agent_card(self) -> dict:
        """Returns the agent card (GET /.well-known/agent.json)."""
        return self.agent_card.model_dump(mode="json")

    async def create_task(self, message: A2AMessage) -> A2ATask:
        """Create a new task (POST /tasks/send)."""
        task = A2ATask(
            messages=[message],
            state=TaskState.SUBMITTED,
        )
        self._tasks[task.id] = task
        return task

    async def get_task(self, task_id: str) -> A2ATask | None:
        """Get task status (GET /tasks/{id})."""
        return self._tasks.get(task_id)

    async def update_task(
        self,
        task_id: str,
        state: TaskState,
        message: A2AMessage | None = None,
        artifact: A2AArtifact | None = None,
    ) -> A2ATask | None:
        """Update a task's state, optionally adding a message or artifact."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.state = state
        task.updated_at = datetime.now(timezone.utc)
        if message:
            task.messages.append(message)
        if artifact:
            task.artifacts.append(artifact)
        return task

    async def cancel_task(self, task_id: str) -> A2ATask | None:
        """Cancel a task."""
        return await self.update_task(task_id, TaskState.CANCELED)


class A2AClient:
    """A2A Client for sending tasks to other agents."""

    def __init__(self):
        self._known_agents: dict[str, A2AAgentCard] = {}

    def register_agent(self, card: A2AAgentCard) -> None:
        """Register an agent card for discovery."""
        self._known_agents[card.name] = card

    def discover_agents(self, skill_tag: str = "") -> list[A2AAgentCard]:
        """Find agents that can handle a given skill."""
        if not skill_tag:
            return list(self._known_agents.values())
        results = []
        for card in self._known_agents.values():
            for skill in card.skills:
                tags = skill.get("tags", [])
                if skill_tag in tags or skill_tag.lower() in str(skill).lower():
                    results.append(card)
                    break
        return results

    async def send_task(self, agent_name: str, message: str) -> A2ATask | None:
        """Send a task to another agent."""
        card = self._known_agents.get(agent_name)
        if not card:
            logger.warning("Agent '%s' not found in A2A registry", agent_name)
            return None

        # For local agents, create task directly
        # For remote agents, would use HTTP POST to card.url
        task = A2ATask(
            messages=[A2AMessage(
                role="user",
                parts=[A2APart(type="text", text=message)],
            )],
        )
        logger.info("A2A task %s sent to '%s'", task.id, agent_name)
        return task

    def list_known_agents(self) -> list[dict]:
        """List all registered agent cards."""
        return [card.model_dump(mode="json") for card in self._known_agents.values()]
