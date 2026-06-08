#!/usr/bin/env python3
"""JARVIS -- Interactive Demo Script

Demonstrates all major capabilities:
1. System initialization (10 agents, 20+ tools)
2. Agent chat routing
3. Streaming Spec creation + DAG execution
4. Constraint editing mid-execution
5. Knowledge graph extraction
6. Memory storage and retrieval
7. Skill distillation from completed specs
8. Curator quality review
9. Session management
10. Observability traces
"""
import asyncio
import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

console = Console()


async def demo():
    console.print(Panel.fit(
        "[bold cyan]JARVIS -- Streaming Spec Driven Personal AI Assistant[/bold cyan]\n"
        "[dim]Interactive Demo | v0.2.0[/dim]",
        border_style="cyan",
    ))

    # ------------------------------------------------------------------ 1
    console.print("\n[bold]1. System Initialization[/bold]")
    from jarvis.app import JarvisApp

    app = JarvisApp()
    await app.initialize()

    # Show agents table
    table = Table(title="Registered Agents", show_lines=True)
    table.add_column("Agent", style="cyan")
    table.add_column("Domain", style="green")
    table.add_column("Skills")
    for agent in app.registry.list_agents():
        skills_str = ", ".join(agent.card.skills[:4])
        if len(agent.card.skills) > 4:
            skills_str += "..."
        table.add_row(agent.name, agent.card.domain, skills_str)
    console.print(table)

    # Show tools table
    tool_list = app._tool_registry.list_tools() if app._tool_registry else []
    table2 = Table(title="Available Tools")
    table2.add_column("Tool", style="cyan")
    table2.add_column("Description")
    for tool in tool_list:
        table2.add_row(tool.name, tool.description[:60])
    console.print(table2)

    agent_count = len(app.registry)
    tool_count = len(tool_list)
    console.print(
        f"[green]>> System ready: {agent_count} agents, {tool_count} tools[/green]\n"
    )

    # ------------------------------------------------------------------ 2
    console.print("[bold]2. Agent Routing Demo[/bold]")
    test_messages = [
        "review this code for security issues",
        "analyze the CSV data and generate statistics",
        "schedule a meeting for Friday",
        "check the Kubernetes cluster health",
        "draft a technical blog post about AI agents",
    ]
    for msg in test_messages:
        result = await app.orchestrator.handle(msg)
        console.print(f"  [dim]'{msg}'[/dim] -> [cyan]{result.agent_name}[/cyan]")

    # ------------------------------------------------------------------ 3
    console.print("\n[bold]3. Streaming Spec (DAG Execution)[/bold]")
    spec = await app.spec_engine.create("Build a REST API for user management")

    console.print(
        f"  Created spec: [cyan]{spec.id}[/cyan] ({len(spec.steps)} steps)"
    )
    status_icons = {
        "pending": "[-]",
        "ready": "[o]",
        "executing": "[~]",
        "completed": "[+]",
    }
    for step in spec.steps:
        deps = ""
        if step.depends_on:
            deps = f" (depends: {', '.join(step.depends_on)})"
        icon = status_icons.get(step.status.value, "[?]")
        console.print(f"    {icon} {step.name}{deps}")

    # Add constraint
    console.print("\n  [yellow]Adding constraint: 'Use FastAPI framework'[/yellow]")
    await app.spec_engine.add_constraint(spec.id, "Use FastAPI framework")

    # Execute
    console.print("  [blue]Executing spec...[/blue]")
    result_spec = await app.executor.execute_spec(spec.id)
    if result_spec:
        console.print(f"  [green]>> Spec completed: {result_spec.progress}[/green]")
        for step in result_spec.steps:
            icon = "[+]" if step.status.value == "completed" else "[-]"
            output_preview = (step.output or "")[:60]
            console.print(f"    {icon} {step.name}: {output_preview}")

    # ------------------------------------------------------------------ 4
    console.print("\n[bold]4. Knowledge Graph[/bold]")
    from jarvis.knowledge.graph import GraphEdge, GraphNode

    app.knowledge_graph.add_node(
        GraphNode(id="python", label="Python", node_type="language")
    )
    app.knowledge_graph.add_node(
        GraphNode(id="fastapi", label="FastAPI", node_type="framework")
    )
    app.knowledge_graph.add_node(
        GraphNode(id="rest_api", label="REST API", node_type="concept")
    )
    app.knowledge_graph.add_edge(
        GraphEdge(source="fastapi", target="python", relation="built_with")
    )
    app.knowledge_graph.add_edge(
        GraphEdge(source="rest_api", target="fastapi", relation="implemented_by")
    )

    stats = app.knowledge_graph.stats
    console.print(f"  Graph: {stats['nodes']} nodes, {stats['edges']} edges")
    console.print(f"  Node types: {stats.get('node_types', {})}")

    # Query (keyword mode -- no LLM)
    kg_results = await app.knowledge_graph.query("What framework for REST APIs?")
    console.print(f"  Query results: {[n.label for n in kg_results]}")

    # ------------------------------------------------------------------ 5
    console.print("\n[bold]5. Memory System[/bold]")
    from jarvis.memory import MemoryManager, MemoryType

    mm = MemoryManager("/tmp/jarvis_demo_memory")
    await mm.add(
        "User prefers Python and FastAPI for backend projects",
        MemoryType.PREFERENCE,
    )
    await mm.add("Project uses PostgreSQL database", MemoryType.FACT)
    await mm.add("Completed REST API spec successfully", MemoryType.SPEC_HISTORY)

    mem_results = await mm.search("Python backend")
    console.print(
        f"  Stored 3 memories, search 'Python backend': {len(mem_results)} results"
    )
    for r in mem_results:
        console.print(
            f"    [{r.memory_type.value}] {r.content[:60]} "
            f"(importance={r.importance:.2f})"
        )

    # ------------------------------------------------------------------ 6
    console.print("\n[bold]6. Skill System[/bold]")
    from jarvis.skills import SkillEvolver, SkillRegistry

    skill_registry = SkillRegistry("/tmp/jarvis_demo_skills")
    evolver = SkillEvolver(skill_registry)

    # Distill from completed spec
    if result_spec:
        skill = await evolver.distill_from_spec(result_spec)
        console.print(
            f"  Distilled skill: [cyan]{skill.metadata.name}[/cyan] "
            f"v{skill.metadata.version}"
        )
        console.print(
            f"  Steps: {len(skill.steps)}, Status: {skill.status.value}"
        )
        console.print(
            f"  Registry: {len(skill_registry.list_skills())} skills loaded"
        )

    # ------------------------------------------------------------------ 7
    console.print("\n[bold]7. Curator Review[/bold]")
    from jarvis.curator import Curator

    curator = Curator()
    review = await curator.review_output(
        request="Build a REST API",
        output=(
            "Created UserController with CRUD endpoints using FastAPI. "
            "All endpoints validated with Pydantic."
        ),
        constraints=["Use FastAPI framework"],
    )
    verdict_color = "green" if review.verdict.value == "approved" else "red"
    console.print(
        f"  Verdict: [{verdict_color}]{review.verdict.value}[/]"
    )
    console.print(
        f"  Score: {review.score:.2f}, "
        f"Hallucination risk: {review.hallucination_risk:.2f}"
    )
    if review.issues:
        console.print(f"  Issues: {review.issues}")

    # ------------------------------------------------------------------ 8
    console.print("\n[bold]8. Session Management[/bold]")
    from jarvis.session import SessionManager

    sm = SessionManager("/tmp/jarvis_demo_sessions")
    session = sm.create(user_id="demo-user", channel="cli")
    session.add_message("user", "Build a REST API for user management")
    session.add_message(
        "agent", "Created spec with 4 steps", agent_name="code-agent"
    )
    console.print(
        f"  Session: {session.id[:8]}... "
        f"({session.message_count} messages, "
        f"{len(session.agents_used)} agents)"
    )

    # ------------------------------------------------------------------ 9
    console.print("\n[bold]9. Observability[/bold]")
    from jarvis.observability.metrics import metrics
    from jarvis.observability.tracer import Tracer

    t = Tracer()
    trace_id = t.start_trace("demo")
    async with t.trace_operation(trace_id, "agent_execution", agent="code-agent"):
        await asyncio.sleep(0.01)  # simulate work
    async with t.trace_operation(trace_id, "tool_call", tool="shell_execute"):
        await asyncio.sleep(0.01)

    metrics.counter("requests_total").inc()
    metrics.histogram("response_time_ms").observe(150.5)
    metrics.histogram("response_time_ms").observe(200.3)

    trace = t.get_trace(trace_id)
    console.print(f"  Trace: {len(trace)} spans")
    snapshot = metrics.snapshot()
    console.print(
        f"  Metrics: {len(snapshot['counters'])} counters, "
        f"{len(snapshot['histograms'])} histograms"
    )

    # ------------------------------------------------------------------ 10
    console.print("\n[bold]10. System Summary[/bold]")
    tree = Tree("[bold cyan]JARVIS v0.2.0[/bold cyan]")
    tree.add(f"[green]Agents[/green]: {agent_count} registered")
    tree.add(f"[green]Tools[/green]: {tool_count} available")
    tree.add(
        f"[green]Specs[/green]: {len(app.spec_engine.list_specs())} active"
    )
    tree.add(
        f"[green]Knowledge[/green]: "
        f"{app.knowledge_graph.stats['nodes']} nodes, "
        f"{app.knowledge_graph.stats['edges']} edges"
    )
    tree.add(f"[green]Memory[/green]: {len(mm.list_memories())} entries")
    tree.add(
        f"[green]Skills[/green]: {len(skill_registry.list_skills())} registered"
    )
    tree.add(f"[green]Sessions[/green]: {len(sm.list_sessions())} active")
    console.print(tree)

    await app.shutdown()
    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(demo())
