from __future__ import annotations

import asyncio
import json
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
from jarvis.llm.provider import Message, Role

logger = logging.getLogger(__name__)


@dataclass
class SubTask:
    """子任务描述，用于任务分解。"""
    agent_name: str
    message: str
    description: str = ""

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

    # ─── Complex task handling with automatic decomposition ───

    # Keywords that suggest a task should be decomposed into sub-agents
    _COMPLEX_KEYWORDS = [
        "分析", "analyze", "深度", "详细", "全面", "架构", "architecture",
        "技术细节", "technical", "审查", "review", "评估", "evaluate",
        "比较", "compare", "调研", "research",
    ]

    def is_complex_task(self, message: str) -> bool:
        """启发式判断：消息是否复杂到需要分解为子 agent 并行执行。"""
        msg = message.lower()
        hits = sum(1 for kw in self._COMPLEX_KEYWORDS if kw.lower() in msg)
        # 长消息或包含多个关键词 → 复杂任务
        return hits >= 2 or (hits >= 1 and len(message) > 50)

    async def handle_complex(
        self,
        message: str,
        context: AgentContext | None = None,
    ) -> TaskResult:
        """处理复杂任务：自动分解 → 并行执行 → 汇总结果。"""
        from jarvis.agents.subagent_manager import SubAgentManager, SubAgentTask

        if context is None:
            context = AgentContext()

        logger.info("[Orchestrator] Handling complex task: %s", message[:80])

        # 1. 分解任务
        subtasks = await self.decompose_task(message)
        if not subtasks or len(subtasks) <= 1:
            # 无法分解或只有一个子任务 → 走普通路由
            return await self.handle(message, context)

        # 2. 并行执行
        manager = SubAgentManager(self)
        sa_tasks = [
            SubAgentTask(
                agent_name=st.agent_name,
                message=st.message,
                description=st.description,
            )
            for st in subtasks
        ]

        results = await manager.spawn_parallel(sa_tasks, context)

        # 3. 汇总结果
        summary = manager.aggregate_results(results)

        succeeded = sum(1 for r in results if r.success)
        total = len(results)

        return TaskResult(
            task_id=context.task_id,
            agent_name="orchestrator",
            success=succeeded == total,
            output=summary,
        )

    async def decompose_task(self, message: str) -> list[SubTask]:
        """将复杂任务分解为子任务列表。

        默认使用启发式规则（快速、可靠）。
        如果启用了 LLM 且启发式未匹配，尝试 LLM 分解。
        """
        # 启发式分解（优先，快速可靠）
        heuristic = self._heuristic_decompose(message)
        if heuristic and len(heuristic) > 1:
            return heuristic

        # 尝试 LLM 分解（需要配置 langchain.decompose_with_llm=true）
        config = getattr(self, '_config', {}) or {}
        if config.get('decompose_with_llm', False):
            if self.registry and hasattr(self.registry, 'list_agents'):
                llm = self._get_llm()
                if llm:
                    try:
                        result = await asyncio.wait_for(
                            self._decompose_with_llm(message, llm),
                            timeout=30.0,
                        )
                        if result:
                            return result
                    except Exception as e:
                        logger.warning("LLM decomposition failed, using heuristic: %s", e)

        # 启发式分解（可能是单任务）
        return heuristic

    def _get_llm(self):
        """安全获取 LLM 实例。"""
        try:
            from jarvis.llm.registry import llm_registry
            return llm_registry.get()
        except Exception:
            return None

    async def _decompose_with_llm(self, message: str, llm) -> list[SubTask]:
        """使用 LLM 将任务分解为子任务。"""
        # 获取可用 agent 列表
        agents = self.registry.list_agents() if self.registry else []
        agent_descriptions = "\n".join(
            f"- {a.name}: {a.card.description} (skills: {', '.join(a.card.skills[:5])})"
            for a in agents
        )

        system_prompt = f"""You are a task decomposition engine. Given a user's request, break it into 2-5 sub-tasks that can be executed in parallel by specialist agents.

Available agents:
{agent_descriptions}

Rules:
- Each sub-task should be assigned to the most appropriate agent
- Sub-tasks should be independent (no dependencies between them)
- Return ONLY a JSON array, no markdown fences
- Format: [{{"agent": "agent-name", "message": "task description", "description": "short label"}}]"""

        user_prompt = f"Decompose this request into parallel sub-tasks:\n\n{message}"

        response = await llm.chat(
            messages=[
                Message(role=Role.SYSTEM, content=system_prompt),
                Message(role=Role.USER, content=user_prompt),
            ],
            temperature=0.3,
            max_tokens=2048,
        )

        text = response.content.strip()
        # 清理可能的 markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = json.loads(text)
        return [
            SubTask(
                agent_name=item.get("agent", "general-agent"),
                message=item.get("message", ""),
                description=item.get("description", ""),
            )
            for item in data
            if isinstance(item, dict)
        ]

    def _heuristic_decompose(self, message: str) -> list[SubTask]:
        """启发式规则分解任务（LLM 不可用时的后备方案）。"""
        import re
        msg = message.lower()
        subtasks: list[SubTask] = []

        # 提取项目路径（如果有）
        path_match = re.search(r'([/\\]?[a-zA-Z0-9_.-]+(?:[/\\][a-zA-Z0-9_.-]+)+)', message)
        project_ref = path_match.group(1) if path_match else "项目"

        # 项目分析类任务
        if any(kw in msg for kw in ["分析", "analyze", "架构", "architecture", "技术"]):
            # 根据关键词选择分析维度
            if any(kw in msg for kw in ["架构", "architecture", "结构", "structure", "设计"]):
                subtasks.append(SubTask(
                    agent_name="code-agent",
                    message=f"分析 {project_ref} 的整体架构：模块划分、组件关系、目录结构。用简洁的列表输出。",
                    description="架构分析",
                ))
            if any(kw in msg for kw in ["代码", "code", "实现", "implementation", "核心"]):
                subtasks.append(SubTask(
                    agent_name="code-agent",
                    message=f"分析 {project_ref} 的核心代码：关键算法、设计模式、技术亮点。用简洁的列表输出。",
                    description="代码实现分析",
                ))
            if any(kw in msg for kw in ["流程", "pipeline", "workflow", "工作流", "业务"]):
                subtasks.append(SubTask(
                    agent_name="research-agent",
                    message=f"分析 {project_ref} 的业务流程：数据流、处理链路、关键逻辑。用简洁的列表输出。",
                    description="业务流程分析",
                ))
            if any(kw in msg for kw in ["依赖", "dependency", "技术栈", "tech stack", "deploy", "部署"]):
                subtasks.append(SubTask(
                    agent_name="devops-agent",
                    message=f"分析 {project_ref} 的技术栈：依赖管理、构建配置、部署方式。用简洁的列表输出。",
                    description="技术栈与部署",
                ))
            if any(kw in msg for kw in ["api", "接口", "endpoint"]):
                subtasks.append(SubTask(
                    agent_name="code-agent",
                    message=f"分析 {project_ref} 的 API 设计：端点列表、请求/响应格式、路由设计。用简洁的列表输出。",
                    description="API 设计分析",
                ))

        # 如果启发式没匹配到具体维度，返回通用分解
        if not subtasks:
            subtasks.append(SubTask(
                agent_name="code-agent",
                message=f"从技术实现角度分析 {project_ref}，包括架构、代码、API 设计。用简洁的列表输出。",
                description="技术分析",
            ))
            subtasks.append(SubTask(
                agent_name="research-agent",
                message=f"从研究调研角度分析 {project_ref}，包括业务流程、数据流、使用场景。用简洁的列表输出。",
                description="研究分析",
            ))

        return subtasks
