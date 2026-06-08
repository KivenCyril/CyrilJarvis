"""JARVIS SDK Usage Examples.

These examples demonstrate how to use the JARVIS Python SDK
for common tasks.  Each function is self-contained and can be
executed independently.
"""

from __future__ import annotations

from jarvis.sdk.client import AsyncJarvisClient


# ---------------------------------------------------------------------------
# 1. Basic chat
# ---------------------------------------------------------------------------

async def example_basic_chat() -> None:
    """Basic chat with JARVIS agents."""
    async with AsyncJarvisClient() as client:
        # Check system health
        health = await client.health()
        print(f"System: {health['status']}, Agents: {health['agents']}")

        # Chat with agents
        response = await client.chat("What is the OWASP Top 10?")
        print(f"Agent: {response.agent}")
        print(f"Response: {response.output}")


# ---------------------------------------------------------------------------
# 2. Streaming Spec lifecycle
# ---------------------------------------------------------------------------

async def example_streaming_spec() -> None:
    """Create and execute a Streaming Spec."""
    async with AsyncJarvisClient() as client:
        # Create spec
        spec = await client.create_spec(
            "Set up CI/CD pipeline for Python project",
        )
        print(f"Created spec: {spec.id} with {len(spec.steps)} steps")

        # Add constraints
        spec = await client.add_constraint(spec.id, "Use GitHub Actions")
        spec = await client.add_constraint(
            spec.id,
            "Include Python 3.11 and 3.12 in matrix",
        )

        # Execute
        result = await client.execute_spec(spec.id)
        print(f"Status: {result.status}, Progress: {result.progress}")
        for step in result.steps:
            print(f"  - {step['name']}: {step['status']}")


# ---------------------------------------------------------------------------
# 3. Knowledge graph
# ---------------------------------------------------------------------------

async def example_knowledge_graph() -> None:
    """Work with the knowledge graph."""
    async with AsyncJarvisClient() as client:
        # Extract knowledge
        result = await client.extract_knowledge(
            "Python is a programming language created by Guido van Rossum. "
            "FastAPI is a web framework built with Python."
        )
        print(f"Extracted {result['extracted_nodes']} nodes")

        # View graph
        graph = await client.knowledge_graph()
        print(
            f"Graph: {len(graph['nodes'])} nodes, "
            f"{len(graph['edges'])} edges"
        )


# ---------------------------------------------------------------------------
# 4. Memory
# ---------------------------------------------------------------------------

async def example_memory() -> None:
    """Store and retrieve memories."""
    async with AsyncJarvisClient() as client:
        # Add memories
        await client.add_memory("User prefers Python", "preference")
        await client.add_memory("Project uses PostgreSQL", "fact")

        # Search
        results = await client.search_memory("Python")
        for r in results:
            print(f"  [{r.get('memory_type')}] {r.get('content')}")


# ---------------------------------------------------------------------------
# 5. Tools
# ---------------------------------------------------------------------------

async def example_tools() -> None:
    """List available tools."""
    async with AsyncJarvisClient() as client:
        tools = await client.list_tools()
        for tool in tools:
            print(f"  {tool.name}: {tool.description[:50]}")


# ---------------------------------------------------------------------------
# 6. Curator review
# ---------------------------------------------------------------------------

async def example_curator_review() -> None:
    """Use the curator for quality review."""
    async with AsyncJarvisClient() as client:
        review_result = await client.review(
            request="Write a secure login function",
            output=(
                "def login(user, pwd): "
                "return user == 'admin' and pwd == 'password'"
            ),
            constraints=["Follow OWASP guidelines"],
        )
        print(
            f"Verdict: {review_result['verdict']}, "
            f"Score: {review_result['score']}"
        )


# ---------------------------------------------------------------------------
# 7. Full workflow
# ---------------------------------------------------------------------------

async def example_full_workflow() -> None:
    """Complete workflow: chat -> spec -> execute -> review -> memorize."""
    async with AsyncJarvisClient() as client:
        # 1. Chat to understand the task
        response = await client.chat("How should I structure a REST API?")
        print(f"Advice from {response.agent}: {response.output[:100]}...")

        # 2. Create a spec based on the advice
        spec = await client.create_spec(
            "Build REST API for user management",
        )

        # 3. Add constraints
        await client.add_constraint(spec.id, "Use FastAPI")
        await client.add_constraint(spec.id, "Include authentication")

        # 4. Execute
        result = await client.execute_spec(spec.id)

        # 5. Review the output
        for step in result.steps:
            if step.get("output"):
                review_result = await client.review(
                    request=step["name"],
                    output=step["output"],
                )
                print(
                    f"  {step['name']}: "
                    f"{review_result['verdict']} ({review_result['score']})"
                )

        # 6. Save to memory
        await client.add_memory(
            f"Completed REST API spec: {result.progress}",
            "spec_history",
        )


# ---------------------------------------------------------------------------
# 8. WebSocket streaming
# ---------------------------------------------------------------------------

async def example_stream_spec() -> None:
    """Stream real-time spec updates over WebSocket."""
    async with AsyncJarvisClient() as client:
        spec = await client.create_spec("Analyze codebase security")

        # Stream events
        async for event in client.stream_spec(spec.id):
            event_type = event.get("type", "unknown")
            print(f"[{event_type}] {event}")
            if event.get("status") in ("completed", "failed"):
                break


# ---------------------------------------------------------------------------
# 9. Observability
# ---------------------------------------------------------------------------

async def example_observability() -> None:
    """Inspect metrics and traces."""
    async with AsyncJarvisClient() as client:
        metrics = await client.get_metrics()
        print(f"Metrics: {metrics}")

        traces = await client.list_traces()
        print(f"Traces: {len(traces)}")


# ---------------------------------------------------------------------------
# 10. Skills
# ---------------------------------------------------------------------------

async def example_skills() -> None:
    """Browse the skill registry."""
    async with AsyncJarvisClient() as client:
        skills = await client.list_skills()
        for skill in skills:
            print(
                f"  {skill.name} v{skill.version} "
                f"({skill.domain}) -- {skill.success_rate:.0%} success"
            )
