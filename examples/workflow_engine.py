#!/usr/bin/env python3
"""workflow_engine.py -- Workflow engine demonstration.

Shows JARVIS's workflow engine: creating workflows with different step
types, conditional branching, loops, parallel execution, approval gates,
data transformations, and template instantiation.

Run:
    python examples/workflow_engine.py
"""

from __future__ import annotations

import asyncio
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.workflow.models import (
        ConditionalBranch,
        StepType,
        Workflow,
        WorkflowStatus,
        WorkflowStep,
        WorkflowVariable,
    )
    from jarvis.workflow.engine import WorkflowEngine
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


def show_workflow(wf: Workflow, title: str = "Workflow") -> None:
    """Render a workflow's steps as a Rich table."""
    table = Table(title=f"{title}: {wf.name} ({wf.status.value})")
    table.add_column("#", style="dim", width=3)
    table.add_column("Step", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Status", style="bold")
    table.add_column("Output", max_width=40)

    for i, step in enumerate(wf.steps, 1):
        status_style = {
            "completed": "green",
            "failed": "red",
            "running": "blue",
            "skipped": "dim",
            "pending": "white",
        }.get(step.status, "white")
        output = str(step.output)[:40] if step.output else "-"
        table.add_row(
            str(i),
            step.name,
            step.step_type.value,
            f"[{status_style}]{step.status}[/{status_style}]",
            output,
        )
    console.print(table)


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Workflow Engine Demo[/bold cyan]",
                        subtitle="Branching, Loops, Parallel, Approvals"))

    engine = WorkflowEngine()

    # -------------------------------------------------------------------
    # 1. Simple sequential workflow
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Simple sequential workflow:[/bold]")
    simple_wf = Workflow(name="Simple Deploy", description="Sequential deployment")
    simple_wf.add_step(WorkflowStep(id="build", name="Build", step_type=StepType.ACTION,
                                     action="Build Docker image"))
    simple_wf.add_step(WorkflowStep(id="test", name="Test", step_type=StepType.ACTION,
                                     action="Run tests", depends_on=["build"]))
    simple_wf.add_step(WorkflowStep(id="deploy", name="Deploy", step_type=StepType.ACTION,
                                     action="Deploy to staging", depends_on=["test"]))

    result = await engine.execute(simple_wf)
    show_workflow(result, "Sequential")
    console.print(f"   Progress: {result.progress}")

    # -------------------------------------------------------------------
    # 2. Workflow with conditions (if/else branching)
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Conditional branching:[/bold]")
    cond_wf = Workflow(name="Conditional Deploy")
    cond_wf.variables = [
        WorkflowVariable(name="test_score", value=0.95, var_type="number"),
    ]

    cond_wf.add_step(WorkflowStep(id="run_tests", name="Run Tests",
                                   step_type=StepType.ACTION, action="Execute test suite"))
    cond_wf.add_step(WorkflowStep(
        id="check_score", name="Check Score",
        step_type=StepType.CONDITION,
        condition="test_score > 0.8",
        on_true="deploy_prod",
        on_false="deploy_staging",
        depends_on=["run_tests"],
    ))
    cond_wf.add_step(WorkflowStep(id="deploy_prod", name="Deploy to Prod",
                                   step_type=StepType.ACTION, action="Deploy production",
                                   depends_on=["check_score"]))
    cond_wf.add_step(WorkflowStep(id="deploy_staging", name="Deploy to Staging",
                                   step_type=StepType.ACTION, action="Deploy staging",
                                   depends_on=["check_score"]))

    result = await engine.execute(cond_wf)
    show_workflow(result, "Conditional")
    console.print(f"   test_score=0.95 > 0.8, so 'Deploy to Prod' ran, 'Deploy to Staging' was skipped")

    # -------------------------------------------------------------------
    # 3. Workflow with loops
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Loop workflow:[/bold]")
    loop_wf = Workflow(name="Batch Processing")
    loop_wf.variables = [
        WorkflowVariable(name="items", value=["service-a", "service-b", "service-c"],
                          var_type="list"),
    ]

    loop_wf.add_step(WorkflowStep(id="init", name="Initialize",
                                   step_type=StepType.ACTION, action="Set up batch"))
    loop_wf.add_step(WorkflowStep(id="process_body", name="Process Item",
                                   step_type=StepType.ACTION, action="Process current item"))
    loop_wf.add_step(WorkflowStep(
        id="loop", name="Process Each",
        step_type=StepType.LOOP,
        loop_over="items",
        loop_variable="current_item",
        loop_body=["process_body"],
        depends_on=["init"],
    ))
    loop_wf.add_step(WorkflowStep(id="summary", name="Summary",
                                   step_type=StepType.ACTION, action="Report results",
                                   depends_on=["loop"]))

    result = await engine.execute(loop_wf)
    show_workflow(result, "Loop")

    # -------------------------------------------------------------------
    # 4. Parallel step execution
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Parallel execution:[/bold]")
    par_wf = Workflow(name="Parallel CI")
    par_wf.add_step(WorkflowStep(id="checkout", name="Checkout", action="git checkout"))
    par_wf.add_step(WorkflowStep(id="lint", name="Lint", action="Run linter",
                                  depends_on=["checkout"]))
    par_wf.add_step(WorkflowStep(id="test", name="Unit Tests", action="Run tests",
                                  depends_on=["checkout"]))
    par_wf.add_step(WorkflowStep(id="scan", name="Security Scan", action="Run SAST",
                                  depends_on=["checkout"]))
    par_wf.add_step(WorkflowStep(id="report", name="Report", action="Aggregate results",
                                  depends_on=["lint", "test", "scan"]))

    result = await engine.execute(par_wf)
    show_workflow(result, "Parallel CI")

    # -------------------------------------------------------------------
    # 5. Data transformation
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Data transformation:[/bold]")
    transform_wf = Workflow(name="Data Transform")
    transform_wf.variables = [
        WorkflowVariable(name="greeting", value="hello world"),
        WorkflowVariable(name="numbers", value=[1, 2, 3, 4, 5], var_type="list"),
    ]

    transform_wf.add_step(WorkflowStep(
        id="upper", name="Uppercase",
        step_type=StepType.TRANSFORM,
        transform_expression="upper(greeting)",
    ))
    transform_wf.add_step(WorkflowStep(
        id="total", name="Sum Numbers",
        step_type=StepType.TRANSFORM,
        transform_expression="sum(numbers)",
    ))
    transform_wf.add_step(WorkflowStep(
        id="count", name="Count Items",
        step_type=StepType.TRANSFORM,
        transform_expression="len(numbers)",
    ))

    result = await engine.execute(transform_wf)
    for step in result.steps:
        console.print(f"   {step.name}: {step.output}")

    # -------------------------------------------------------------------
    # 6. Validation
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Workflow validation:[/bold]")
    valid_wf = Workflow(name="Valid Workflow")
    valid_wf.add_step(WorkflowStep(id="a", name="Step A"))
    valid_wf.add_step(WorkflowStep(id="b", name="Step B", depends_on=["a"]))
    errors = valid_wf.validate()
    console.print(f"   Valid workflow errors: {errors if errors else '(none)'}")

    # Invalid: missing dependency
    invalid_wf = Workflow(name="Invalid Workflow")
    invalid_wf.add_step(WorkflowStep(id="x", name="Step X", depends_on=["missing_id"]))
    errors = invalid_wf.validate()
    console.print(f"   Invalid workflow errors: {errors}")

    # Invalid: condition step without condition
    bad_cond = Workflow(name="Bad Condition")
    bad_cond.add_step(WorkflowStep(id="c1", name="Empty Cond", step_type=StepType.CONDITION))
    errors = bad_cond.validate()
    console.print(f"   Missing condition errors: {errors}")

    # -------------------------------------------------------------------
    # 7. Error handling policies
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Error handling policy (skip):[/bold]")
    skip_wf = Workflow(name="Skip on Error", on_error="skip")
    skip_wf.add_step(WorkflowStep(id="ok1", name="OK Step 1"))
    skip_wf.add_step(WorkflowStep(id="ok2", name="OK Step 2", depends_on=["ok1"]))
    result = await engine.execute(skip_wf)
    console.print(f"   Status: {result.status.value}, steps completed: "
                  f"{sum(1 for s in result.steps if s.is_complete)}/{len(result.steps)}")

    # -------------------------------------------------------------------
    # 8. Execution log
    # -------------------------------------------------------------------
    console.print("\n[bold]8. Execution log (last 10):[/bold]")
    log = engine.get_execution_log()
    table = Table(title=f"Execution Log ({len(log)} entries, showing last 10)")
    table.add_column("Event", style="cyan")
    table.add_column("Workflow", style="dim", width=12)
    table.add_column("Step", style="yellow", max_width=20)
    for entry in log[-10:]:
        table.add_row(
            entry.get("event", ""),
            entry.get("workflow_id", "")[:12],
            entry.get("step_name", "-"),
        )
    console.print(table)

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
