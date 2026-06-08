#!/usr/bin/env python3
"""full_pipeline.py -- End-to-end pipeline demonstration.

This is the capstone example: a complete JARVIS pipeline that
exercises user modeling, spec creation with constraints, DAG
execution with parallel steps, knowledge extraction, memory storage,
skill distillation, curator review, session tracking, notifications,
observability traces, and a final report.

Run:
    python examples/full_pipeline.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.user.profile import UserProfile, UserPreferences
    from jarvis.user.modeler import UserModeler
    from jarvis.models.streaming_spec import (
        ChangeSource,
        SpecStatus,
        StepStatus,
        StreamingSpec,
    )
    from jarvis.engine.spec_engine import SpecEngine
    from jarvis.knowledge.graph import GraphNode, GraphEdge, KnowledgeGraph
    from jarvis.memory.manager import MemoryManager, MemoryType
    from jarvis.skills.base import Skill, SkillMetadata, SkillStatus, SkillStep
    from jarvis.skills.registry import SkillRegistry
    from jarvis.skills.evolve import SkillEvolver
    from jarvis.curator.engine import Curator
    from jarvis.session.manager import SessionManager
    from jarvis.notifications.manager import NotificationManager
    from jarvis.notifications.models import NotificationChannel, NotificationPriority
    from jarvis.observability.tracer import Tracer
    from jarvis.observability.metrics import Metrics
    from jarvis.events.bus import Event, EventBus
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel(
        "[bold cyan]JARVIS -- Full Pipeline Demo[/bold cyan]\n"
        "User -> Spec -> DAG -> Knowledge -> Memory -> Skill -> Review -> Notify",
        subtitle="End-to-End Integration",
    ))

    tmpdir = tempfile.mkdtemp(prefix="jarvis_pipeline_")
    pipeline_start = time.monotonic()

    # Initialize subsystems
    tracer = Tracer()
    metrics_collector = Metrics()
    event_bus = EventBus()
    session_mgr = SessionManager(storage_path=f"{tmpdir}/sessions")
    memory = MemoryManager(storage_path=f"{tmpdir}/memory")
    knowledge = KnowledgeGraph()
    skill_registry = SkillRegistry(skills_dir=f"{tmpdir}/skills")
    evolver = SkillEvolver(skill_registry)
    curator = Curator()
    notifier = NotificationManager()
    spec_engine = SpecEngine()

    # Start a trace for the entire pipeline
    trace_id = tracer.start_trace("full_pipeline")

    # ===================================================================
    # Stage 1: User Modeling
    # ===================================================================
    console.print("\n[bold]Stage 1: User Modeling[/bold]")
    async with tracer.trace_operation(trace_id, "user_modeling") as span:
        profile = UserProfile(
            name="Demo Developer",
            preferences=UserPreferences(
                language="en",
                communication_style="concise",
                code_language="python",
                framework_preferences=["FastAPI", "Pydantic"],
            ),
            goals=["Build production-ready APIs", "Learn AI agent architecture"],
        )
        profile.add_expertise("backend", "advanced")
        profile.add_expertise("devops", "intermediate")

        modeler = UserModeler(profile=profile, storage_path=f"{tmpdir}/user")
        await modeler.on_interaction("code", "Build a REST API for authentication")
        span.set_attribute("user", profile.name)

    console.print(f"   User: {profile.name}")
    console.print(f"   Expertise: {[(e.domain, e.level) for e in profile.expertise]}")
    console.print(f"   Context:\n{profile.to_context_string()}")
    metrics_collector.counter("pipeline_stages", stage="user_modeling").inc()

    # ===================================================================
    # Stage 2: Spec Creation with Constraints
    # ===================================================================
    console.print("\n[bold]Stage 2: Spec Creation[/bold]")
    async with tracer.trace_operation(trace_id, "spec_creation") as span:
        spec = await spec_engine.create(
            intent="Build a REST API for user authentication with JWT tokens and role-based access",
            name="Auth API Pipeline",
        )

        # Add constraints
        await spec_engine.add_constraint(spec.id, "Use bcrypt for password hashing")
        await spec_engine.add_constraint(spec.id, "Implement rate limiting (100 req/min)")
        await spec_engine.add_constraint(spec.id, "Follow OWASP security guidelines")

        # Set up dependencies for DAG
        if len(spec.steps) >= 4:
            spec.add_dependency(spec.steps[1].id, spec.steps[0].id)
            spec.add_dependency(spec.steps[2].id, spec.steps[1].id)
            spec.add_dependency(spec.steps[3].id, spec.steps[2].id)
        spec.update_step_readiness()

        span.set_attribute("spec_id", spec.id)
        span.set_attribute("step_count", len(spec.steps))

    # Track in session
    session = session_mgr.create(user_id=profile.id, channel="cli")
    session.add_message("user", "Build auth API with JWT and RBAC")
    session.add_spec(spec.id)

    console.print(f"   Spec: {spec.name} ({spec.id})")
    console.print(f"   Steps: {len(spec.steps)}")
    console.print(f"   Constraints: {len(spec.constraints)}")
    console.print(f"   DAG valid: {spec.validate_dag()}")

    await event_bus.publish(Event(topic="spec.created", source="pipeline",
                                  data={"spec_id": spec.id}))
    metrics_collector.counter("pipeline_stages", stage="spec_creation").inc()

    # ===================================================================
    # Stage 3: DAG Execution with Progress
    # ===================================================================
    console.print("\n[bold]Stage 3: DAG Execution[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Executing spec...", total=len(spec.steps))

        for step in spec.steps:
            async with tracer.trace_operation(trace_id, f"step.{step.name}") as span:
                progress.update(task, description=f"  {step.name}...")

                await spec_engine.update_step(spec.id, step.id, status=StepStatus.EXECUTING)
                await asyncio.sleep(0.05)  # simulate work
                await spec_engine.update_step(
                    spec.id, step.id,
                    status=StepStatus.COMPLETED,
                    output=f"Completed: {step.name} -- all checks passed",
                )

                span.set_attribute("step_id", step.id)
                metrics_collector.histogram("step_duration_ms").observe(50)

            progress.advance(task)

    console.print(f"   Progress: {spec.progress}")
    console.print(f"   Status: {spec.status.value}")

    await event_bus.publish(Event(topic="spec.completed", source="pipeline",
                                  data={"spec_id": spec.id}))
    metrics_collector.counter("pipeline_stages", stage="execution").inc()

    # ===================================================================
    # Stage 4: Knowledge Extraction
    # ===================================================================
    console.print("\n[bold]Stage 4: Knowledge Extraction[/bold]")
    async with tracer.trace_operation(trace_id, "knowledge_extraction") as span:
        # Extract entities from spec outputs
        combined_output = " ".join(
            step.output or "" for step in spec.steps
        )
        extracted = await knowledge.extract_from_text(
            f"Built Auth API with FastAPI. Used JWT tokens with bcrypt hashing. "
            f"Implemented role-based access control. {combined_output}"
        )

        # Add domain-specific nodes
        knowledge.add_node(GraphNode(id="auth_api", label="Auth API", node_type="project"))
        knowledge.add_node(GraphNode(id="jwt", label="JWT", node_type="technology"))
        knowledge.add_edge(GraphEdge(source="auth_api", target="jwt", relation="uses"))

        span.set_attribute("entities_extracted", len(extracted))

    console.print(f"   Extracted {len(extracted)} entities from results")
    console.print(f"   Graph: {knowledge.stats}")
    metrics_collector.counter("pipeline_stages", stage="knowledge").inc()

    # ===================================================================
    # Stage 5: Memory Storage
    # ===================================================================
    console.print("\n[bold]Stage 5: Memory Storage[/bold]")
    async with tracer.trace_operation(trace_id, "memory_storage") as span:
        await memory.add(
            f"Completed spec '{spec.name}': {spec.intent}",
            MemoryType.SPEC_HISTORY,
            metadata={"spec_id": spec.id},
        )
        await memory.add(
            "Auth API uses bcrypt + JWT. Rate limiting at 100 req/min.",
            MemoryType.FACT,
        )
        await memory.add(
            "User prefers FastAPI with Pydantic for API development.",
            MemoryType.PREFERENCE,
        )

    console.print(f"   Stored {len(memory.list_memories())} memories")
    console.print(f"   Context preview: {memory.get_context(limit=2)[:100]}...")
    metrics_collector.counter("pipeline_stages", stage="memory").inc()

    # ===================================================================
    # Stage 6: Skill Distillation
    # ===================================================================
    console.print("\n[bold]Stage 6: Skill Distillation[/bold]")
    async with tracer.trace_operation(trace_id, "skill_distillation") as span:
        skill = await evolver.distill_from_spec(spec)
        span.set_attribute("skill_name", skill.metadata.name)

    console.print(f"   Distilled: {skill.metadata.name}")
    console.print(f"   Steps: {len(skill.steps)}")
    console.print(f"   Constraints: {len(skill.constraints)}")
    console.print(f"   Status: {skill.status.value}")
    metrics_collector.counter("pipeline_stages", stage="distillation").inc()

    # ===================================================================
    # Stage 7: Curator Review
    # ===================================================================
    console.print("\n[bold]Stage 7: Curator Review[/bold]")
    async with tracer.trace_operation(trace_id, "curator_review") as span:
        # Review the spec output
        review = await curator.review_output(
            request=spec.intent,
            output=" | ".join(step.output or "" for step in spec.steps),
            constraints=[c.content for c in spec.constraints],
        )
        span.set_attribute("verdict", review.verdict.value)
        span.set_attribute("score", review.score)

    console.print(f"   Verdict: {review.verdict.value}")
    console.print(f"   Score: {review.score:.2f}")
    console.print(f"   Issues: {review.issues if review.issues else '(none)'}")
    console.print(f"   Hallucination risk: {review.hallucination_risk:.1f}")

    # Review the skill
    skill_review = await curator.review_skill(skill)
    console.print(f"   Skill review: {skill_review.verdict.value} (score={skill_review.score:.2f})")
    metrics_collector.counter("pipeline_stages", stage="review").inc()

    # ===================================================================
    # Stage 8: Session Tracking
    # ===================================================================
    console.print("\n[bold]Stage 8: Session Tracking[/bold]")
    session.add_message("agent", f"Completed: {spec.name}", agent_name="orchestrator")
    session.add_message("system", f"Curator verdict: {review.verdict.value}")

    console.print(f"   Session: {session.id[:12]}...")
    console.print(f"   Messages: {session.message_count}")
    console.print(f"   Agents used: {session.agents_used}")
    console.print(f"   Duration: {session.duration_seconds:.1f}s")
    metrics_collector.counter("pipeline_stages", stage="session").inc()

    # ===================================================================
    # Stage 9: Notification
    # ===================================================================
    console.print("\n[bold]Stage 9: Notification[/bold]")
    async with tracer.trace_operation(trace_id, "notification") as span:
        notification = await notifier.notify(
            title=f"Pipeline Complete: {spec.name}",
            body=f"Curator score: {review.score:.2f}. "
                 f"Skill distilled: {skill.metadata.name}. "
                 f"Knowledge: {knowledge.stats['nodes']} entities.",
            priority=NotificationPriority.NORMAL,
            channel=NotificationChannel.LOG,
            source="pipeline",
            category="pipeline_complete",
        )
    console.print(f"   Notification: {notification.status.value}")
    metrics_collector.counter("pipeline_stages", stage="notification").inc()

    # ===================================================================
    # Stage 10: Observability Summary
    # ===================================================================
    console.print("\n[bold]Stage 10: Observability Summary[/bold]")

    pipeline_duration = (time.monotonic() - pipeline_start) * 1000
    metrics_collector.histogram("pipeline_duration_ms").observe(pipeline_duration)

    # Show trace
    trace_data = tracer.get_trace(trace_id)
    table = Table(title=f"Pipeline Trace ({len(trace_data)} spans)")
    table.add_column("Operation", style="cyan")
    table.add_column("Duration (ms)", justify="right", style="yellow")
    table.add_column("Status", style="bold")

    for span_dict in trace_data:
        table.add_row(
            span_dict["operation"],
            f"{span_dict['duration_ms']:.1f}",
            span_dict["status"],
        )
    console.print(table)

    # Event bus stats
    bus_stats = event_bus.get_stats()
    console.print(f"\n   Events published: {bus_stats['published']}")

    # Metrics
    snapshot = metrics_collector.snapshot()
    console.print(f"   Metrics: {len(snapshot['counters'])} counters, "
                  f"{len(snapshot['histograms'])} histograms")

    # ===================================================================
    # Final Report
    # ===================================================================
    console.print("\n" + "=" * 60)
    console.print(Panel("[bold cyan]Pipeline Summary[/bold cyan]"))

    report_lines = [
        f"User:           {profile.name}",
        f"Spec:           {spec.name} ({spec.id})",
        f"Intent:         {spec.intent[:60]}...",
        f"Steps:          {len(spec.steps)} (all completed)",
        f"Constraints:    {len(spec.constraints)}",
        f"DAG valid:      {spec.validate_dag()}",
        f"Curator score:  {review.score:.2f} ({review.verdict.value})",
        f"Skill:          {skill.metadata.name} ({skill.status.value})",
        f"Knowledge:      {knowledge.stats['nodes']} nodes, {knowledge.stats['edges']} edges",
        f"Memories:       {len(memory.list_memories())}",
        f"Session:        {session.message_count} messages, {session.duration_seconds:.1f}s",
        f"Trace spans:    {len(trace_data)}",
        f"Pipeline time:  {pipeline_duration:.0f}ms",
    ]

    for line in report_lines:
        console.print(f"   {line}")

    # Mark session complete
    session_mgr.complete(session.id)

    console.print("\n[bold green]Full pipeline demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
