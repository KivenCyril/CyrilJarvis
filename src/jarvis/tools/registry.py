from __future__ import annotations

import logging
from typing import Any

from jarvis.llm.provider import ToolDefinition
from jarvis.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry that maps tool names to their implementations."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool.  Raises ValueError on duplicate names."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by name, returning None if not found."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_definitions(self) -> list[ToolDefinition]:
        """Return LLM-compatible definitions for every registered tool."""
        return [t.to_llm_definition() for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Look up a tool by *name* and execute it.

        Returns a failing ``ToolResult`` when the tool is not found or when
        execution raises an unexpected exception.
        """
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, output=f"Unknown tool: {name}")

        try:
            return await tool.execute(arguments)
        except Exception as exc:
            logger.exception("Tool '%s' raised an exception", name)
            return ToolResult(success=False, output=f"Tool error: {exc}")


# Global singleton shared across the application.
tool_registry = ToolRegistry()
