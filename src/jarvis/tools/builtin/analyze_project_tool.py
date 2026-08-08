"""AnalyzeProject Tool — 项目分析专用工具，自动并行多维度分析。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# 默认分析维度
_DEFAULT_FOCUS_AREAS = [
    "项目架构与模块划分",
    "核心代码实现与关键算法",
    "技术栈与依赖关系",
    "数据流与业务流程",
    "API 端点与接口设计",
    "部署配置与基础设施",
]


class AnalyzeProjectTool(BaseTool):
    """分析一个代码仓库的技术细节。

    自动并行使用多个 agent 分析项目的不同维度，然后汇总结果。
    """

    name = "analyze_project"
    description = (
        "分析一个代码仓库的技术细节。自动并行使用多个 agent 从不同维度分析项目，"
        "包括架构、代码实现、技术栈、数据流、API 设计等。"
        "适用于需要全面了解一个项目的场景。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目目录的绝对或相对路径",
            },
            "focus_areas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "重点分析维度列表（可选，默认分析所有维度）",
            },
        },
        "required": ["path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path_str: str = arguments["path"]
        focus_areas: list[str] | None = arguments.get("focus_areas")

        logger.info("[AnalyzeProjectTool] Analyzing project at: %s", path_str)

        project_path = Path(path_str).expanduser().resolve()
        if not project_path.exists():
            return ToolResult(success=False, output=f"路径不存在: {project_path}")
        if not project_path.is_dir():
            return ToolResult(success=False, output=f"不是目录: {project_path}")

        # 如果没有指定维度，先探测项目结构再决定
        if not focus_areas:
            focus_areas = await self._detect_focus_areas(project_path)

        try:
            from jarvis.app import jarvis
            from jarvis.agents.base import AgentContext
            from jarvis.agents.subagent_manager import SubAgentManager, SubAgentTask

            # 获取项目结构摘要
            structure_summary = await self._get_project_structure(project_path)

            # 构建子任务
            sa_tasks = []
            agent_mapping = {
                "架构": "code-agent",
                "代码": "code-agent",
                "技术栈": "devops-agent",
                "依赖": "devops-agent",
                "数据流": "data-agent",
                "业务": "research-agent",
                "API": "code-agent",
                "部署": "devops-agent",
                "测试": "code-agent",
                "安全": "code-agent",
            }

            for area in focus_areas:
                # 选择合适的 agent
                agent_name = "general-agent"
                for keyword, mapped_agent in agent_mapping.items():
                    if keyword in area:
                        agent_name = mapped_agent
                        break

                task_message = (
                    f"分析项目 {project_path.name}（路径: {project_path}）的{area}。\n\n"
                    f"## 项目结构摘要\n{structure_summary}\n\n"
                    f"请深入分析并提供详细的技术见解。"
                )
                sa_tasks.append(SubAgentTask(
                    agent_name=agent_name,
                    message=task_message,
                    description=area,
                ))

            if not sa_tasks:
                return ToolResult(success=False, output="无法确定分析维度")

            # 并行执行
            manager = SubAgentManager(jarvis.orchestrator)
            results = await manager.spawn_parallel(sa_tasks, AgentContext())

            # 汇总
            summary = manager.aggregate_results(results)

            # 添加项目基本信息头
            header = f"# 项目技术分析报告: {project_path.name}\n"
            header += f"路径: {project_path}\n"
            header += f"分析维度: {len(focus_areas)} 个\n"
            header += f"成功: {sum(1 for r in results if r.success)}/{len(results)}\n\n---\n\n"

            return ToolResult(success=True, output=header + summary)

        except Exception as exc:
            logger.exception("[AnalyzeProjectTool] Analysis failed")
            return ToolResult(success=False, output=f"项目分析失败: {exc}")

    async def _detect_focus_areas(self, project_path: Path) -> list[str]:
        """根据项目结构自动检测分析维度。"""
        areas = ["项目架构与模块划分", "核心代码实现"]

        # 检查常见文件来推断技术栈
        files = {f.name.lower() for f in project_path.rglob("*") if f.is_file()}

        if any(f.endswith((".py", ".pyw")) for f in files):
            areas.append("Python 技术栈与依赖")
        if any(f.endswith((".java", ".kt")) for f in files):
            areas.append("Java 技术栈与构建配置")
        if "docker-compose.yml" in files or "dockerfile" in files:
            areas.append("部署配置与容器化")
        if "requirements.txt" in files or "pyproject.toml" in files:
            areas.append("Python 依赖管理")
        if any("test" in f for f in files):
            areas.append("测试策略与覆盖率")
        if any(f.endswith((".yaml", ".yml", ".json")) for f in files):
            areas.append("配置文件与基础设施")

        areas.append("API 端点与接口设计")
        return areas

    async def _get_project_structure(self, project_path: Path, max_depth: int = 2) -> str:
        """获取项目目录结构的文本摘要。"""
        lines = []
        try:
            for item in sorted(project_path.iterdir()):
                if item.name.startswith('.') and item.name not in ('.env.example',):
                    continue
                if item.is_dir():
                    lines.append(f"📁 {item.name}/")
                    if max_depth > 1:
                        try:
                            sub_items = list(item.iterdir())[:20]  # 限制数量
                            for sub in sorted(sub_items):
                                if not sub.name.startswith('.'):
                                    icon = "📁" if sub.is_dir() else "📄"
                                    lines.append(f"  {icon} {sub.name}")
                        except PermissionError:
                            lines.append("  (权限不足)")
                else:
                    lines.append(f"📄 {item.name}")
        except PermissionError:
            lines.append("(无法读取目录)")

        return "\n".join(lines[:100])  # 限制行数
