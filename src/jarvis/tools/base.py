from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from jarvis.llm.provider import ToolDefinition


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    output: str
    data: dict[str, Any] | None = None


class BaseTool(ABC):
    """Abstract base class for all tools.

    Every tool must declare a name, description, and JSON Schema for its
    parameters, then implement the ``execute`` method.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Run the tool with the given arguments and return a result."""
        ...

    def to_llm_definition(self) -> ToolDefinition:
        """Convert this tool to an LLM-compatible tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )
