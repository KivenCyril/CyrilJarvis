from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.agents.subagent_manager import SubAgentResult

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass
class AgentMessage:
    """A single message in an agent conversation, following A2A Message semantics."""
    role: MessageRole
    content: str
    sender: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentCard:
    """Agent's identity and capabilities declaration, inspired by A2A Agent Card."""
    name: str
    description: str
    skills: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=lambda: ["text"])
    output_modes: list[str] = field(default_factory=lambda: ["text"])
    domain: str = ""
    version: str = "1.0"
    can_delegate: bool = False
    max_concurrent: int = 1
    tool_filter: list[str] | None = None


@dataclass
class TaskResult:
    """Result of a delegated task execution."""
    task_id: str
    agent_name: str
    success: bool
    output: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


@dataclass
class AgentContext:
    """Runtime context passed to an agent during task execution."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_agent: str | None = None
    spec_id: str | None = None
    step_id: str | None = None
    constraints: list[str] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    history: list[AgentMessage] = field(default_factory=list)

    def add_message(self, role: MessageRole, content: str, sender: str = "") -> AgentMessage:
        msg = AgentMessage(role=role, content=content, sender=sender)
        self.history.append(msg)
        return msg


class BaseAgent(ABC):
    """Abstract base class for all JARVIS agents.

    Lifecycle:
        initialize() -> execute() [repeatable] -> shutdown()

    Each agent has:
    - An AgentCard declaring its identity and capabilities
    - A status tracking its current state
    - The ability to receive tasks and return results
    - Optional delegation to sub-agents via the orchestrator
    - LLM provider for intelligent task execution
    - Tool registry for calling external tools
    """

    def __init__(self, card: AgentCard) -> None:
        self.card = card
        self.status = AgentStatus.IDLE
        self._orchestrator: Any = None
        self._llm_registry: Any = None
        self._tool_registry: Any = None

    @property
    def name(self) -> str:
        return self.card.name

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def set_llm_registry(self, registry: Any) -> None:
        self._llm_registry = registry

    def set_tool_registry(self, registry: Any) -> None:
        self._tool_registry = registry

    async def _llm_execute(
        self,
        message: str,
        context: AgentContext,
        system_prompt: str | None = None,
        max_tool_rounds: int = 5,
    ) -> TaskResult:
        """Execute a task using the conversation loop with tool calling."""
        if not self._llm_registry:
            return TaskResult(
                task_id=context.task_id,
                agent_name=self.name,
                success=False,
                error="No LLM registry configured",
            )

        from jarvis.agents.conversation import ConversationLoop
        from jarvis.agents.context import ContextBuilder

        try:
            llm = self._llm_registry.get()
        except (ImportError, Exception) as e:
            return TaskResult(
                task_id=context.task_id,
                agent_name=self.name,
                success=False,
                error=f"LLM not available: {e}",
            )

        # Build context
        builder = ContextBuilder()
        full_system_prompt = builder.build(
            system_prompt=system_prompt or f"You are {self.name}, a specialist agent.",
            constraints=context.constraints,
        )

        # Get tool definitions filtered by agent's tool_filter
        tools = None
        tool_executor = None
        if self._tool_registry and self.card.tool_filter != []:
            if self.card.tool_filter is None:
                tools = self._tool_registry.get_definitions()
            else:
                allowed = set(self.card.tool_filter)
                tools = [t for t in self._tool_registry.get_definitions() if t.name in allowed]
                if not tools:
                    tools = None
            if tools:
                tool_executor = self._tool_registry

        # Run conversation loop
        loop = ConversationLoop(
            llm=llm,
            tools=tools,
            tool_executor=tool_executor,
            max_turns=max_tool_rounds,
            system_prompt=full_system_prompt,
        )

        start = time.monotonic()
        response_text, state = await loop.run(message, constraints=context.constraints)
        duration_ms = int((time.monotonic() - start) * 1000)

        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=response_text,
            duration_ms=duration_ms,
        )

    async def initialize(self) -> None:
        """Called once when the agent is registered. Override for setup logic."""
        logger.info("Agent '%s' initialized", self.name)

    async def shutdown(self) -> None:
        """Called when the agent is being deregistered. Override for cleanup."""
        self.status = AgentStatus.SHUTDOWN
        logger.info("Agent '%s' shut down", self.name)

    async def run(self, message: str, context: AgentContext | None = None) -> TaskResult:
        """Main entry point: receive a task, execute, return result."""
        if context is None:
            context = AgentContext()

        context.add_message(MessageRole.USER, message)
        self.status = AgentStatus.BUSY

        try:
            result = await self.execute(message, context)
            context.add_message(MessageRole.AGENT, result.output, sender=self.name)
            self.status = AgentStatus.IDLE
            return result
        except Exception as e:
            self.status = AgentStatus.ERROR
            logger.exception("Agent '%s' failed on task %s", self.name, context.task_id)
            return TaskResult(
                task_id=context.task_id,
                agent_name=self.name,
                success=False,
                error=str(e),
            )

    @abstractmethod
    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        """Implement the agent's core logic. Must be overridden by subclasses."""
        ...

    async def delegate(self, agent_name: str, message: str, context: AgentContext) -> TaskResult:
        """Delegate a sub-task to another agent via the orchestrator."""
        if not self._orchestrator:
            return TaskResult(
                task_id=context.task_id,
                agent_name=self.name,
                success=False,
                error="No orchestrator available for delegation",
            )

        child_context = AgentContext(
            parent_agent=self.name,
            spec_id=context.spec_id,
            constraints=context.constraints.copy(),
        )
        return await self._orchestrator.delegate(agent_name, message, child_context)

    async def spawn_subagent(
        self,
        agent_name: str,
        message: str,
        context: AgentContext | None = None,
        description: str = "",
        timeout: float = 60.0,
    ) -> "SubAgentResult":
        """生成单个子 agent 执行子任务。

        这是 delegate() 的高级版本，返回 SubAgentResult 包含更多元数据。
        """
        from jarvis.agents.subagent_manager import SubAgentManager, SubAgentTask

        if context is None:
            context = AgentContext()

        manager = SubAgentManager(self._orchestrator)
        task = SubAgentTask(
            agent_name=agent_name,
            message=message,
            description=description,
            timeout=timeout,
        )
        return await manager.spawn_single(task, context)

    async def spawn_parallel_subagents(
        self,
        tasks: list[tuple[str, str]],
        context: AgentContext | None = None,
        descriptions: list[str] | None = None,
        max_concurrency: int = 5,
    ) -> "list[SubAgentResult]":
        """并行生成多个子 agent 执行各自任务。

        Args:
            tasks: [(agent_name, message), ...] 列表
            context: 父上下文
            descriptions: 每个任务的描述（可选）
            max_concurrency: 最大并发数
        """
        from jarvis.agents.subagent_manager import SubAgentManager, SubAgentTask

        if context is None:
            context = AgentContext()

        subtasks = []
        for i, (agent_name, message) in enumerate(tasks):
            desc = descriptions[i] if descriptions and i < len(descriptions) else ""
            subtasks.append(SubAgentTask(
                agent_name=agent_name,
                message=message,
                description=desc,
            ))

        manager = SubAgentManager(self._orchestrator)
        return await manager.spawn_parallel(subtasks, context, max_concurrency)

    def can_handle(self, message: str) -> float:
        """Return a confidence score (0.0–1.0) for whether this agent can handle the message.
        Used by the orchestrator for dynamic routing. Default: keyword match on skills.
        """
        message_lower = message.lower()
        matches = sum(1 for skill in self.card.skills if skill.lower() in message_lower)
        if not self.card.skills:
            return 0.0
        return min(matches / max(len(self.card.skills), 1), 1.0)
