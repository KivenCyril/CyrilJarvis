"""SubAgent Tool — 让 agent 通过 LLM tool-calling 生成子 agent。"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SpawnSubAgentTool(BaseTool):
    """生成一个子 agent 来执行子任务。

    工具 agent 可以在对话中调用此工具来并行处理复杂任务。
    """

    name = "spawn_subagent"
    description = (
        "生成一个子 agent 来执行子任务。适用于需要并行处理多个独立子任务的场景。"
        "可用的 agent: code-agent, research-agent, data-agent, general-agent, "
        "writing-agent, knowledge-agent, ops-agent, devops-agent, comms-agent, calendar-agent。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "子 agent 名称（如 code-agent, research-agent）",
            },
            "task": {
                "type": "string",
                "description": "子任务的详细描述",
            },
            "description": {
                "type": "string",
                "description": "子任务的简短标签（可选）",
            },
        },
        "required": ["agent", "task"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        agent_name: str = arguments["agent"]
        task: str = arguments["task"]
        description: str = arguments.get("description", "")

        logger.info("[SpawnSubAgentTool] Request to spawn '%s' for: %s", agent_name, task[:50])

        try:
            from jarvis.agents.registry import AgentRegistry
            from jarvis.agents.base import AgentContext
            from jarvis.agents.subagent_manager import SubAgentManager, SubAgentTask

            # 获取全局 orchestrator — 通过 registry 间接访问
            # 注意：这里需要 orchestrator 实例，通过全局变量或依赖注入获取
            from jarvis.app import jarvis

            manager = SubAgentManager(jarvis.orchestrator)
            sa_task = SubAgentTask(
                agent_name=agent_name,
                message=task,
                description=description,
            )
            result = await manager.spawn_single(sa_task, AgentContext())

            if result.success:
                return ToolResult(
                    success=True,
                    output=result.result.output if result.result else "子任务完成（无输出）",
                )
            else:
                return ToolResult(
                    success=False,
                    output=f"子任务失败: {result.error or '未知错误'}",
                )
        except Exception as exc:
            logger.exception("[SpawnSubAgentTool] Failed to spawn '%s'", agent_name)
            return ToolResult(
                success=False,
                output=f"生成子 agent 失败: {exc}",
            )


class SpawnParallelSubAgentsTool(BaseTool):
    """并行生成多个子 agent 执行各自任务。"""

    name = "spawn_parallel_subagents"
    description = (
        "并行生成多个子 agent 来同时执行多个独立子任务。"
        "每个子任务会被分配给最合适的 agent。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "子任务列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "description": "agent 名称"},
                        "task": {"type": "string", "description": "任务描述"},
                        "description": {"type": "string", "description": "简短标签"},
                    },
                    "required": ["agent", "task"],
                },
            },
        },
        "required": ["tasks"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        tasks_raw: list[dict] = arguments["tasks"]

        logger.info("[SpawnParallelSubAgentsTool] Spawning %d sub-agents", len(tasks_raw))

        try:
            from jarvis.app import jarvis
            from jarvis.agents.base import AgentContext
            from jarvis.agents.subagent_manager import SubAgentManager, SubAgentTask

            manager = SubAgentManager(jarvis.orchestrator)
            sa_tasks = [
                SubAgentTask(
                    agent_name=t["agent"],
                    message=t["task"],
                    description=t.get("description", ""),
                )
                for t in tasks_raw
            ]

            results = await manager.spawn_parallel(sa_tasks, AgentContext())
            summary = manager.aggregate_results(results)

            return ToolResult(success=True, output=summary)
        except Exception as exc:
            logger.exception("[SpawnParallelSubAgentsTool] Failed")
            return ToolResult(success=False, output=f"并行子任务失败: {exc}")
