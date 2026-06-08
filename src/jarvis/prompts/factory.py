"""System prompt factory for different agent types."""

from __future__ import annotations

from typing import Any

from jarvis.prompts.builder import PromptBuilder

# Agent configuration presets keyed by canonical agent name.
_AGENT_CONFIGS: dict[str, dict[str, Any]] = {
    "code-agent": {
        "description": "a specialist coding agent",
        "personality": "precise, thorough, security-conscious",
        "capabilities": [
            "code review",
            "code generation",
            "refactoring",
            "debugging",
        ],
        "output_format": "Use code blocks with language tags. Explain changes briefly.",
    },
    "knowledge-agent": {
        "description": "a knowledge retrieval and research specialist",
        "personality": "accurate, well-sourced, comprehensive",
        "capabilities": ["web search", "document analysis", "fact checking"],
        "output_format": "Cite sources when possible. Structure answers with headers.",
    },
    "data-agent": {
        "description": "a data analysis and statistics specialist",
        "personality": "analytical, precise, data-driven",
        "capabilities": ["statistical analysis", "data visualization", "pandas/SQL"],
        "output_format": "Include data tables and statistics. Recommend visualizations.",
    },
    "security-agent": {
        "description": "a security audit and vulnerability assessment specialist",
        "personality": "thorough, cautious, OWASP-focused",
        "capabilities": [
            "code security review",
            "dependency scanning",
            "threat modeling",
        ],
        "output_format": "Categorize findings by severity: Critical > High > Medium > Low > Info.",
    },
    "devops-agent": {
        "description": "a DevOps and infrastructure management specialist",
        "personality": "reliable, automation-focused, safety-first",
        "capabilities": ["Docker", "Kubernetes", "CI/CD", "monitoring"],
        "output_format": "Include command examples. Warn about destructive operations.",
    },
    "writing-agent": {
        "description": "a technical writing and documentation specialist",
        "personality": "clear, concise, well-structured",
        "capabilities": ["documentation", "blog posts", "API docs", "README"],
        "output_format": "Use markdown formatting. Include code examples where relevant.",
    },
    "research-agent": {
        "description": "a deep research and analysis specialist",
        "personality": "thorough, multi-perspective, evidence-based",
        "capabilities": [
            "market analysis",
            "competitive research",
            "literature review",
        ],
        "output_format": "Structure as: Summary -> Methodology -> Findings -> Recommendations.",
    },
    "ops-agent": {
        "description": "a system operations and monitoring specialist",
        "personality": "alert, diagnostic, action-oriented",
        "capabilities": [
            "monitoring",
            "incident response",
            "performance analysis",
        ],
        "output_format": "Lead with severity assessment. Include actionable next steps.",
    },
    "calendar-agent": {
        "description": "a calendar and scheduling specialist",
        "personality": "organized, time-aware, conflict-detecting",
        "capabilities": [
            "scheduling",
            "conflict detection",
            "meeting preparation",
        ],
        "output_format": "Use structured event format. Flag conflicts clearly.",
    },
    "comms-agent": {
        "description": "a communication and messaging specialist",
        "personality": "professional, empathetic, concise",
        "capabilities": [
            "email drafting",
            "message triage",
            "notification management",
        ],
        "output_format": "Match the tone of the original message. Be concise.",
    },
}

_DEFAULT_CONFIG: dict[str, Any] = {
    "description": "a general-purpose AI assistant",
    "personality": "helpful, accurate, concise",
    "capabilities": [],
    "output_format": "",
}

# Task-specific base prompts.
_TASK_PROMPTS: dict[str, str] = {
    "decompose": (
        "You are a task decomposition engine. Break the given task into "
        "clear, actionable sub-tasks. Each sub-task should be independently "
        "executable and have a well-defined output."
    ),
    "review": (
        "You are a quality reviewer. Evaluate the provided output for "
        "correctness, completeness, clarity, and adherence to requirements. "
        "Provide specific, actionable feedback."
    ),
    "summarize": (
        "You are a summarization engine. Produce a concise summary that "
        "captures the key points, decisions, and action items."
    ),
    "extract": (
        "You are an entity extraction engine. Identify and extract "
        "structured entities (names, dates, values, relationships) from "
        "the provided text. Return them in a structured format."
    ),
    "plan": (
        "You are a planning engine. Given the objective and constraints, "
        "produce a step-by-step execution plan with estimated effort, "
        "dependencies, and risk factors."
    ),
    "debug": (
        "You are a debugging specialist. Analyze the provided error, "
        "traceback, or unexpected behaviour. Identify root causes and "
        "suggest targeted fixes."
    ),
}


class SystemPromptFactory:
    """Factory for creating system prompts for different agent types.

    Provides pre-configured :class:`PromptBuilder` flows for each agent
    specialisation, with support for dynamic context injection.
    """

    @staticmethod
    def for_agent(agent_name: str, **context: Any) -> str:
        """Generate a system prompt for a specific agent with context.

        Parameters
        ----------
        agent_name:
            Canonical agent name (e.g. ``"code-agent"``).
        **context:
            Optional keys: ``tools``, ``skills``, ``constraints``,
            ``memory_context``, ``knowledge_context``, ``few_shot_examples``.
        """
        config = _AGENT_CONFIGS.get(agent_name, _DEFAULT_CONFIG)

        builder = PromptBuilder(max_tokens=6000)
        builder.add_system_identity(
            agent_name,
            config["description"],
            config.get("personality", ""),
        )
        builder.add_capabilities(
            tools=context.get("tools", config.get("capabilities", [])),
            skills=context.get("skills"),
        )

        if config.get("output_format"):
            builder.add_output_format(config["output_format"])

        if context.get("constraints"):
            builder.add_constraints(context["constraints"])
        if context.get("memory_context"):
            builder.add_memory_context(context["memory_context"])
        if context.get("knowledge_context"):
            builder.add_knowledge_context(context["knowledge_context"])
        if context.get("few_shot_examples"):
            builder.add_few_shot(context["few_shot_examples"])

        return builder.build()

    @staticmethod
    def for_task(task_type: str, **context: Any) -> str:
        """Generate a task-specific system prompt.

        Parameters
        ----------
        task_type:
            One of ``decompose``, ``review``, ``summarize``, ``extract``,
            ``plan``, ``debug``.
        **context:
            Optional keys: ``constraints``.
        """
        base = _TASK_PROMPTS.get(
            task_type, "You are a helpful AI assistant."
        )
        builder = PromptBuilder()
        builder.add_section("task_prompt", base, priority=1, required=True)
        if context.get("constraints"):
            builder.add_constraints(context["constraints"])
        return builder.build()

    @staticmethod
    def available_agents() -> list[str]:
        """Return the list of known agent names."""
        return sorted(_AGENT_CONFIGS)

    @staticmethod
    def available_tasks() -> list[str]:
        """Return the list of known task types."""
        return sorted(_TASK_PROMPTS)
