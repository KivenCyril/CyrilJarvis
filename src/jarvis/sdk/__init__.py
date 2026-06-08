"""JARVIS Python SDK — programmatic interface for the JARVIS API."""

from jarvis.sdk.client import (
    AgentInfo,
    AsyncJarvisClient,
    ChatResponse,
    JarvisClient,
    MemoryInfo,
    SkillInfo,
    SpecInfo,
    ToolInfo,
)

# Public aliases matching the task spec
Spec = SpecInfo
Agent = AgentInfo
Tool = ToolInfo
Memory = MemoryInfo
Skill = SkillInfo

__all__ = [
    "JarvisClient",
    "AsyncJarvisClient",
    "Spec",
    "Agent",
    "Tool",
    "Memory",
    "Skill",
    # Full names also exported
    "AgentInfo",
    "ChatResponse",
    "MemoryInfo",
    "SkillInfo",
    "SpecInfo",
    "ToolInfo",
]
