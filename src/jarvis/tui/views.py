"""Specialized Rich views for the JARVIS TUI.

DashboardView: system overview tables and trees.
ChatView: agent message rendering.
SpecView: Streaming Spec detail and DAG visualization.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()


# ======================================================================
# DashboardView
# ======================================================================


class DashboardView:
    """Renders the system dashboard with live updates."""

    @staticmethod
    def render_agent_cards(agents: list[Any]) -> Table:
        """Render agents as a formatted table with status indicators."""
        table = Table(title="Agents", show_lines=True, expand=True)
        table.add_column("Name", style="cyan")
        table.add_column("Domain", style="green")
        table.add_column("Status")
        table.add_column("Skills")

        for agent in agents:
            if agent.status.value == "idle":
                status = "[green]>[/green] idle"
            else:
                status = f"[yellow]>[/yellow] {agent.status.value}"

            skills = ", ".join(agent.card.skills[:3])
            if len(agent.card.skills) > 3:
                skills += f" +{len(agent.card.skills) - 3}"

            table.add_row(agent.name, agent.card.domain, status, skills)

        return table

    @staticmethod
    def render_spec_timeline(specs: list[Any]) -> Panel:
        """Render specs as a timeline with status colors."""
        lines: list[str] = []
        for spec in specs:
            color = {
                "planning": "yellow",
                "executing": "blue",
                "completed": "green",
                "failed": "red",
                "paused": "yellow",
                "redirected": "magenta",
            }.get(spec.status.value, "white")
            lines.append(
                f"[{color}]{spec.status.value:>10}[/{color}] "
                f"[cyan]{spec.id[:8]}[/cyan] {spec.name} -- {spec.progress}"
            )

        if not lines:
            lines.append("[dim]No active specs[/dim]")

        return Panel("\n".join(lines), title="Spec Timeline", border_style="yellow")

    @staticmethod
    def render_system_tree(app: Any) -> Tree:
        """Render full system tree with all module stats."""
        tree = Tree("[bold cyan]JARVIS v0.2.0[/bold cyan]")

        # Agents branch
        agents = app.registry.list_agents()
        agents_branch = tree.add(f"[green]Agents[/green] ({len(agents)})")
        for agent in agents:
            agents_branch.add(f"{agent.name} [{agent.card.domain}]")

        # Tools branch
        tool_count = (
            len(app._tool_registry.list_tools()) if app._tool_registry else 0
        )
        tools_branch = tree.add(f"[blue]Tools[/blue] ({tool_count})")
        if app._tool_registry:
            categories: dict[str, list[str]] = {}
            for tool in app._tool_registry.list_tools():
                cat = tool.name.split("_")[0] if "_" in tool.name else "general"
                categories.setdefault(cat, []).append(tool.name)
            for cat, names in categories.items():
                cat_branch = tools_branch.add(f"{cat}/ ({len(names)})")
                for name in names:
                    cat_branch.add(name)

        # Specs branch
        specs = app.spec_engine.list_specs()
        specs_branch = tree.add(f"[yellow]Specs[/yellow] ({len(specs)})")
        for spec in specs:
            specs_branch.add(f"{spec.name} [{spec.status.value}] {spec.progress}")

        # Knowledge branch
        kg = app.knowledge_graph.stats
        tree.add(f"[magenta]Knowledge[/magenta] ({kg['nodes']} nodes, {kg['edges']} edges)")

        return tree


# ======================================================================
# ChatView
# ======================================================================


class ChatView:
    """Renders chat messages with agent attribution."""

    @staticmethod
    def render_message(
        role: str, content: str, agent_name: str = ""
    ) -> Panel:
        """Render a single chat message as a Rich Panel."""
        if role == "user":
            return Panel(content, title="You", border_style="blue", title_align="left")

        color = "green" if "code" in agent_name else "cyan"

        # Attempt markdown rendering for rich content
        if "```" in content or "#" in content:
            body: Text | Markdown = Markdown(content)
        else:
            body = Text(content)

        return Panel(
            body,
            title=agent_name or "JARVIS",
            border_style=color,
            title_align="left",
        )

    @staticmethod
    def render_conversation(messages: list[dict[str, str]]) -> None:
        """Render a full conversation history."""
        for msg in messages:
            panel = ChatView.render_message(
                msg.get("role", ""),
                msg.get("content", ""),
                msg.get("agent", ""),
            )
            console.print(panel)


# ======================================================================
# SpecView
# ======================================================================


class SpecView:
    """Renders Streaming Spec details and DAG visualizations."""

    STATUS_ICONS = {
        "pending": "[dim]pending[/dim]",
        "planning": "[yellow]planning[/yellow]",
        "ready": "[blue]ready[/blue]",
        "blocked": "[yellow]blocked[/yellow]",
        "executing": "[blue]running[/blue]",
        "completed": "[green]done[/green]",
        "failed": "[red]failed[/red]",
        "skipped": "[dim]skipped[/dim]",
        "cancelled": "[dim]cancelled[/dim]",
    }

    @classmethod
    def render_spec_detail(cls, spec: Any) -> None:
        """Render full spec details including constraints and steps."""
        status_color = {
            "planning": "yellow",
            "executing": "blue",
            "paused": "red",
            "completed": "green",
            "failed": "red",
            "redirected": "magenta",
        }.get(spec.status.value, "white")

        console.print(
            Panel(
                f"[bold]{spec.name}[/bold]\n"
                f"Intent: {spec.intent}\n"
                f"Status: [{status_color}]{spec.status.value}[/{status_color}]"
                f"  |  Progress: {spec.progress}",
                title=f"Spec [{spec.id[:8]}]",
                border_style=status_color,
            )
        )

        # Constraints
        if spec.constraints:
            console.print("\n[bold]Constraints:[/bold]")
            for c in spec.constraints:
                active = "[green]>[/green]" if c.active else "[red]x[/red]"
                source = f"[dim]({c.added_by.value})[/dim]"
                console.print(f"  {active} {c.content} {source}")

        # Steps
        console.print("\n[bold]Steps (DAG):[/bold]")
        for step in spec.steps:
            icon = cls.STATUS_ICONS.get(step.status.value, "?")
            deps = ""
            if step.depends_on:
                dep_names: list[str] = []
                for dep_id in step.depends_on:
                    dep_step = spec.get_step(dep_id)
                    dep_names.append(
                        dep_step.name[:15] if dep_step else dep_id[:6]
                    )
                deps = f" <- [{', '.join(dep_names)}]"

            output_line = ""
            if step.output:
                output_line = f"\n      -- {step.output[:80]}"

            console.print(f"  {icon} {step.name}{deps}{output_line}")

        # Changelog summary
        if spec.changelog:
            console.print(f"\n[dim]Changelog: {len(spec.changelog)} changes[/dim]")

    @classmethod
    def render_dag_tree(cls, spec: Any) -> Tree:
        """Render spec DAG as a Rich tree.

        Root nodes (steps without dependencies) appear at the top level;
        their dependants are nested recursively below.
        """
        tree = Tree(f"[bold]{spec.name}[/bold] [{spec.status.value}]")

        # Build adjacency: parent -> list of children that depend on it
        children: dict[str, list[Any]] = {}
        roots: list[Any] = []
        step_map = {s.id: s for s in spec.steps}

        for step in spec.steps:
            if not step.depends_on:
                roots.append(step)
            for dep_id in step.depends_on:
                children.setdefault(dep_id, []).append(step)

        def _add_subtree(parent_tree: Tree, step: Any) -> None:
            icon = cls.STATUS_ICONS.get(step.status.value, "?")
            node = parent_tree.add(f"{icon} {step.name}")
            for child in children.get(step.id, []):
                _add_subtree(node, child)

        for root in roots:
            _add_subtree(tree, root)

        return tree
