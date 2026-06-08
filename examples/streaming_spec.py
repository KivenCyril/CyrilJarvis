#!/usr/bin/env python3
"""streaming_spec.py -- Streaming Spec lifecycle demonstration.

Shows the core JARVIS innovation: Streaming Specs -- real-time editable
task control panels that allow mid-execution constraint changes, DAG
visualisation, and spec redirection.

Run:
    python examples/streaming_spec.py
"""

from __future__ import annotations

import asyncio
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.tree import Tree
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.models.streaming_spec import (
        ChangeSource,
        Constraint,
        SpecStatus,
        StepStatus,
        StreamingSpec,
    )
    from jarvis.engine.spec_engine import SpecEngine
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


def show_spec(spec: StreamingSpec, title: str = "Spec") -> None:
    """Render a spec as a Rich table."""
    table = Table(title=f"{title}: {spec.name} (v{spec.version})")
    table.add_column("#", style="dim")
    table.add_column("Step", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Depends On", style="dim")
    table.add_column("Output", style="green", max_width=40)

    for i, step in enumerate(spec.steps, 1):
        status_style = {
            "pending": "white",
            "ready": "yellow",
            "executing": "blue",
            "completed": "green",
            "failed": "red",
            "blocked": "dim",
        }.get(step.status.value, "white")
        deps = ", ".join(step.depends_on) if step.depends_on else "-"
        output = (step.output or "")[:40]
        table.add_row(
            str(i),
            step.name,
            f"[{status_style}]{step.status.value}[/{status_style}]",
            deps,
            output,
        )
    console.print(table)


def show_dag(spec: StreamingSpec) -> None:
    """Visualise the spec's DAG as a Rich tree."""
    tree = Tree(f"[bold]{spec.name}[/bold] DAG")
    step_map = {s.id: s for s in spec.steps}
    roots = [s for s in spec.steps if not s.depends_on]

    def _add_children(parent_tree: Tree, parent_id: str) -> None:
        children = [s for s in spec.steps if parent_id in s.depends_on]
        for child in children:
            child_tree = parent_tree.add(f"{child.name} [{child.status.value}]")
            _add_children(child_tree, child.id)

    for root in roots:
        root_tree = tree.add(f"[cyan]{root.name}[/cyan] [{root.status.value}]")
        _add_children(root_tree, root.id)

    console.print(tree)


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Streaming Spec Demo[/bold cyan]",
                        subtitle="Real-time Editable Task Control Panel"))

    # Step 1: Create a spec from intent (mock mode, no LLM)
    console.print("\n[bold]1. Creating spec from intent...[/bold]")
    engine = SpecEngine()  # no LLM = uses fallback steps
    spec = await engine.create(
        intent="Build a REST API for user authentication with JWT tokens",
        name="Auth API",
    )
    console.print(f"   Spec ID: {spec.id}")
    console.print(f"   Status: {spec.status.value}")
    console.print(f"   Steps: {len(spec.steps)}")
    show_spec(spec, "Initial Spec")

    # Step 2: View DAG structure
    console.print("\n[bold]2. DAG structure:[/bold]")
    # Add dependencies to make the DAG interesting
    if len(spec.steps) >= 4:
        spec.add_dependency(spec.steps[1].id, spec.steps[0].id)
        spec.add_dependency(spec.steps[2].id, spec.steps[1].id)
        spec.add_dependency(spec.steps[3].id, spec.steps[2].id)
    spec.update_step_readiness()
    show_dag(spec)
    console.print(f"   DAG valid: {spec.validate_dag()}")

    # Step 3: Add constraints mid-execution
    console.print("\n[bold]3. Adding constraints mid-execution...[/bold]")
    c1 = await engine.add_constraint(spec.id, "Use bcrypt for password hashing")
    c2 = await engine.add_constraint(spec.id, "Support OAuth2 flow")
    c3 = await engine.add_constraint(
        spec.id, "Rate limit: 100 req/min per user",
        source=ChangeSource.AGENT,
    )

    console.print("   Active constraints:")
    for c in spec.constraints:
        console.print(f"   - [{c.added_by.value}] {c.content}")

    # Step 4: Execute with progress tracking
    console.print("\n[bold]4. Simulating execution with progress...[/bold]")
    for step in spec.steps:
        # Mark as executing
        await engine.update_step(spec.id, step.id, status=StepStatus.EXECUTING)
        console.print(f"   Executing: {step.name}...")

        # Simulate work
        await asyncio.sleep(0.1)

        # Mark as completed with output
        await engine.update_step(
            spec.id, step.id,
            status=StepStatus.COMPLETED,
            output=f"Done: {step.name}",
        )
        console.print(f"   Progress: {spec.progress}")

    show_spec(spec, "After Execution")

    # Step 5: View changelog
    console.print("\n[bold]5. Changelog (last 10 entries):[/bold]")
    table = Table()
    table.add_column("Type", style="cyan")
    table.add_column("Source", style="yellow")
    table.add_column("Path", style="dim")
    table.add_column("New Value", max_width=40)
    for change in spec.changelog[-10:]:
        table.add_row(
            change.change_type.value,
            change.source.value,
            change.path,
            str(change.new_value)[:40] if change.new_value else "-",
        )
    console.print(table)

    # Step 6: Modify a constraint
    console.print("\n[bold]6. Removing a constraint...[/bold]")
    removed = await engine.remove_constraint(spec.id, spec.constraints[0].id)
    if removed:
        console.print(f"   Removed: {removed.content}")
    console.print(f"   Remaining constraints: {len(spec.constraints)}")

    # Step 7: Redirect the spec
    console.print("\n[bold]7. Redirecting spec to new intent...[/bold]")
    redirected = await engine.redirect(
        spec.id,
        "Build auth API with JWT + add WebSocket support for real-time notifications",
    )
    if redirected:
        console.print(f"   New intent: {redirected.intent[:80]}")
        console.print(f"   Status: {redirected.status.value}")
        console.print(f"   Version: {redirected.version}")
        show_spec(redirected, "After Redirect")

    # Step 8: Critical path
    console.print("\n[bold]8. Critical path analysis:[/bold]")
    cp = spec.critical_path()
    if cp:
        console.print(f"   Critical path ({len(cp)} steps):")
        for step in cp:
            console.print(f"   -> {step.name}")
    else:
        console.print("   (no critical path -- spec was redirected)")

    # Step 9: Topological sort
    console.print("\n[bold]9. Topological sort:[/bold]")
    topo = spec.topological_sort()
    for i, step in enumerate(topo, 1):
        console.print(f"   {i}. {step.name}")

    # Summary
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"   Elapsed: {spec.elapsed_time:.1f}s")
    console.print(f"   Version: {spec.version}")
    console.print(f"   Changelog entries: {len(spec.changelog)}")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
