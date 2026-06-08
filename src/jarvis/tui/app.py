"""Main TUI Application for JARVIS.

Provides an interactive Rich-based terminal experience with multiple views:
dashboard, chat, spec management, tools, skills, memory, and knowledge graph.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from rich.console import Console
from rich.columns import Columns
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from jarvis.app import JarvisApp

logger = logging.getLogger(__name__)
console = Console()


class TUIApp:
    """Rich terminal user interface for JARVIS.

    Provides an interactive terminal experience with:
    - Dashboard view (system overview)
    - Chat view (agent interaction)
    - Spec view (streaming spec management)
    - Tool view (tool listing and execution)
    - Skill view (skill management)
    - Memory view (memory browsing)
    - Knowledge view (knowledge graph)
    - Settings view
    """

    BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"""

    COMMANDS = [
        ("help", "h", "Show this help"),
        ("dashboard", "d", "Show system dashboard"),
        ("chat <msg>", "c", "Chat with agents (or just type a message)"),
        ("agents", "a", "List all agents with details"),
        ("tools", "t", "List all available tools"),
        ("spec <intent>", "s", "Create and execute a Streaming Spec"),
        ("skills", "", "List all skills"),
        ("memory <query>", "m", "Search or list memories"),
        ("knowledge <q>", "k", "Query the knowledge graph"),
        ("clear", "", "Clear screen"),
        ("quit", "q", "Exit JARVIS"),
    ]

    def __init__(self) -> None:
        self.jarvis = JarvisApp()
        self._running = False
        self._current_view = "dashboard"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the TUI application."""
        console.clear()
        self._print_banner()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Initializing JARVIS...", total=None)
            await self.jarvis.initialize()

        console.print("[green]> JARVIS initialized[/green]")
        self._print_status_bar()

        self._running = True
        await self._main_loop()

    def _print_banner(self) -> None:
        console.print(
            Panel(
                Text(self.BANNER, style="cyan")
                + Text("\n\n  Streaming Spec Driven Personal AI Assistant", style="dim"),
                border_style="cyan",
            )
        )

    def _print_status_bar(self) -> None:
        agents = len(self.jarvis.registry)
        tools = (
            len(self.jarvis._tool_registry.list_tools())
            if self.jarvis._tool_registry
            else 0
        )
        specs = len(self.jarvis.spec_engine.list_specs())
        console.print(
            f"  [green]>[/green] {agents} agents  "
            f"[blue]>[/blue] {tools} tools  "
            f"[yellow]>[/yellow] {specs} active specs  "
            f"[dim]Type 'help' for commands[/dim]"
        )
        console.print()

    # ------------------------------------------------------------------
    # Main loop & command routing
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        """Main interactive loop."""
        while self._running:
            try:
                cmd = Prompt.ask("[bold cyan]jarvis[/bold cyan]")
                if not cmd.strip():
                    continue
                await self._handle_command(cmd.strip())
            except KeyboardInterrupt:
                if Confirm.ask("\n[yellow]Exit JARVIS?[/yellow]"):
                    await self._shutdown()
                    break
            except EOFError:
                await self._shutdown()
                break

    async def _handle_command(self, cmd: str) -> None:
        """Route commands to handlers."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers: dict[str, Any] = {
            "help": self._cmd_help,
            "h": self._cmd_help,
            "dashboard": self._cmd_dashboard,
            "d": self._cmd_dashboard,
            "chat": self._cmd_chat,
            "c": self._cmd_chat,
            "agents": self._cmd_agents,
            "a": self._cmd_agents,
            "tools": self._cmd_tools,
            "t": self._cmd_tools,
            "spec": self._cmd_spec,
            "s": self._cmd_spec,
            "skills": self._cmd_skills,
            "memory": self._cmd_memory,
            "m": self._cmd_memory,
            "knowledge": self._cmd_knowledge,
            "k": self._cmd_knowledge,
            "clear": self._cmd_clear,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
            "q": self._cmd_quit,
        }

        handler = handlers.get(command)
        if handler:
            await handler(args)
        else:
            # Default: treat as chat message
            await self._cmd_chat(cmd)

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------

    async def _cmd_help(self, args: str = "") -> None:
        """Show help."""
        table = Table(title="JARVIS Commands", show_lines=True)
        table.add_column("Command", style="cyan", width=15)
        table.add_column("Shortcut", style="dim", width=8)
        table.add_column("Description")

        for cmd, shortcut, desc in self.COMMANDS:
            table.add_row(cmd, shortcut, desc)
        console.print(table)

    async def _cmd_dashboard(self, args: str = "") -> None:
        """Show system dashboard."""
        from jarvis.tui.views import DashboardView

        console.print()
        console.print("[bold]System Dashboard[/bold]", style="cyan")
        console.print()

        # Agents table
        agent_table = DashboardView.render_agent_cards(
            self.jarvis.registry.list_agents()
        )
        console.print(agent_table)

        # Tools summary
        if self.jarvis._tool_registry:
            tools = self.jarvis._tool_registry.list_tools()
            tool_table = Table(
                title=f"Tools ({len(tools)})", show_lines=True, expand=True
            )
            tool_table.add_column("Name", style="cyan")
            tool_table.add_column("Description")
            for tool in tools[:15]:
                tool_table.add_row(tool.name, tool.description[:60])
            if len(tools) > 15:
                tool_table.add_row("...", f"and {len(tools) - 15} more")
            console.print(tool_table)

        # Specs
        specs = self.jarvis.spec_engine.list_specs()
        if specs:
            spec_table = Table(
                title="Active Specs", show_lines=True, expand=True
            )
            spec_table.add_column("ID", style="cyan")
            spec_table.add_column("Name")
            spec_table.add_column("Status")
            spec_table.add_column("Progress")
            for spec in specs[:10]:
                spec_table.add_row(
                    spec.id[:8], spec.name[:40], spec.status.value, spec.progress
                )
            console.print(spec_table)

        # System tree
        tree = DashboardView.render_system_tree(self.jarvis)
        console.print(tree)

    async def _cmd_chat(self, args: str = "") -> None:
        """Chat with agents."""
        if not args:
            args = Prompt.ask("[dim]Message[/dim]")
            if not args:
                return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Thinking...", total=None)
            result = await self.jarvis.orchestrator.handle(args)

        if result.success:
            from jarvis.tui.views import ChatView

            panel = ChatView.render_message("agent", result.output, result.agent_name)
            console.print(panel)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    async def _cmd_agents(self, args: str = "") -> None:
        """List agents with details."""
        if args:
            # Show specific agent
            agent = self.jarvis.registry.get(args)
            if agent:
                tree = Tree(f"[bold cyan]{agent.name}[/bold cyan]")
                tree.add(f"Domain: {agent.card.domain}")
                tree.add(f"Description: {agent.card.description}")
                tree.add(f"Status: {agent.status.value}")
                skills_branch = tree.add("Skills")
                for skill in agent.card.skills:
                    skills_branch.add(skill)
                tree.add(f"Can delegate: {agent.card.can_delegate}")
                console.print(tree)
            else:
                console.print(f"[red]Agent '{args}' not found[/red]")
            return

        # List all
        for agent in self.jarvis.registry.list_agents():
            console.print(
                f"  [cyan]{agent.name}[/cyan] [{agent.card.domain}] "
                f"-- {agent.card.description[:50]}"
            )

    async def _cmd_tools(self, args: str = "") -> None:
        """List and optionally run tools."""
        if not self.jarvis._tool_registry:
            console.print("[dim]No tools available[/dim]")
            return

        if args.startswith("run "):
            # Run a specific tool
            parts = args[4:].split(maxsplit=1)
            tool_name = parts[0]
            tool_args_str = parts[1] if len(parts) > 1 else "{}"

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {"command": tool_args_str}

            with Progress(
                SpinnerColumn(), TextColumn("Executing..."), transient=True
            ) as p:
                p.add_task("", total=None)
                result = await self.jarvis._tool_registry.execute(
                    tool_name, tool_args
                )

            status = "[green]>[/green]" if result.success else "[red]x[/red]"
            console.print(f"{status} {result.output}")
            return

        # List tools
        table = Table(title="Available Tools", show_lines=True)
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        for tool in self.jarvis._tool_registry.list_tools():
            table.add_row(tool.name, tool.description[:70])
        console.print(table)

    async def _cmd_spec(self, args: str = "") -> None:
        """Create and manage Streaming Specs."""
        if not args:
            # List specs
            specs = self.jarvis.spec_engine.list_specs()
            if not specs:
                console.print(
                    "[dim]No active specs. Use 'spec <intent>' to create one.[/dim]"
                )
                return
            for spec in specs:
                status_icon = {
                    "planning": "[yellow]planning[/yellow]",
                    "executing": "[blue]executing[/blue]",
                    "completed": "[green]completed[/green]",
                    "failed": "[red]failed[/red]",
                    "paused": "[yellow]paused[/yellow]",
                }.get(spec.status.value, spec.status.value)
                console.print(
                    f"  {status_icon} [{spec.id[:8]}] {spec.name} -- {spec.progress}"
                )
            return

        # Create and execute spec
        console.print(f"\n[bold]Creating Streaming Spec[/bold]: {args}")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Decomposing intent...", total=None)
            spec = await self.jarvis.spec_engine.create(args)

        console.print(
            f"[green]> Created spec[/green] [{spec.id[:8]}] "
            f"with {len(spec.steps)} steps:"
        )
        for i, step in enumerate(spec.steps, 1):
            deps = ""
            if step.depends_on:
                dep_names = ", ".join(d[:6] for d in step.depends_on)
                deps = f" (depends: {dep_names})"
            console.print(f"  {i}. {step.name}{deps}")

        if Confirm.ask("\nExecute now?"):
            console.print("\n[blue]Executing...[/blue]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
            ) as progress:
                task = progress.add_task(
                    "Executing spec", total=len(spec.steps)
                )
                result = await self.jarvis.executor.execute_spec(spec.id)
                progress.update(task, completed=len(spec.steps))

            if result:
                console.print(
                    f"\n[green]> Spec completed[/green]: {result.progress}"
                )
                for step in result.steps:
                    icon = (
                        "[green]done[/green]"
                        if step.status.value == "completed"
                        else "[red]fail[/red]"
                    )
                    output_preview = (step.output or "")[:60]
                    console.print(f"  {icon} {step.name}: {output_preview}")

    async def _cmd_skills(self, args: str = "") -> None:
        """List skills."""
        try:
            from jarvis.skills import SkillRegistry

            registry = SkillRegistry()
            registry.load_directory("skills/builtin")

            table = Table(title="Skills", show_lines=True)
            table.add_column("Name", style="cyan")
            table.add_column("Domain", style="green")
            table.add_column("Version")
            table.add_column("Steps")
            for skill in registry.list_skills():
                table.add_row(
                    skill.metadata.name,
                    skill.metadata.domain,
                    skill.metadata.version,
                    str(len(skill.steps)),
                )
            console.print(table)
        except Exception as e:
            console.print(f"[dim]Skills: {e}[/dim]")

    async def _cmd_memory(self, args: str = "") -> None:
        """Memory management."""
        from jarvis.memory import MemoryManager, MemoryType

        mm = MemoryManager()

        if args:
            results = await mm.search(args)
            if results:
                for r in results:
                    console.print(
                        f"  [{r.memory_type.value}] {r.content[:80]} "
                        f"[dim](importance={r.importance:.2f})[/dim]"
                    )
            else:
                console.print("[dim]No matching memories found.[/dim]")
        else:
            memories = mm.list_memories()
            console.print(
                f"[dim]Total memories: {len(memories)}. "
                f"Use 'memory <query>' to search.[/dim]"
            )

    async def _cmd_knowledge(self, args: str = "") -> None:
        """Knowledge graph query."""
        stats = self.jarvis.knowledge_graph.stats
        console.print(
            f"[bold]Knowledge Graph[/bold]: "
            f"{stats['nodes']} nodes, {stats['edges']} edges"
        )

        if args:
            results = await self.jarvis.knowledge_graph.query(args)
            if results:
                for node in results:
                    neighbors = self.jarvis.knowledge_graph.neighbors(node.id)
                    console.print(f"  [cyan]{node.label}[/cyan] ({node.node_type})")
                    for edge, neighbor in neighbors[:3]:
                        console.print(
                            f"    -> {edge.relation} -> {neighbor.label}"
                        )
            else:
                console.print("[dim]No relevant nodes found.[/dim]")

    async def _cmd_clear(self, args: str = "") -> None:
        """Clear screen and reprint banner."""
        console.clear()
        self._print_banner()
        self._print_status_bar()

    async def _cmd_quit(self, args: str = "") -> None:
        """Exit the TUI."""
        await self._shutdown()
        self._running = False

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def _shutdown(self) -> None:
        console.print("\n[dim]Shutting down...[/dim]")
        await self.jarvis.shutdown()
        console.print("[green]Goodbye![/green]")


async def run_tui() -> None:
    """Entry point for the TUI."""
    app = TUIApp()
    await app.start()
