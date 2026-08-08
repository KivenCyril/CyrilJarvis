"""End-to-end integration tests that exercise the full JARVIS stack."""

import pytest

from jarvis.app import JarvisApp


class TestFullStack:
    @pytest.fixture
    async def app(self, tmp_path):
        j = JarvisApp(specs_dir=tmp_path / "specs")
        await j.initialize()
        yield j
        await j.shutdown()

    # ------------------------------------------------------------------ #
    # Spec lifecycle
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_full_spec_lifecycle(self, app):
        """Create spec -> add constraints -> execute -> verify completion."""
        spec = await app.spec_engine.create("Build a REST API")
        assert len(spec.steps) >= 3

        await app.spec_engine.add_constraint(spec.id, "Use Python")
        spec = app.spec_engine.get(spec.id)
        assert len(spec.constraints) == 1

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status.value == "completed"

    # ------------------------------------------------------------------ #
    # Agent routing
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_agent_routing_all_domains(self, app):
        """Verify each agent domain gets routed correctly."""
        routing_tests = [
            ("review this code", "code-agent"),
            ("schedule a meeting", "calendar-agent"),
            ("search for information about Python", "knowledge-agent"),
            ("reply to this email", "comms-agent"),
            ("check server health", "ops-agent"),
            ("analyze this CSV data", "data-agent"),
            ("deploy with Docker", "devops-agent"),
            ("write documentation", "writing-agent"),
            ("research market trends", "research-agent"),
        ]
        for message, expected_agent in routing_tests:
            result = await app.orchestrator.handle(message)
            assert result.agent_name == expected_agent, (
                f"'{message}' routed to {result.agent_name}, "
                f"expected {expected_agent}"
            )

    # ------------------------------------------------------------------ #
    # DAG dependencies
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_spec_with_dag_dependencies(self, app):
        """Create a spec, add dependencies, execute with DAG ordering."""
        spec = await app.spec_engine.create("Deploy microservice")
        if len(spec.steps) >= 2:
            await app.spec_engine.add_dependency(
                spec.id, spec.steps[1].id, spec.steps[0].id
            )
            spec = app.spec_engine.get(spec.id)
            assert spec.validate_dag()

        result = await app.executor.execute_spec(spec.id)
        assert result is not None
        assert result.status.value == "completed"

    # ------------------------------------------------------------------ #
    # Knowledge graph
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_knowledge_graph_roundtrip(self, app):
        """Add nodes and edges, query, verify results."""
        from jarvis.knowledge.graph import GraphEdge, GraphNode

        app.knowledge_graph.add_node(
            GraphNode(id="py", label="Python", node_type="lang")
        )
        app.knowledge_graph.add_node(
            GraphNode(id="js", label="JavaScript", node_type="lang")
        )
        app.knowledge_graph.add_edge(
            GraphEdge(source="py", target="js", relation="compared_with")
        )

        results = await app.knowledge_graph.query("Python")
        assert len(results) >= 1

        viz = app.knowledge_graph.to_visualization()
        assert len(viz["nodes"]) >= 2
        assert len(viz["edges"]) >= 1

    # ------------------------------------------------------------------ #
    # Memory
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_memory_roundtrip(self, app, tmp_path):
        from jarvis.memory import MemoryManager, MemoryType

        mm = MemoryManager(str(tmp_path / "memory"))

        await mm.add("User likes Python", MemoryType.PREFERENCE)
        await mm.add("Project deadline is Friday", MemoryType.FACT)

        results = await mm.search("Python")
        assert len(results) >= 1
        assert any("Python" in r.content for r in results)

    # ------------------------------------------------------------------ #
    # Skill distillation
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_skill_distillation(self, app, tmp_path):
        from jarvis.skills import SkillEvolver, SkillRegistry

        spec = await app.spec_engine.create("Write unit tests")
        result = await app.executor.execute_spec(spec.id)
        assert result is not None

        registry = SkillRegistry(str(tmp_path / "skills"))
        evolver = SkillEvolver(registry)
        skill = await evolver.distill_from_spec(result)

        assert skill.metadata.name
        assert len(skill.steps) > 0
        assert skill.parent_spec_id == result.id

    # ------------------------------------------------------------------ #
    # Curator review
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_curator_review(self, app):
        from jarvis.curator import Curator, ReviewVerdict

        curator = Curator()

        review = await curator.review_output(
            request="Write a hello world program",
            output="print('Hello, World!')",
            constraints=["Use Python"],
        )
        assert review.verdict in [
            ReviewVerdict.APPROVED,
            ReviewVerdict.NEEDS_REVISION,
        ]
        assert 0.0 <= review.score <= 1.0

    # ------------------------------------------------------------------ #
    # Session tracking
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_session_tracking(self, app, tmp_path):
        from jarvis.session import SessionManager

        sm = SessionManager(str(tmp_path / "sessions"))

        session = sm.create(user_id="test", channel="test")
        session.add_message("user", "Hello")

        chat_output = await app.chat("review this code")
        session.add_message("agent", chat_output, agent_name="code-agent")

        assert session.message_count == 2
        assert "code-agent" in session.agents_used

    # ------------------------------------------------------------------ #
    # Observability
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_observability_tracing(self, app):
        from jarvis.observability.tracer import Tracer

        t = Tracer()

        trace_id = t.start_trace("test")
        async with t.trace_operation(trace_id, "test_op"):
            pass

        trace = t.get_trace(trace_id)
        assert len(trace) == 1
        assert trace[0]["status"] == "ok"

    # ------------------------------------------------------------------ #
    # Tool execution
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_tool_execution(self, app):
        if app._tool_registry:
            result = await app._tool_registry.execute(
                "shell_execute", {"command": "echo hello"}
            )
            assert result.success
            assert "hello" in result.output

    # ------------------------------------------------------------------ #
    # Module counts
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_system_modules_count(self, app):
        """Verify minimum module availability."""
        assert len(app.registry) >= 10  # 10 agents
        if app._tool_registry:
            assert len(app._tool_registry.list_tools()) >= 20  # 20+ tools

    # ------------------------------------------------------------------ #
    # Constraint editing mid-execution
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_constraint_add_and_remove(self, app):
        """Add and remove constraints, verify changelog tracks edits."""
        spec = await app.spec_engine.create("Refactor module")
        initial_version = spec.version

        await app.spec_engine.add_constraint(spec.id, "Keep backward compat")
        spec = app.spec_engine.get(spec.id)
        assert len(spec.constraints) == 1
        assert spec.version > initial_version

        cid = spec.constraints[0].id
        await app.spec_engine.remove_constraint(spec.id, cid)
        spec = app.spec_engine.get(spec.id)
        assert len(spec.constraints) == 0

    # ------------------------------------------------------------------ #
    # Spec redirect
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_spec_redirect(self, app):
        """Change spec intent mid-flight and verify new intent is applied."""
        spec = await app.spec_engine.create("Build CLI tool")
        await app.spec_engine.redirect(spec.id, "Build web dashboard instead")

        spec = app.spec_engine.get(spec.id)
        # After redirect, the spec is replanned with the new intent and
        # set back to executing (ready for the next execution wave).
        assert spec.intent == "Build web dashboard instead"
        assert len(spec.steps) >= 2

    # ------------------------------------------------------------------ #
    # Chat round-trip
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_chat_returns_output(self, app):
        """Simple chat interface returns a non-empty string."""
        output = await app.chat("review this code")
        assert isinstance(output, str)
        assert len(output) > 0
