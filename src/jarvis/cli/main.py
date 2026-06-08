from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from jarvis.app import JarvisApp
from jarvis.models.streaming_spec import StepStatus

app = typer.Typer(name="jarvis", help="JARVIS — Streaming Spec driven personal AI assistant")
console = Console()

STATUS_ICONS = {
    StepStatus.PENDING: "[dim]⏳[/dim]",
    StepStatus.PLANNING: "[yellow]📝[/yellow]",
    StepStatus.EXECUTING: "[blue]🔄[/blue]",
    StepStatus.COMPLETED: "[green]✅[/green]",
    StepStatus.SKIPPED: "[dim]⏭️[/dim]",
}


def _run(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)


async def _init_app() -> JarvisApp:
    j = JarvisApp()
    await j.initialize()
    return j


def _render_spec(spec) -> None:
    status_color = {
        "planning": "yellow", "executing": "blue", "paused": "red",
        "completed": "green", "redirected": "magenta",
    }.get(spec.status.value, "white")

    console.print(Panel(
        f"[bold]{spec.name}[/bold]\n"
        f"Intent: {spec.intent}\n"
        f"Status: [{status_color}]{spec.status.value}[/{status_color}]  |  Progress: {spec.progress}",
        title=f"Spec [{spec.id}]",
        border_style=status_color,
    ))

    if spec.constraints:
        console.print("\n[bold]Constraints:[/bold]")
        for c in spec.constraints:
            active = "✓" if c.active else "✗"
            console.print(f"  {active} [{c.id}] {c.content}  [dim]({c.added_by.value})[/dim]")

    if spec.steps:
        console.print("\n[bold]Steps:[/bold]")
        for i, step in enumerate(spec.steps, 1):
            icon = STATUS_ICONS.get(step.status, "?")
            console.print(f"  {icon} {i}. {step.name}  [dim]({step.status.value})[/dim]")
            if step.output:
                console.print(f"      └─ {step.output}")
    console.print()


# ─── Spec commands ───

spec_app = typer.Typer(help="Streaming Spec management")
app.add_typer(spec_app, name="spec")


@spec_app.command("create")
def spec_create(intent: str = typer.Argument(help="Task intent description")):
    """Create a new Streaming Spec from an intent."""
    async def _do():
        j = await _init_app()
        return await j.spec_engine.create(intent)

    spec = _run(_do())
    console.print(f"[green]Created Streaming Spec:[/green] {spec.id}\n")
    _render_spec(spec)


@spec_app.command("list")
def spec_list():
    """List all active Streaming Specs."""
    async def _do():
        j = await _init_app()
        return j.spec_engine.list_specs()

    specs = _run(_do())
    if not specs:
        console.print("[dim]No active specs.[/dim]")
        return
    table = Table(title="Active Streaming Specs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Progress")
    for s in specs:
        table.add_row(s.id, s.name, s.status.value, s.progress)
    console.print(table)


@spec_app.command("run")
def spec_run(intent: str = typer.Argument(help="Task intent to create and execute")):
    """Create a Streaming Spec and execute it through agents."""
    async def _do():
        j = await _init_app()
        spec = await j.spec_engine.create(intent)
        console.print(f"[green]Created spec:[/green] {spec.id}")
        _render_spec(spec)
        console.print("[blue]Executing...[/blue]\n")
        result = await j.executor.execute_spec(spec.id)
        if result:
            _render_spec(result)
        return result

    _run(_do())


# ─── Agent commands ───

agent_app = typer.Typer(help="Agent management")
app.add_typer(agent_app, name="agent")


@agent_app.command("list")
def agent_list():
    """List all registered agents."""
    async def _do():
        j = await _init_app()
        return j.registry.list_agents()

    agents = _run(_do())
    table = Table(title="Registered Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Domain")
    table.add_column("Skills")
    table.add_column("Status")
    for a in agents:
        table.add_row(
            a.name,
            a.card.domain,
            ", ".join(a.card.skills[:3]) + ("..." if len(a.card.skills) > 3 else ""),
            a.status.value,
        )
    console.print(table)


@agent_app.command("chat")
def agent_chat(message: str = typer.Argument(help="Message to send to agents")):
    """Send a message to the orchestrator for routing."""
    async def _do():
        j = await _init_app()
        return await j.orchestrator.handle(message)

    result = _run(_do())
    if result.success:
        console.print(f"[cyan]{result.agent_name}[/cyan] → {result.output}")
    else:
        console.print(f"[red]Error:[/red] {result.error}")


@agent_app.command("route")
def agent_route(message: str = typer.Argument(help="Message to score agents against")):
    """Show how the orchestrator would route a message."""
    async def _do():
        j = await _init_app()
        return j.registry.route(message)

    candidates = _run(_do())
    if not candidates:
        console.print("[dim]No agents can handle this message.[/dim]")
        return
    table = Table(title="Agent Routing Scores")
    table.add_column("Agent", style="cyan")
    table.add_column("Score")
    table.add_column("Domain")
    for agent, score in candidates:
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        table.add_row(agent.name, f"{score:.2f} {bar}", agent.card.domain)
    console.print(table)


# ─── Memory commands ───

memory_app = typer.Typer(help="Memory management")
app.add_typer(memory_app, name="memory")


@memory_app.command("add")
def memory_add(
    content: str = typer.Argument(help="Memory content to store"),
    memory_type: str = typer.Option("fact", help="Type: fact, preference, conversation, skill_learned, spec_history"),
):
    """Add a memory entry."""
    from jarvis.memory import MemoryManager, MemoryType

    async def _do():
        mm = MemoryManager()
        return await mm.add(content, MemoryType(memory_type))

    entry = _run(_do())
    console.print(f"[green]Added memory:[/green] {entry.id[:8]}  (type={entry.memory_type.value}, importance={entry.importance:.2f})")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(help="Search query"),
    limit: int = typer.Option(5, help="Max results"),
):
    """Search memories by keyword."""
    from jarvis.memory import MemoryManager

    async def _do():
        mm = MemoryManager()
        return await mm.search(query, limit)

    results = _run(_do())
    if not results:
        console.print("[dim]No matching memories.[/dim]")
        return
    table = Table(title=f"Memory Search: '{query}'")
    table.add_column("ID", style="cyan", max_width=10)
    table.add_column("Type")
    table.add_column("Content", max_width=60)
    table.add_column("Importance")
    for e in results:
        table.add_row(e.id[:8], e.memory_type.value, e.content[:60], f"{e.importance:.2f}")
    console.print(table)


@memory_app.command("list")
def memory_list():
    """List all stored memories."""
    from jarvis.memory import MemoryManager

    mm = MemoryManager()
    entries = mm.list_memories()
    if not entries:
        console.print("[dim]No memories stored.[/dim]")
        return
    table = Table(title="Stored Memories")
    table.add_column("ID", style="cyan", max_width=10)
    table.add_column("Type")
    table.add_column("Content", max_width=60)
    table.add_column("Importance")
    table.add_column("Keywords")
    for e in entries:
        table.add_row(
            e.id[:8],
            e.memory_type.value,
            e.content[:60],
            f"{e.importance:.2f}",
            ", ".join(e.keywords[:4]),
        )
    console.print(table)


# ─── Knowledge commands ───

knowledge_app = typer.Typer(help="Knowledge graph management")
app.add_typer(knowledge_app, name="knowledge")


@knowledge_app.command("stats")
def knowledge_stats():
    """Show knowledge graph statistics."""
    from jarvis.knowledge.graph import KnowledgeGraph

    kg = KnowledgeGraph()
    stats = kg.stats
    console.print(Panel(
        f"Nodes: {stats['nodes']}\n"
        f"Edges: {stats['edges']}\n"
        f"Node types: {json.dumps(stats.get('node_types', {}))}\n"
        f"Relation types: {json.dumps(stats.get('relation_types', {}))}",
        title="Knowledge Graph Stats",
    ))


@knowledge_app.command("extract")
def knowledge_extract(text: str = typer.Argument(help="Text to extract entities from")):
    """Extract entities and relations from text."""
    from jarvis.knowledge.graph import KnowledgeGraph

    async def _do():
        kg = KnowledgeGraph()
        return await kg.extract_from_text(text)

    nodes = _run(_do())
    if not nodes:
        console.print("[dim]No entities extracted.[/dim]")
        return
    table = Table(title="Extracted Entities")
    table.add_column("ID", style="cyan")
    table.add_column("Label")
    table.add_column("Type")
    for n in nodes:
        table.add_row(n.id, n.label, n.node_type)
    console.print(table)


@knowledge_app.command("query")
def knowledge_query(question: str = typer.Argument(help="Question to query the knowledge graph")):
    """Query the knowledge graph."""
    from jarvis.knowledge.graph import KnowledgeGraph

    async def _do():
        kg = KnowledgeGraph()
        return await kg.query(question)

    nodes = _run(_do())
    if not nodes:
        console.print("[dim]No matching nodes found.[/dim]")
        return
    table = Table(title=f"Knowledge Query: '{question}'")
    table.add_column("ID", style="cyan")
    table.add_column("Label")
    table.add_column("Type")
    table.add_column("Properties")
    for n in nodes:
        table.add_row(n.id, n.label, n.node_type, json.dumps(n.properties)[:50])
    console.print(table)


# ─── Skill commands ───

skill_app = typer.Typer(help="Skill management")
app.add_typer(skill_app, name="skill")


@skill_app.command("list")
def skill_list():
    """List all registered skills."""
    from jarvis.skills import SkillRegistry

    registry = SkillRegistry()
    registry.load_directory()
    skills = registry.list_skills()
    if not skills:
        console.print("[dim]No skills registered.[/dim]")
        return
    table = Table(title="Registered Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Domain")
    table.add_column("Status")
    table.add_column("Uses")
    table.add_column("Success Rate")
    for s in skills:
        table.add_row(
            s.metadata.name,
            s.metadata.version,
            s.metadata.domain or "-",
            s.status.value,
            str(s.use_count),
            f"{s.success_rate:.0%}",
        )
    console.print(table)


# ─── Tool commands ───

tool_app = typer.Typer(help="Tool management")
app.add_typer(tool_app, name="tool")


@tool_app.command("list")
def tool_list():
    """List all registered tools."""
    async def _do():
        j = await _init_app()
        return j._tool_registry.list_tools() if j._tool_registry else []

    tools = _run(_do())
    if not tools:
        console.print("[dim]No tools registered.[/dim]")
        return
    table = Table(title="Registered Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Description", max_width=60)
    for t in tools:
        table.add_row(t.name, t.description[:60])
    console.print(table)


@tool_app.command("run")
def tool_run(
    name: str = typer.Argument(help="Tool name to execute"),
    args: str = typer.Option("{}", help="JSON arguments"),
):
    """Execute a tool by name with JSON arguments."""
    import json as _json

    async def _do():
        j = await _init_app()
        if not j._tool_registry:
            console.print("[red]Tool registry not initialized[/red]")
            raise typer.Exit(1)
        arguments = _json.loads(args)
        return await j._tool_registry.execute(name, arguments)

    result = _run(_do())
    if result.success:
        console.print(f"[green]Success:[/green] {result.output}")
    else:
        console.print(f"[red]Failed:[/red] {result.output}")


# ─── System info ───

@app.command("info")
def system_info():
    """Show JARVIS system information."""
    async def _do():
        j = await _init_app()
        return j

    j = _run(_do())

    table = Table(title="JARVIS System Information", show_header=False)
    table.add_column("Property", style="bold cyan")
    table.add_column("Value")

    table.add_row("Version", "0.2.0")
    table.add_row("Agents", str(len(j.registry)))
    table.add_row("Tools", str(len(j._tool_registry.list_tools()) if j._tool_registry else 0))
    table.add_row("Active Specs", str(len(j.spec_engine.list_specs())))
    table.add_row("Agent Specs", str(len(j.spec_registry.list_specs())))

    # Module status
    modules = {
        "Agents": True,
        "Tools": j._tool_registry is not None,
        "Skills": hasattr(j, '_skill_registry'),
        "Memory": hasattr(j, '_memory_manager'),
        "Knowledge Graph": True,
        "Curator": hasattr(j, '_curator'),
        "Sessions": hasattr(j, '_session_manager'),
        "MCP": hasattr(j, '_mcp_registry'),
        "Gateway": hasattr(j, '_gateway'),
    }
    for mod_name, active in modules.items():
        status = "[green]active[/green]" if active else "[dim]not initialized[/dim]"
        table.add_row(f"  {mod_name}", status)

    console.print(table)


# ─── Server commands ───

server_app = typer.Typer(help="API server management")
app.add_typer(server_app, name="server")


@server_app.command("start")
def server_start(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
):
    """Start the JARVIS API server."""
    import uvicorn
    console.print(f"[green]Starting JARVIS server on {host}:{port}[/green]")
    uvicorn.run("jarvis.server.app:app", host=host, port=port, reload=True)


@app.command("ui")
def launch_tui():
    """Launch the interactive TUI."""
    from jarvis.tui.app import run_tui

    asyncio.run(run_tui())


# ─── Workflow commands ───

workflow_app = typer.Typer(help="Workflow management")
app.add_typer(workflow_app, name="workflow")


@workflow_app.command("list")
def workflow_list(
    status: str = typer.Option(None, help="Filter by status"),
    tag: str = typer.Option(None, help="Filter by tag"),
    limit: int = typer.Option(50, help="Max results"),
):
    """List all workflows."""
    import httpx

    try:
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        if tag:
            params["tag"] = tag
        resp = httpx.get("http://127.0.0.1:8000/workflows", params=params, timeout=5)
        data = resp.json()
        workflows = data.get("workflows", [])
        if not workflows:
            console.print("[dim]No workflows found.[/dim]")
            return
        table = Table(title="Workflows")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Steps")
        table.add_column("Runs")
        for wf in workflows:
            table.add_row(
                wf["id"],
                wf["name"],
                wf["status"],
                str(len(wf.get("steps", []))),
                str(wf.get("execution_count", 0)),
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error connecting to server:[/red] {exc}")
        console.print("[dim]Make sure the server is running (jarvis server start)[/dim]")


@workflow_app.command("create")
def workflow_create(
    name: str = typer.Argument(help="Workflow name"),
    description: str = typer.Option("", help="Workflow description"),
):
    """Create a new workflow."""
    import httpx

    try:
        resp = httpx.post(
            "http://127.0.0.1:8000/workflows",
            json={"name": name, "description": description},
            timeout=5,
        )
        wf = resp.json()
        console.print(f"[green]Created workflow:[/green] {wf['id']}")
        console.print(Panel(
            f"Name: {wf['name']}\n"
            f"Status: {wf['status']}\n"
            f"Steps: {len(wf.get('steps', []))}\n"
            f"Created: {wf.get('created_at', 'N/A')}",
            title=f"Workflow [{wf['id']}]",
        ))
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


@workflow_app.command("run")
def workflow_run(
    wf_id: str = typer.Argument(help="Workflow ID to execute"),
):
    """Execute a workflow."""
    import httpx

    try:
        console.print(f"[blue]Executing workflow {wf_id}...[/blue]")
        resp = httpx.post(
            f"http://127.0.0.1:8000/workflows/{wf_id}/execute",
            timeout=30,
        )
        if resp.status_code == 404:
            console.print(f"[red]Workflow '{wf_id}' not found[/red]")
            return
        wf = resp.json()
        console.print(f"[green]Workflow completed:[/green] {wf['status']}")
        for step in wf.get("steps", []):
            icon = "[green]v[/green]" if step["status"] == "completed" else "[red]x[/red]"
            console.print(f"  {icon} {step['name']}: {step.get('output', '')}")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


@workflow_app.command("templates")
def workflow_templates():
    """List available workflow templates."""
    import httpx

    try:
        resp = httpx.get("http://127.0.0.1:8000/templates/specs", timeout=5)
        templates = resp.json()
        if not templates:
            console.print("[dim]No templates available.[/dim]")
            return
        table = Table(title="Workflow Templates")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Variables")
        table.add_column("Tags")
        for t in templates:
            table.add_row(
                t["name"],
                t.get("description", ""),
                ", ".join(t.get("variables", [])),
                ", ".join(t.get("tags", [])),
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


# ─── Event commands ───

event_app = typer.Typer(help="Event bus management")
app.add_typer(event_app, name="event")


@event_app.command("list")
def event_list(
    topic: str = typer.Option(None, help="Filter by topic"),
    limit: int = typer.Option(20, help="Max results"),
):
    """List recent events."""
    import httpx

    try:
        params: dict = {"limit": limit}
        if topic:
            params["topic"] = topic
        resp = httpx.get("http://127.0.0.1:8000/events", params=params, timeout=5)
        data = resp.json()
        events = data.get("events", [])
        if not events:
            console.print("[dim]No events found.[/dim]")
            return
        table = Table(title=f"Events (total: {data.get('total', 0)})")
        table.add_column("ID", style="cyan")
        table.add_column("Topic")
        table.add_column("Source")
        table.add_column("Priority")
        table.add_column("Timestamp")
        for evt in events:
            table.add_row(
                evt["id"],
                evt["topic"],
                evt.get("source", ""),
                evt.get("priority", "normal"),
                evt.get("timestamp", "")[:19],
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


@event_app.command("publish")
def event_publish(
    topic: str = typer.Argument(help="Event topic"),
    payload: str = typer.Option("{}", help="JSON payload"),
    source: str = typer.Option("cli", help="Event source"),
):
    """Publish an event to the event bus."""
    import httpx

    try:
        import json as _json
        body = {
            "topic": topic,
            "payload": _json.loads(payload),
            "source": source,
        }
        resp = httpx.post("http://127.0.0.1:8000/events/publish", json=body, timeout=5)
        evt = resp.json()
        console.print(f"[green]Published event:[/green] {evt['id']} (topic={evt['topic']})")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


# ─── Notification commands ───

notification_app = typer.Typer(help="Notification management")
app.add_typer(notification_app, name="notification")


@notification_app.command("list")
def notification_list(
    level: str = typer.Option(None, help="Filter by level (info/warning/error)"),
    unread: bool = typer.Option(False, help="Show only unread"),
    limit: int = typer.Option(20, help="Max results"),
):
    """List notifications."""
    import httpx

    try:
        params: dict = {"limit": limit}
        if level:
            params["level"] = level
        if unread:
            params["read"] = False
        resp = httpx.get("http://127.0.0.1:8000/notifications", params=params, timeout=5)
        data = resp.json()
        notifs = data.get("notifications", [])
        if not notifs:
            console.print("[dim]No notifications.[/dim]")
            return
        table = Table(title=f"Notifications (total: {data.get('total', 0)})")
        table.add_column("ID", style="cyan")
        table.add_column("Level")
        table.add_column("Title")
        table.add_column("Read")
        table.add_column("Created")
        for n in notifs:
            read_status = "[green]Yes[/green]" if n["read"] else "[red]No[/red]"
            table.add_row(
                n["id"],
                n["level"],
                n["title"],
                read_status,
                n.get("created_at", "")[:19],
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


@notification_app.command("send")
def notification_send(
    title: str = typer.Argument(help="Notification title"),
    body: str = typer.Option("", help="Notification body"),
    level: str = typer.Option("info", help="Level: info/warning/error/critical"),
):
    """Send a notification."""
    import httpx

    try:
        resp = httpx.post(
            "http://127.0.0.1:8000/notifications",
            json={"title": title, "body": body, "level": level},
            timeout=5,
        )
        notif = resp.json()
        console.print(f"[green]Sent notification:[/green] {notif['id']} ({notif['level']})")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


# ─── Diagnostics ───

@app.command("diagnose")
def diagnose():
    """Run system diagnostics."""
    import httpx

    try:
        resp = httpx.get("http://127.0.0.1:8000/diagnostics", timeout=10)
        data = resp.json()
        status_color = "green" if data["status"] == "healthy" else "yellow"
        console.print(Panel(
            f"[{status_color}]Status: {data['status']}[/{status_color}]",
            title="System Diagnostics",
        ))
        table = Table(show_header=True)
        table.add_column("Check", style="bold")
        table.add_column("Value")
        for k, v in data.get("checks", {}).items():
            display = str(v)
            if isinstance(v, bool):
                display = "[green]Pass[/green]" if v else "[red]Fail[/red]"
            table.add_row(k.replace("_", " ").title(), display)
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error connecting to server:[/red] {exc}")
        console.print("[dim]Running offline diagnostics...[/dim]")
        import platform
        import sys
        console.print(f"  Python: {sys.version}")
        console.print(f"  Platform: {platform.platform()}")
        console.print(f"  Machine: {platform.machine()}")


@app.command("benchmark")
def benchmark():
    """Run a performance benchmark."""
    import httpx

    try:
        console.print("[blue]Running benchmarks...[/blue]")
        resp = httpx.get("http://127.0.0.1:8000/diagnostics/benchmark", timeout=30)
        data = resp.json()
        console.print(Panel(
            f"Status: {data['status']}",
            title="Benchmark Results",
        ))
        table = Table(title="Performance")
        table.add_column("Operation", style="cyan")
        table.add_column("Duration (ms)")
        for k, v in data.get("benchmarks", {}).items():
            name = k.replace("_", " ").replace(" ms", "").title()
            table.add_row(name, f"{v:.2f} ms")
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")


# ─── Migration commands ───

migration_app = typer.Typer(help="Migration tools")
app.add_typer(migration_app, name="migration")


@migration_app.command("validate")
def migration_validate(
    source: str = typer.Argument(help="Source platform (hermes/openclaw)"),
    path: str = typer.Argument(help="Path to source data directory"),
):
    """Validate a migration source before running."""
    import os

    console.print(f"[blue]Validating migration source:[/blue] {source} at {path}")

    checks = []
    if not os.path.isdir(path):
        checks.append(("Directory exists", False, f"'{path}' not found"))
    else:
        checks.append(("Directory exists", True, path))

        # Check for expected files
        expected_files = {
            "hermes": ["config.yaml", "agents/", "workflows/"],
            "openclaw": ["manifest.json", "skills/", "plugins/"],
        }
        source_files = expected_files.get(source, ["config.yaml"])
        for expected in source_files:
            full_path = os.path.join(path, expected)
            exists = os.path.exists(full_path)
            checks.append((f"Has {expected}", exists, full_path if exists else "missing"))

    table = Table(title=f"Migration Validation: {source}")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for name, passed, detail in checks:
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        table.add_row(name, status, detail)
    console.print(table)

    all_passed = all(c[1] for c in checks)
    if all_passed:
        console.print("[green]Validation passed. Ready to migrate.[/green]")
    else:
        console.print("[red]Validation failed. Fix issues before migrating.[/red]")


@migration_app.command("run")
def migration_run(
    source: str = typer.Argument(help="Source platform (hermes/openclaw)"),
    path: str = typer.Argument(help="Path to source data directory"),
    dry_run: bool = typer.Option(False, help="Preview changes without applying"),
):
    """Run a migration from another platform."""
    from jarvis.migration import MigrationEngine

    async def _do():
        engine = MigrationEngine()
        if source == "hermes":
            result = await engine.migrate_from_hermes(path, dry_run=dry_run)
        elif source == "openclaw":
            result = await engine.migrate_from_openclaw(path, dry_run=dry_run)
        else:
            console.print(f"[red]Unknown source platform: {source}[/red]")
            return None
        return result

    try:
        result = _run(_do())
        if result is None:
            return
        mode = "[yellow]DRY RUN[/yellow]" if dry_run else "[green]EXECUTED[/green]"
        console.print(f"\n{mode} Migration from {source}")
        console.print(Panel(
            f"Items migrated: {result.get('migrated', 0)}\n"
            f"Items skipped: {result.get('skipped', 0)}\n"
            f"Errors: {result.get('errors', 0)}\n"
            f"Warnings: {result.get('warnings', 0)}",
            title="Migration Results",
        ))
    except Exception as exc:
        console.print(f"[red]Migration failed:[/red] {exc}")


if __name__ == "__main__":
    app()
