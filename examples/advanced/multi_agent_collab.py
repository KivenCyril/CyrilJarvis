"""Multi-Agent Collaboration Demo.

Demonstrates how multiple JARVIS agents can collaborate on a complex
task using the Streaming Spec pattern. The orchestrator routes subtasks
to specialist agents, each contributing to the overall result.

Usage:
    python examples/advanced/multi_agent_collab.py
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data models for the collaboration
# ---------------------------------------------------------------------------

@dataclass
class SubTask:
    """A subtask assigned to a specific agent."""
    id: str
    description: str
    assigned_agent: str
    status: str = "pending"  # pending, in_progress, completed, failed
    output: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        """A subtask is ready if all its dependencies are completed."""
        return len(self.dependencies) == 0

    def complete(self, output: str) -> None:
        self.status = "completed"
        self.output = output


@dataclass
class CollaborationPlan:
    """A plan for multi-agent collaboration."""
    goal: str
    subtasks: list[SubTask] = field(default_factory=list)
    results: dict[str, str] = field(default_factory=dict)

    def add_subtask(self, task_id: str, description: str, agent: str,
                    dependencies: list[str] | None = None) -> SubTask:
        task = SubTask(
            id=task_id,
            description=description,
            assigned_agent=agent,
            dependencies=dependencies or [],
        )
        self.subtasks.append(task)
        return task

    def get_ready_tasks(self) -> list[SubTask]:
        """Get tasks whose dependencies are all completed."""
        completed_ids = {t.id for t in self.subtasks if t.status == "completed"}
        return [
            t for t in self.subtasks
            if t.status == "pending"
            and all(dep in completed_ids for dep in t.dependencies)
        ]

    def is_complete(self) -> bool:
        return all(t.status == "completed" for t in self.subtasks)

    @property
    def progress(self) -> str:
        done = sum(1 for t in self.subtasks if t.status == "completed")
        return f"{done}/{len(self.subtasks)}"


# ---------------------------------------------------------------------------
# Simulated agent behaviour
# ---------------------------------------------------------------------------

async def simulate_agent_work(agent_name: str, task: SubTask) -> str:
    """Simulate an agent processing a subtask."""
    print(f"  [{agent_name}] Starting: {task.description}")
    task.status = "in_progress"

    # Simulate work with varying duration
    work_time = 0.5 + (hash(task.id) % 10) / 10.0
    await asyncio.sleep(work_time)

    # Generate output based on agent type
    outputs = {
        "research-agent": f"Research complete: Found 5 relevant sources about '{task.description}'",
        "code-agent": f"Implementation complete: Generated 150 lines of code for '{task.description}'",
        "writer-agent": f"Documentation complete: Wrote 500 words covering '{task.description}'",
        "qa-agent": f"Testing complete: 12 test cases passed for '{task.description}'",
        "devops-agent": f"Deployment plan ready: 3 stages for '{task.description}'",
        "reviewer-agent": f"Review complete: 2 suggestions for '{task.description}'",
    }

    result = outputs.get(agent_name, f"Completed: {task.description}")
    task.complete(result)
    print(f"  [{agent_name}] Done: {task.description}")
    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class CollaborationOrchestrator:
    """Orchestrate multi-agent collaboration on a plan."""

    def __init__(self):
        self.execution_log: list[dict] = []

    async def execute_plan(self, plan: CollaborationPlan) -> dict[str, Any]:
        """Execute a collaboration plan, respecting dependencies."""
        print(f"\n{'='*60}")
        print(f"Starting collaboration: {plan.goal}")
        print(f"Subtasks: {len(plan.subtasks)}")
        print(f"{'='*60}\n")

        iteration = 0
        while not plan.is_complete():
            iteration += 1
            ready = plan.get_ready_tasks()

            if not ready:
                print("DEADLOCK: No tasks are ready but plan is incomplete!")
                break

            print(f"\n--- Iteration {iteration} ({plan.progress}) ---")
            print(f"Ready tasks: {[t.id for t in ready]}")

            # Execute ready tasks concurrently
            tasks = [
                simulate_agent_work(task.assigned_agent, task)
                for task in ready
            ]
            results = await asyncio.gather(*tasks)

            for task, result in zip(ready, results):
                plan.results[task.id] = result
                self.execution_log.append({
                    "iteration": iteration,
                    "task_id": task.id,
                    "agent": task.assigned_agent,
                    "output": result,
                })

        print(f"\n{'='*60}")
        print(f"Collaboration complete! ({plan.progress})")
        print(f"{'='*60}\n")

        return {
            "goal": plan.goal,
            "total_tasks": len(plan.subtasks),
            "completed": sum(1 for t in plan.subtasks if t.status == "completed"),
            "results": plan.results,
            "execution_log": self.execution_log,
        }


# ---------------------------------------------------------------------------
# Example: Build a full-stack feature
# ---------------------------------------------------------------------------

def build_feature_plan() -> CollaborationPlan:
    """Create a plan for building a user authentication feature."""
    plan = CollaborationPlan(goal="Build user authentication feature")

    # Phase 1: Research (no dependencies)
    plan.add_subtask("research-auth", "Research authentication best practices", "research-agent")
    plan.add_subtask("research-libs", "Evaluate authentication libraries", "research-agent")

    # Phase 2: Design (depends on research)
    plan.add_subtask(
        "design-api", "Design authentication API endpoints",
        "code-agent", dependencies=["research-auth", "research-libs"],
    )
    plan.add_subtask(
        "design-schema", "Design database schema for users/sessions",
        "code-agent", dependencies=["research-auth"],
    )

    # Phase 3: Implementation (depends on design)
    plan.add_subtask(
        "impl-backend", "Implement authentication backend",
        "code-agent", dependencies=["design-api", "design-schema"],
    )
    plan.add_subtask(
        "impl-frontend", "Implement login/signup UI components",
        "code-agent", dependencies=["design-api"],
    )

    # Phase 4: Testing (depends on implementation)
    plan.add_subtask(
        "test-unit", "Write unit tests for auth module",
        "qa-agent", dependencies=["impl-backend"],
    )
    plan.add_subtask(
        "test-integration", "Write integration tests for auth flow",
        "qa-agent", dependencies=["impl-backend", "impl-frontend"],
    )

    # Phase 5: Documentation & Review (depends on testing)
    plan.add_subtask(
        "docs-api", "Write API documentation for auth endpoints",
        "writer-agent", dependencies=["impl-backend", "test-unit"],
    )
    plan.add_subtask(
        "review-security", "Security review of authentication implementation",
        "reviewer-agent", dependencies=["impl-backend", "test-integration"],
    )

    # Phase 6: Deployment (depends on everything)
    plan.add_subtask(
        "deploy-plan", "Create deployment plan for auth feature",
        "devops-agent", dependencies=["test-integration", "review-security", "docs-api"],
    )

    return plan


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    """Run the multi-agent collaboration demo."""
    plan = build_feature_plan()
    orchestrator = CollaborationOrchestrator()

    result = await orchestrator.execute_plan(plan)

    print("\n--- Final Results ---")
    print(json.dumps(result, indent=2))

    print(f"\nTotal tasks: {result['total_tasks']}")
    print(f"Completed: {result['completed']}")
    print(f"Execution log entries: {len(result['execution_log'])}")


if __name__ == "__main__":
    asyncio.run(main())
