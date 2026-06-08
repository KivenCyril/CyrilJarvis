#!/usr/bin/env python3
"""skill_evolution.py -- Skill system demonstration.

Shows JARVIS's procedural memory: skills that are distilled from
completed Streaming Specs, track execution history, trigger automatic
evolution, and persist as YAML files.

Run:
    python examples/skill_evolution.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.skills.base import (
        Skill,
        SkillExecution,
        SkillMetadata,
        SkillStatus,
        SkillStep,
    )
    from jarvis.skills.registry import SkillRegistry
    from jarvis.skills.evolve import SkillEvolver
    from jarvis.models.streaming_spec import StreamingSpec, StepStatus
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Skill Evolution Demo[/bold cyan]",
                        subtitle="Procedural Memory That Improves Over Time"))

    tmpdir = tempfile.mkdtemp(prefix="jarvis_skills_")

    # -------------------------------------------------------------------
    # 1. Create a skill registry and load built-in skills
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Setting up skill registry...[/bold]")
    registry = SkillRegistry(skills_dir=tmpdir)
    # Load from the project's skills directory if it exists
    builtin_count = registry.load_directory(
        Path(__file__).resolve().parent.parent / "skills"
    )
    console.print(f"   Loaded {builtin_count} built-in skill(s)")
    console.print(f"   Registry: {registry}")

    # -------------------------------------------------------------------
    # 2. Create a custom skill
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Creating a custom skill...[/bold]")
    deploy_skill = Skill(
        metadata=SkillMetadata(
            name="deploy-fastapi",
            version="1.0.0",
            description="Deploy a FastAPI service to production",
            author="demo-user",
            tags=["deploy", "fastapi", "devops"],
            domain="devops",
        ),
        status=SkillStatus.ACTIVE,
        system_prompt="You are a deployment specialist for FastAPI applications.",
        steps=[
            SkillStep(order=0, action="Run unit tests", tool="shell_execute",
                      tool_args_template={"command": "pytest tests/"}),
            SkillStep(order=1, action="Build Docker image", tool="shell_execute",
                      tool_args_template={"command": "docker build -t {service} ."}),
            SkillStep(order=2, action="Push to registry", tool="shell_execute",
                      tool_args_template={"command": "docker push {service}"}),
            SkillStep(order=3, action="Deploy to Kubernetes", tool="shell_execute",
                      tool_args_template={"command": "kubectl apply -f k8s/"}),
            SkillStep(order=4, action="Verify deployment", tool="http_request",
                      tool_args_template={"url": "https://{service}.example.com/health"}),
        ],
        constraints=[
            "Zero-downtime deployment required",
            "Must pass all tests before deployment",
            "Rollback on health check failure",
        ],
    )
    registry.register(deploy_skill)
    console.print(f"   Created: {deploy_skill.metadata.name} v{deploy_skill.metadata.version}")
    console.print(f"   Steps: {len(deploy_skill.steps)}")
    console.print(f"   Constraints: {len(deploy_skill.constraints)}")

    # -------------------------------------------------------------------
    # 3. Record execution results
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Recording execution results...[/bold]")
    executions = [
        SkillExecution(input_context="Deploy user-service", output="Deployed successfully",
                       success=True, duration_ms=45000, score=0.9, feedback="Clean deploy"),
        SkillExecution(input_context="Deploy payment-service", output="Deployed with warnings",
                       success=True, duration_ms=62000, score=0.7, feedback="Slow rollout"),
        SkillExecution(input_context="Deploy auth-service", output="Error: tests failed",
                       success=False, duration_ms=12000, score=0.0,
                       feedback="Unit tests had flaky network calls"),
        SkillExecution(input_context="Deploy order-service", output="Deployed OK",
                       success=True, duration_ms=38000, score=0.85, feedback=""),
    ]

    for ex in executions:
        deploy_skill.record_execution(ex)
        status = "[green]OK[/green]" if ex.success else "[red]FAIL[/red]"
        console.print(f"   {status} {ex.input_context}: score={ex.score:.1f}, {ex.duration_ms}ms")

    console.print(f"\n   Skill stats after {deploy_skill.use_count} executions:")
    console.print(f"   - Success rate: {deploy_skill.success_rate:.0%}")
    console.print(f"   - Avg score: {deploy_skill.avg_score:.2f}")

    # -------------------------------------------------------------------
    # 4. Check evolution trigger
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Checking evolution trigger...[/bold]")
    evolver = SkillEvolver(registry)
    should = await evolver.should_evolve(deploy_skill)
    console.print(f"   Should evolve: {should}")
    console.print(f"   (success_rate={deploy_skill.success_rate:.2f}, "
                  f"avg_score={deploy_skill.avg_score:.2f}, "
                  f"use_count={deploy_skill.use_count})")

    # -------------------------------------------------------------------
    # 5. Evolve skill to a new version (heuristic mode)
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Evolving skill...[/bold]")
    improved = await evolver.improve_skill(deploy_skill)
    if improved:
        console.print(f"   Evolved: {improved.metadata.name} v{improved.metadata.version}")
        console.print(f"   New constraints ({len(improved.constraints)}):")
        for c in improved.constraints:
            console.print(f"   - {c[:80]}")
        console.print(f"   Improvement notes:")
        for note in improved.improvement_notes:
            console.print(f"   - {note}")
    else:
        console.print("   No evolution needed at this time")

    # -------------------------------------------------------------------
    # 6. Distill a skill from a completed spec
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Distilling skill from completed Streaming Spec...[/bold]")
    spec = StreamingSpec(
        name="Data Pipeline",
        intent="Build ETL pipeline from Postgres to BigQuery",
    )
    spec.add_step("Analyse source schema")
    spec.add_step("Design transformation")
    spec.add_step("Implement pipeline")
    spec.add_step("Test with sample data")
    spec.add_constraint("Handle schema evolution gracefully")
    spec.add_constraint("Include data validation")
    # Mark all as completed
    for step in spec.steps:
        step.status = StepStatus.COMPLETED
        step.output = f"Completed: {step.name}"

    distilled = await evolver.distill_from_spec(spec)
    console.print(f"   Distilled: {distilled.metadata.name}")
    console.print(f"   Steps: {len(distilled.steps)}")
    console.print(f"   Parent spec: {distilled.parent_spec_id}")
    console.print(f"   Status: {distilled.status.value}")

    # -------------------------------------------------------------------
    # 7. Save and reload skills
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Save/load persistence...[/bold]")
    # Save
    saved_path = deploy_skill.save(tmpdir)
    console.print(f"   Saved to: {saved_path}")

    # Show YAML content
    yaml_content = deploy_skill.to_yaml()
    console.print(Panel(yaml_content[:500], title="Skill YAML (truncated)"))

    # Load back
    loaded = Skill.from_yaml(saved_path)
    console.print(f"   Loaded: {loaded.metadata.name} v{loaded.metadata.version}")
    console.print(f"   Steps: {len(loaded.steps)}")
    console.print(f"   Status: {loaded.status.value}")

    # -------------------------------------------------------------------
    # 8. Registry search and discovery
    # -------------------------------------------------------------------
    console.print("\n[bold]8. Skill search and discovery:[/bold]")
    table = Table(title="All registered skills")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="yellow")
    table.add_column("Status", style="bold")
    table.add_column("Tags")
    table.add_column("Uses", justify="right")

    for skill in registry.list_skills():
        table.add_row(
            skill.metadata.name,
            skill.metadata.version,
            skill.status.value,
            ", ".join(skill.metadata.tags[:3]),
            str(skill.use_count),
        )
    console.print(table)

    # Search
    results = registry.search("deploy")
    console.print(f"   Search 'deploy': {len(results)} result(s)")
    for s in results:
        console.print(f"   - {s.metadata.name}: {s.metadata.description[:60]}")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
