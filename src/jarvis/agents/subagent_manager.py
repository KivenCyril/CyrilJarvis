"""SubAgent Manager — 管理子 agent 的并行/串行执行和结果汇总。"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from jarvis.agents.base import AgentContext, TaskResult

logger = logging.getLogger(__name__)


@dataclass
class SubAgentTask:
    """单个子 agent 任务的描述。"""
    agent_name: str
    message: str
    description: str = ""
    timeout: float = 60.0


@dataclass
class SubAgentResult:
    """子 agent 执行结果的封装。"""
    task: SubAgentTask
    result: TaskResult | None = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.completed_at:
            return round((self.completed_at - self.started_at) * 1000, 2)
        return 0.0

    @property
    def success(self) -> bool:
        return self.result is not None and self.result.success


class SubAgentManager:
    """管理子 agent 的生命周期、并行执行和结果汇总。

    使用方式::
    
        manager = SubAgentManager(orchestrator)
        results = await manager.spawn_parallel([
            SubAgentTask("code-agent", "分析架构"),
            SubAgentTask("research-agent", "分析算法"),
        ], context)
        summary = manager.aggregate_results(results)
    """

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    async def spawn_single(
        self,
        task: SubAgentTask,
        context: AgentContext | None = None,
    ) -> SubAgentResult:
        """生成单个子 agent 执行任务。"""
        if context is None:
            context = AgentContext()

        wrapper = SubAgentResult(task=task, started_at=time.monotonic())

        try:
            result = await asyncio.wait_for(
                self.orchestrator.delegate(task.agent_name, task.message, context),
                timeout=task.timeout,
            )
            wrapper.result = result
        except asyncio.TimeoutError:
            wrapper.error = f"Timeout after {task.task.timeout}s"
            logger.warning("[SubAgent] %s timed out: %s", task.agent_name, task.description)
        except Exception as exc:
            wrapper.error = str(exc)
            logger.exception("[SubAgent] %s failed: %s", task.agent_name, task.description)

        wrapper.completed_at = time.monotonic()
        return wrapper

    async def spawn_parallel(
        self,
        tasks: list[SubAgentTask],
        context: AgentContext | None = None,
        max_concurrency: int = 5,
    ) -> list[SubAgentResult]:
        """并行生成多个子 agent 执行各自任务。

        Args:
            tasks: 子任务列表
            context: 父上下文（子 agent 会继承约束）
            max_concurrency: 最大并发数
        """
        if not tasks:
            return []

        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_with_semaphore(task: SubAgentTask) -> SubAgentResult:
            async with semaphore:
                return await self.spawn_single(task, context)

        logger.info(
            "[SubAgent] Spawning %d sub-agents in parallel (max_concurrency=%d)",
            len(tasks), max_concurrency,
        )

        coros = [_run_with_semaphore(t) for t in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        processed: list[SubAgentResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                wrapper = SubAgentResult(
                    task=tasks[i],
                    error=str(r),
                    started_at=time.monotonic(),
                    completed_at=time.monotonic(),
                )
                processed.append(wrapper)
            else:
                processed.append(r)

        succeeded = sum(1 for r in processed if r.success)
        logger.info(
            "[SubAgent] Parallel batch complete: %d/%d succeeded",
            succeeded, len(processed),
        )
        return processed

    async def spawn_chain(
        self,
        tasks: list[SubAgentTask],
        context: AgentContext | None = None,
    ) -> list[SubAgentResult]:
        """串行生成子 agent，前一个的输出作为下一个的输入。"""
        if not tasks:
            return []

        results: list[SubAgentResult] = []
        last_output = ""

        for task in tasks:
            message = task.message
            if last_output:
                message = f"{task.message}\n\n## 前一个子任务结果\n{last_output}"

            result = await self.spawn_single(task, context)
            results.append(result)

            if result.success and result.result:
                last_output = result.result.output
            else:
                logger.warning(
                    "[SubAgent] Chain broken at '%s': %s",
                    task.agent_name, result.error or "unknown error",
                )
                break

        return results

    def aggregate_results(self, results: list[SubAgentResult]) -> str:
        """汇总多个子 agent 的结果为单个字符串。"""
        if not results:
            return "没有子任务结果。"

        parts: list[str] = []
        parts.append(f"## 子任务执行汇总 ({sum(1 for r in results if r.success)}/{len(results)} 成功)\n")

        for i, r in enumerate(results, 1):
            header = f"### {i}. [{r.task.agent_name}] {r.task.description or r.task.message[:50]}"
            parts.append(header)

            if r.success and r.result:
                parts.append(f"状态: ✅ 成功 ({r.duration_ms}ms)")
                output = (r.result.output or "").strip()
                if output:
                    parts.append(f"\n{output}\n")
            else:
                parts.append(f"状态: ❌ 失败 ({r.duration_ms}ms)")
                if r.error:
                    parts.append(f"错误: {r.error}")

            parts.append("")  # blank line between entries

        return "\n".join(parts)

    def get_progress(self, results: list[SubAgentResult]) -> dict[str, Any]:
        """获取子任务执行进度信息。"""
        total = len(results)
        completed = sum(1 for r in results if r.completed_at > 0)
        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if r.completed_at > 0 and not r.success)

        return {
            "total": total,
            "completed": completed,
            "succeeded": succeeded,
            "failed": failed,
            "in_progress": total - completed,
            "percent": int(completed / total * 100) if total else 100,
        }
