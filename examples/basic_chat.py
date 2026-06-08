#!/usr/bin/env python3
"""basic_chat.py -- Agent routing and chat demonstration.

Shows how JARVIS routes user messages to specialist agents based on
intent scoring, handles multiple conversation turns, and recovers
from routing failures gracefully.

Run:
    python examples/basic_chat.py
"""

from __future__ import annotations

import asyncio
import sys

# ---------------------------------------------------------------------------
# Graceful import
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult
    from jarvis.agents.registry import AgentRegistry
    from jarvis.agents.orchestrator import Orchestrator
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    print("Make sure you are running from the project root with the venv active.")
    sys.exit(1)

console = Console()

# ---------------------------------------------------------------------------
# Demo agents (lightweight, no LLM needed)
# ---------------------------------------------------------------------------

class DemoCodeAgent(BaseAgent):
    """Handles code-related requests."""

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="code",
            description="Write, review, and debug code",
            skills=["code", "python", "debug", "review", "programming", "bug"],
            domain="development",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"[Code Agent] Analysed your request: '{message[:60]}...' -- ready to help with code!",
        )


class DemoResearchAgent(BaseAgent):
    """Handles research and knowledge queries."""

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="research",
            description="Research topics, summarise documents, answer questions",
            skills=["research", "search", "summarise", "explain", "knowledge"],
            domain="research",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"[Research Agent] Researched: '{message[:60]}...' -- here are my findings.",
        )


class DemoWritingAgent(BaseAgent):
    """Handles writing and documentation tasks."""

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="writing",
            description="Write documentation, emails, reports",
            skills=["write", "document", "email", "report", "draft"],
            domain="writing",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"[Writing Agent] Drafted content for: '{message[:60]}...'",
        )


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Basic Chat Demo[/bold cyan]",
                        subtitle="Agent Routing & Conversation"))

    # Step 1: Set up the agent registry
    console.print("\n[bold]1. Setting up agent registry...[/bold]")
    registry = AgentRegistry()
    await registry.register(DemoCodeAgent())
    await registry.register(DemoResearchAgent())
    await registry.register(DemoWritingAgent())
    console.print(f"   Registered {len(registry)} agents")

    # Step 2: Create the orchestrator
    console.print("\n[bold]2. Creating orchestrator...[/bold]")
    orchestrator = Orchestrator(registry)

    # Step 3: Show routing scores for a sample message
    console.print("\n[bold]3. Routing analysis for sample messages:[/bold]")
    sample_messages = [
        "Fix the bug in the login function",
        "Summarise this research paper about LLMs",
        "Write a status report for the sprint",
        "What time is it?",  # no agent should match well
    ]

    for msg in sample_messages:
        candidates = registry.route(msg)
        table = Table(title=f"'{msg[:50]}'", show_lines=False)
        table.add_column("Agent", style="cyan")
        table.add_column("Score", justify="right", style="green")
        if candidates:
            for agent, score in candidates:
                table.add_row(agent.name, f"{score:.2f}")
        else:
            table.add_row("(no match)", "0.00")
        console.print(table)

    # Step 4: Send messages through the orchestrator
    console.print("\n[bold]4. Orchestrator routing and execution:[/bold]")
    for msg in sample_messages:
        result = await orchestrator.handle(msg)
        if result.success:
            console.print(f"   [green]OK[/green] -> {result.agent_name}: {result.output[:80]}")
        else:
            console.print(f"   [red]FAIL[/red] -> {result.error}")

    # Step 5: Multi-turn conversation with context
    console.print("\n[bold]5. Multi-turn conversation:[/bold]")
    context = AgentContext()
    turns = [
        "Review my Python code for security issues",
        "Now write tests for those issues",
        "Explain the OWASP top 10",
    ]
    for turn_msg in turns:
        result = await orchestrator.handle(turn_msg, context)
        console.print(f"   User: {turn_msg}")
        console.print(f"   JARVIS ({result.agent_name}): {result.output[:80]}")
        console.print()

    # Step 6: Show conversation history
    console.print("[bold]6. Conversation history:[/bold]")
    for msg in context.history:
        console.print(f"   [{msg.role.value}] {msg.content[:80]}")

    # Step 7: Show delegation log
    console.print(f"\n[bold]7. Delegation log:[/bold] {len(orchestrator.get_delegation_log())} entries")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
