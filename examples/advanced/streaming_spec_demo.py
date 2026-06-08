"""Streaming Spec Advanced Demo.

Demonstrates the full lifecycle of a Streaming Spec with:
- Real-time step creation and execution
- Constraint management (add, remove, human/agent sources)
- Spec redirection and pause/resume
- Changelog tracking
- Multi-agent step assignment
- Progress tracking and completion

This is the core innovation of JARVIS: a real-time editable task
control panel that both humans and agents can modify while execution
is in progress.

Usage:
    python examples/advanced/streaming_spec_demo.py
"""

from __future__ import annotations

import asyncio
import datetime
import json
import uuid
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Streaming Spec Models
# ---------------------------------------------------------------------------

@dataclass
class SpecConstraint:
    """A constraint that guides how agents execute the spec."""
    id: str
    content: str
    active: bool = True
    added_by: str = "human"
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"c-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()


@dataclass
class SpecStep:
    """A step in the spec's execution plan."""
    id: str
    name: str
    description: str = ""
    status: str = "pending"
    agent: str | None = None
    output: str = ""
    started_at: str | None = None
    completed_at: str | None = None

    async def execute(self, delay: float = 0.3) -> str:
        """Simulate executing this step."""
        self.status = "executing"
        self.started_at = datetime.datetime.utcnow().isoformat()
        await asyncio.sleep(delay)
        self.status = "completed"
        self.output = f"Step '{self.name}' completed successfully"
        self.completed_at = datetime.datetime.utcnow().isoformat()
        return self.output


@dataclass
class ChangelogEntry:
    """An entry in the spec's change history."""
    action: str
    details: str
    source: str = "system"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.utcnow().isoformat()


@dataclass
class StreamingSpec:
    """The core Streaming Spec: a real-time editable task control panel."""
    id: str
    name: str
    intent: str
    status: str = "planning"
    steps: list[SpecStep] = field(default_factory=list)
    constraints: list[SpecConstraint] = field(default_factory=list)
    changelog: list[ChangelogEntry] = field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"spec-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()

    @property
    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.status == "completed")
        return f"{done}/{len(self.steps)}"

    @property
    def completion_pct(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status == "completed")
        return round(done / len(self.steps) * 100, 1)

    def add_step(self, name: str, description: str = "",
                 agent: str | None = None) -> SpecStep:
        step = SpecStep(
            id=f"step-{len(self.steps) + 1}",
            name=name,
            description=description,
            agent=agent,
        )
        self.steps.append(step)
        self._log("step_added", f"Added step: {name}")
        return step

    def add_constraint(self, content: str, source: str = "human") -> SpecConstraint:
        constraint = SpecConstraint(
            id=f"c-{len(self.constraints) + 1}",
            content=content,
            added_by=source,
        )
        self.constraints.append(constraint)
        self._log("constraint_added", f"Added constraint: {content}", source)
        return constraint

    def remove_constraint(self, constraint_id: str) -> bool:
        for c in self.constraints:
            if c.id == constraint_id:
                c.active = False
                self._log("constraint_removed", f"Deactivated constraint: {c.content}")
                return True
        return False

    def redirect(self, new_intent: str) -> None:
        old = self.intent
        self.intent = new_intent
        self.status = "redirected"
        self._log("redirected", f"Redirected from '{old}' to '{new_intent}'")

    def pause(self) -> None:
        self.status = "paused"
        self._log("paused", "Spec execution paused")

    def resume(self) -> None:
        self.status = "executing"
        self._log("resumed", "Spec execution resumed")

    def _log(self, action: str, details: str, source: str = "system") -> None:
        self.changelog.append(ChangelogEntry(
            action=action, details=details, source=source,
        ))


# ---------------------------------------------------------------------------
# Spec Engine
# ---------------------------------------------------------------------------

class SpecEngine:
    """Engine that manages Streaming Spec lifecycle."""

    def __init__(self):
        self.specs: dict[str, StreamingSpec] = {}

    async def create(self, intent: str, name: str | None = None) -> StreamingSpec:
        """Create a new Streaming Spec from an intent."""
        spec = StreamingSpec(
            id=f"spec-{len(self.specs) + 1:04d}",
            name=name or f"Spec: {intent[:40]}",
            intent=intent,
        )

        # Auto-decompose intent into steps
        steps = self._decompose_intent(intent)
        for step_name, step_desc, agent in steps:
            spec.add_step(step_name, step_desc, agent)

        spec.status = "planning"
        self.specs[spec.id] = spec
        return spec

    async def execute(self, spec_id: str) -> StreamingSpec | None:
        """Execute a spec through its steps."""
        spec = self.specs.get(spec_id)
        if not spec:
            return None

        spec.status = "executing"
        print(f"\n  Executing spec: {spec.name}")
        print(f"  Intent: {spec.intent}")
        print(f"  Steps: {len(spec.steps)}")
        print(f"  Constraints: {len(spec.constraints)}")

        for i, step in enumerate(spec.steps):
            if spec.status == "paused":
                print(f"  [PAUSED] Waiting to resume...")
                while spec.status == "paused":
                    await asyncio.sleep(0.1)

            print(f"  [{i+1}/{len(spec.steps)}] {step.name}...", end=" ")
            await step.execute(delay=0.2)
            print(f"DONE ({step.status})")

        spec.status = "completed"
        spec._log("completed", f"All {len(spec.steps)} steps completed")
        return spec

    def _decompose_intent(self, intent: str) -> list[tuple[str, str, str | None]]:
        """Decompose an intent into (name, description, agent) tuples."""
        intent_lower = intent.lower()

        if "review" in intent_lower:
            return [
                ("Analyze Code", "Read and understand the code structure", "code-agent"),
                ("Identify Issues", "Find bugs, style issues, and security concerns", "code-agent"),
                ("Check Tests", "Verify test coverage and quality", "qa-agent"),
                ("Write Report", "Summarize findings and recommendations", "writer-agent"),
            ]
        elif "deploy" in intent_lower:
            return [
                ("Pre-check", "Validate deployment prerequisites", "devops-agent"),
                ("Build", "Build the application artifacts", "devops-agent"),
                ("Test", "Run pre-deployment tests", "qa-agent"),
                ("Deploy", "Deploy to target environment", "devops-agent"),
                ("Verify", "Verify deployment health", "devops-agent"),
            ]
        elif "research" in intent_lower or "analyze" in intent_lower:
            return [
                ("Define Scope", "Define research questions and scope", "research-agent"),
                ("Gather Sources", "Find relevant sources and data", "research-agent"),
                ("Analyze", "Analyze findings and draw conclusions", "research-agent"),
                ("Synthesize", "Create a comprehensive report", "writer-agent"),
            ]
        else:
            return [
                ("Plan", "Create an execution plan", None),
                ("Execute", "Carry out the main task", None),
                ("Verify", "Verify the results", None),
            ]


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

async def demo_basic_lifecycle():
    """Demonstrate the basic Streaming Spec lifecycle."""
    print("=" * 60)
    print("DEMO 1: Basic Streaming Spec Lifecycle")
    print("=" * 60)

    engine = SpecEngine()

    # Create a spec
    spec = await engine.create("Review the authentication module for security issues")
    print(f"\nCreated spec: {spec.id}")
    print(f"  Name: {spec.name}")
    print(f"  Status: {spec.status}")
    print(f"  Steps: {len(spec.steps)}")

    # Add human constraints before execution
    spec.add_constraint("Focus on OWASP Top 10 vulnerabilities", source="human")
    spec.add_constraint("Check for SQL injection in all queries", source="human")
    spec.add_constraint("Verify JWT token expiration handling", source="human")
    print(f"\n  Added {len(spec.constraints)} constraints")

    # Agent adds a constraint during planning
    spec.add_constraint(
        "Also check rate limiting on auth endpoints",
        source="agent",
    )
    print("  Agent added 1 additional constraint")

    # Execute the spec
    result = await engine.execute(spec.id)

    print(f"\nSpec completed!")
    print(f"  Progress: {spec.progress}")
    print(f"  Completion: {spec.completion_pct}%")
    print(f"  Changelog entries: {len(spec.changelog)}")


async def demo_spec_editing():
    """Demonstrate editing a spec during execution."""
    print("\n" + "=" * 60)
    print("DEMO 2: Spec Editing (Redirect + Constraint Management)")
    print("=" * 60)

    engine = SpecEngine()

    spec = await engine.create("Deploy version 2.0 to production")
    print(f"\nCreated spec: {spec.name}")

    # Add initial constraint
    c1 = spec.add_constraint("Must pass all CI checks")
    c2 = spec.add_constraint("Deploy during maintenance window only")

    # Execute first step
    spec.status = "executing"
    await spec.steps[0].execute(delay=0.1)
    print(f"  Step 1 completed: {spec.steps[0].name}")

    # User decides to change direction
    spec.redirect("Deploy version 2.1-hotfix to staging first")
    print(f"\n  REDIRECTED: {spec.intent}")

    # Remove an outdated constraint
    spec.remove_constraint(c2.id)
    print(f"  Removed constraint: {c2.content}")

    # Add new constraint for the redirected intent
    spec.add_constraint("Deploy to staging only, not production")
    print(f"  Added new constraint for staging deploy")

    # Show changelog
    print(f"\n  Changelog ({len(spec.changelog)} entries):")
    for entry in spec.changelog:
        print(f"    [{entry.source}] {entry.action}: {entry.details}")


async def demo_multi_agent():
    """Demonstrate multi-agent step assignment."""
    print("\n" + "=" * 60)
    print("DEMO 3: Multi-Agent Collaboration")
    print("=" * 60)

    engine = SpecEngine()

    spec = await engine.create("Research AI trends and write a comprehensive report")
    print(f"\nSpec: {spec.name}")
    print(f"Steps assigned to agents:")
    for step in spec.steps:
        agent = step.agent or "unassigned"
        print(f"  {step.name} -> {agent}")

    # Execute
    result = await engine.execute(spec.id)
    print(f"\nAll steps completed by multiple agents!")

    # Show final state
    print(f"\nFinal spec state:")
    print(json.dumps({
        "id": spec.id,
        "status": spec.status,
        "progress": spec.progress,
        "steps": [{"name": s.name, "agent": s.agent, "status": s.status} for s in spec.steps],
        "constraints": [{"content": c.content, "active": c.active, "by": c.added_by} for c in spec.constraints],
        "changelog_entries": len(spec.changelog),
    }, indent=2))


async def main():
    """Run all demos."""
    await demo_basic_lifecycle()
    await demo_spec_editing()
    await demo_multi_agent()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
