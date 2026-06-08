#!/usr/bin/env python3
"""dag_workflows.py -- DAG-based parallel execution demonstration.

Shows how to build specs with custom dependency graphs, including
diamond dependencies, parallel branches, critical path analysis,
and DAG validation.

Run:
    python examples/dag_workflows.py
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
        SpecStatus,
        StepStatus,
        StreamingSpec,
    )
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


def render_dag(spec: StreamingSpec) -> None:
    """Render the DAG as a tree and a table."""
    # Table view
    table = Table(title=f"DAG: {spec.name}")
    table.add_column("Step ID", style="dim", width=10)
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Depends On", style="yellow")
    for step in spec.steps:
        deps = ", ".join(step.depends_on) if step.depends_on else "(root)"
        status_style = {"ready": "green", "blocked": "red", "completed": "cyan"}.get(
            step.status.value, "white"
        )
        table.add_row(
            step.id[:8],
            step.name,
            f"[{status_style}]{step.status.value}[/{status_style}]",
            deps,
        )
    console.print(table)


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- DAG Workflows Demo[/bold cyan]",
                        subtitle="Parallel Execution & Dependency Graphs"))

    # -------------------------------------------------------------------
    # 1. Diamond dependency pattern
    #
    #       A
    #      / \
    #     B   C
    #      \ /
    #       D
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Diamond dependency pattern:[/bold]")
    spec = StreamingSpec(name="Diamond DAG", intent="Test diamond dependencies")
    spec.status = SpecStatus.EXECUTING

    step_a = spec.add_step("Fetch data", "Download raw data from API")
    step_b = spec.add_step("Parse JSON", "Parse response body", depends_on=[step_a.id])
    step_c = spec.add_step("Validate schema", "Check data against schema", depends_on=[step_a.id])
    step_d = spec.add_step("Store results", "Save to database", depends_on=[step_b.id, step_c.id])

    spec.update_step_readiness()
    render_dag(spec)

    console.print(f"   DAG valid: {spec.validate_dag()}")
    console.print(f"   Ready steps: {[s.name for s in spec.get_ready_steps()]}")
    console.print(f"   Blocked steps: {[s.name for s in spec.get_blocked_steps()]}")

    # -------------------------------------------------------------------
    # 2. Parallel branch execution
    #
    #       Start
    #      / | \
    #     A  B  C   (parallel)
    #      \ | /
    #      Merge
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Parallel branch execution:[/bold]")
    par_spec = StreamingSpec(name="Parallel Branches", intent="Test parallel execution")
    par_spec.status = SpecStatus.EXECUTING

    s_start = par_spec.add_step("Start", "Initialize pipeline")
    s_a = par_spec.add_step("Branch A: Lint", "Run linter", depends_on=[s_start.id])
    s_b = par_spec.add_step("Branch B: Test", "Run unit tests", depends_on=[s_start.id])
    s_c = par_spec.add_step("Branch C: Scan", "Security scan", depends_on=[s_start.id])
    s_merge = par_spec.add_step("Merge", "Collect results", depends_on=[s_a.id, s_b.id, s_c.id])

    par_spec.update_step_readiness()
    render_dag(par_spec)

    # Simulate execution
    console.print("\n   Simulating execution:")

    # Execute Start
    par_spec.update_step_status(s_start.id, StepStatus.COMPLETED)
    par_spec.update_step_readiness()
    ready = par_spec.get_ready_steps()
    console.print(f"   After Start: {len(ready)} parallel branches ready: {[s.name for s in ready]}")

    # Execute parallel branches
    for branch in [s_a, s_b, s_c]:
        par_spec.update_step_status(branch.id, StepStatus.EXECUTING)
    await asyncio.sleep(0.1)
    for branch in [s_a, s_b, s_c]:
        par_spec.update_step_status(branch.id, StepStatus.COMPLETED)
        par_spec.set_step_output(branch.id, f"OK: {branch.name}")

    par_spec.update_step_readiness()
    ready = par_spec.get_ready_steps()
    console.print(f"   After branches: merge ready: {[s.name for s in ready]}")

    # Execute Merge
    par_spec.update_step_status(s_merge.id, StepStatus.COMPLETED)
    console.print(f"   Progress: {par_spec.progress}")

    # -------------------------------------------------------------------
    # 3. Complex DAG with multiple layers
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Complex multi-layer DAG:[/bold]")
    complex_spec = StreamingSpec(name="ML Pipeline", intent="Train and deploy ML model")
    complex_spec.status = SpecStatus.EXECUTING

    # Layer 0: data sources (parallel)
    d1 = complex_spec.add_step("Load dataset A", "Load from S3")
    d2 = complex_spec.add_step("Load dataset B", "Load from DB")

    # Layer 1: preprocessing (each depends on a data source)
    p1 = complex_spec.add_step("Clean A", "Preprocess dataset A", depends_on=[d1.id])
    p2 = complex_spec.add_step("Clean B", "Preprocess dataset B", depends_on=[d2.id])

    # Layer 2: merge (depends on both preprocessing steps)
    m = complex_spec.add_step("Merge datasets", "Join cleaned data", depends_on=[p1.id, p2.id])

    # Layer 3: parallel model training
    t1 = complex_spec.add_step("Train model v1", "Random Forest", depends_on=[m.id])
    t2 = complex_spec.add_step("Train model v2", "XGBoost", depends_on=[m.id])

    # Layer 4: compare and deploy
    cmp = complex_spec.add_step("Compare models", "Select best", depends_on=[t1.id, t2.id])
    deploy = complex_spec.add_step("Deploy winner", "Push to prod", depends_on=[cmp.id])

    complex_spec.update_step_readiness()
    render_dag(complex_spec)

    # -------------------------------------------------------------------
    # 4. Critical path analysis
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Critical path analysis:[/bold]")
    cp = complex_spec.critical_path()
    console.print(f"   Critical path length: {len(cp)} steps")
    for i, step in enumerate(cp, 1):
        console.print(f"   {i}. {step.name}")

    # -------------------------------------------------------------------
    # 5. Topological sort
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Topological sort order:[/bold]")
    topo = complex_spec.topological_sort()
    for i, step in enumerate(topo, 1):
        deps_str = ", ".join(step.depends_on[:2]) if step.depends_on else "(root)"
        console.print(f"   {i}. {step.name}  [dim](deps: {deps_str})[/dim]")

    # -------------------------------------------------------------------
    # 6. Cycle detection
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Cycle detection:[/bold]")
    console.print(f"   Valid DAG (no cycles): {complex_spec.validate_dag()}")

    # Try to create a cycle
    cycle_spec = StreamingSpec(name="Cycle Test", intent="Test cycle detection")
    sa = cycle_spec.add_step("A")
    sb = cycle_spec.add_step("B", depends_on=[sa.id])
    sc = cycle_spec.add_step("C", depends_on=[sb.id])
    # Attempt to add A->C dependency (which would create C->B->A->C cycle)
    ok = cycle_spec.add_dependency(sa.id, sc.id)
    console.print(f"   Adding cycle A->C: {'allowed' if ok else 'rejected (cycle detected!)'}")
    console.print(f"   DAG still valid: {cycle_spec.validate_dag()}")

    # -------------------------------------------------------------------
    # 7. Dynamic dependency management
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Dynamic dependency management:[/bold]")
    dyn_spec = StreamingSpec(name="Dynamic DAG", intent="Test dynamic deps")
    dyn_spec.status = SpecStatus.EXECUTING
    s1 = dyn_spec.add_step("Step 1")
    s2 = dyn_spec.add_step("Step 2")
    s3 = dyn_spec.add_step("Step 3")

    console.print("   Initial: no dependencies")
    dyn_spec.update_step_readiness()
    console.print(f"   Ready: {[s.name for s in dyn_spec.get_ready_steps()]}")

    # Add dependency: Step 2 depends on Step 1
    dyn_spec.add_dependency(s2.id, s1.id)
    dyn_spec.update_step_readiness()
    console.print(f"   After S2->S1 dep, ready: {[s.name for s in dyn_spec.get_ready_steps()]}")

    # Complete Step 1
    dyn_spec.update_step_status(s1.id, StepStatus.COMPLETED)
    dyn_spec.update_step_readiness()
    console.print(f"   After S1 complete, ready: {[s.name for s in dyn_spec.get_ready_steps()]}")

    # Remove dependency
    dyn_spec.remove_dependency(s2.id, s1.id)
    console.print(f"   After removing dep, DAG valid: {dyn_spec.validate_dag()}")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
