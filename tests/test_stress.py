"""Stress and performance tests for JARVIS modules.

These tests exercise modules under load to verify they handle high
volumes, large data structures, and concurrent operations correctly.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from jarvis.models.streaming_spec import (
    ChangeSource,
    SpecStatus,
    StepStatus,
    StreamingSpec,
)
from jarvis.engine.spec_engine import SpecEngine
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult
from jarvis.agents.registry import AgentRegistry
from jarvis.tools.builtin.shell import ShellTool
from jarvis.memory.manager import MemoryManager, MemoryType
from jarvis.knowledge.graph import KnowledgeGraph, GraphNode, GraphEdge
from jarvis.storage.json_store import JSONStore
from jarvis.storage.memory_store import MemoryStore
from jarvis.events.bus import EventBus, Event
from jarvis.skills.base import Skill, SkillMetadata, SkillStep, SkillExecution, SkillStatus
from jarvis.skills.registry import SkillRegistry
from jarvis.security.manager import SecurityManager
from jarvis.security.permissions import AuthContext, Permission, PermissionLevel


# =====================================================================
# Helper
# =====================================================================


class EchoAgent(BaseAgent):
    """Fast agent for stress testing."""

    def __init__(self, name: str = "echo", skills: list[str] | None = None):
        super().__init__(AgentCard(
            name=name,
            description="Echo agent",
            skills=skills or ["echo"],
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"Echo: {message}",
        )


# =====================================================================
# Spec stress tests
# =====================================================================


class TestSpecStress:
    """Stress tests for the StreamingSpec model and SpecEngine."""

    @pytest.mark.asyncio
    async def test_create_100_specs(self):
        """Creating 100 specs and listing them all."""
        engine = SpecEngine()
        specs = []
        for i in range(100):
            spec = await engine.create(f"Task {i}")
            specs.append(spec)
        listed = engine.list_specs()
        assert len(listed) == 100

    def test_spec_with_50_steps(self):
        """A spec with 50 steps validates and sorts correctly."""
        spec = StreamingSpec(name="big", intent="big task")
        for i in range(50):
            spec.add_step(f"Step {i}", source=ChangeSource.AGENT)
        assert len(spec.steps) == 50
        assert spec.validate_dag() is True
        assert len(spec.topological_sort()) == 50

    def test_long_chain_dag(self):
        """Chain of 50 steps: each depends on the previous."""
        spec = StreamingSpec(name="chain", intent="chain task")
        steps = []
        for i in range(50):
            step = spec.add_step(f"Step {i}")
            if steps:
                step.depends_on = [steps[-1].id]
            steps.append(step)
        assert spec.validate_dag() is True
        sorted_steps = spec.topological_sort()
        assert len(sorted_steps) == 50
        # Verify order
        for idx in range(len(sorted_steps) - 1):
            assert sorted_steps[idx].id == steps[idx].id

    def test_wide_dag(self):
        """50 parallel steps all depending on one root step."""
        spec = StreamingSpec(name="wide", intent="wide task")
        root = spec.add_step("Root")
        for i in range(50):
            step = spec.add_step(f"Parallel {i}")
            step.depends_on = [root.id]
        assert spec.validate_dag() is True
        sorted_steps = spec.topological_sort()
        assert len(sorted_steps) == 51
        # Root should come first
        assert sorted_steps[0].name == "Root"

    def test_critical_path_deep_chain(self):
        """Critical path of a long linear chain matches the full chain."""
        spec = StreamingSpec(name="deep", intent="deep chain")
        steps = []
        for i in range(30):
            step = spec.add_step(f"Step {i}")
            if steps:
                step.depends_on = [steps[-1].id]
            steps.append(step)
        cp = spec.critical_path()
        assert len(cp) == 30

    def test_readiness_cascade(self):
        """Completing steps in a chain cascades readiness updates."""
        spec = StreamingSpec(name="cascade", intent="cascade")
        steps = []
        for i in range(10):
            step = spec.add_step(f"Step {i}")
            if steps:
                step.depends_on = [steps[-1].id]
            steps.append(step)

        spec.update_step_readiness()
        ready = spec.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == steps[0].id

        # Complete steps one by one and check readiness propagation
        for i in range(10):
            spec.update_step_status(steps[i].id, StepStatus.COMPLETED)
            spec.update_step_readiness()
            if i < 9:
                ready = spec.get_ready_steps()
                assert len(ready) == 1
                assert ready[0].id == steps[i + 1].id

    def test_many_constraints(self):
        """Adding and querying 100 constraints."""
        spec = StreamingSpec(name="constraints", intent="many constraints")
        for i in range(100):
            spec.add_constraint(f"Constraint #{i}: do not use pattern {i}")
        assert len(spec.constraints) == 100
        # Remove half
        ids_to_remove = [c.id for c in spec.constraints[:50]]
        for cid in ids_to_remove:
            spec.remove_constraint(cid)
        assert len(spec.constraints) == 50


# =====================================================================
# Agent stress tests
# =====================================================================


class TestAgentStress:
    """Stress tests for agent routing and execution."""

    @pytest.mark.asyncio
    async def test_route_1000_messages(self):
        """Route 1000 messages through the registry."""
        registry = AgentRegistry()
        await registry.register(EchoAgent("coder", skills=["code", "review"]))
        await registry.register(EchoAgent("researcher", skills=["search", "knowledge"]))
        await registry.register(EchoAgent("ops", skills=["deploy", "monitor"]))

        start = time.monotonic()
        for i in range(1000):
            msg = f"please review this code change #{i}"
            result = registry.route(msg)
            assert len(result) > 0
        elapsed = time.monotonic() - start
        assert elapsed < 5.0  # 1000 routes should be fast

    @pytest.mark.asyncio
    async def test_register_50_agents(self):
        """Registering 50 agents works and all are findable."""
        registry = AgentRegistry()
        for i in range(50):
            await registry.register(EchoAgent(f"agent-{i}", skills=[f"skill-{i}"]))
        assert len(registry) == 50
        for i in range(50):
            assert registry.get(f"agent-{i}") is not None

    @pytest.mark.asyncio
    async def test_parallel_agent_execution(self):
        """Execute 20 agents in parallel."""
        agents = [EchoAgent(f"a{i}") for i in range(20)]
        tasks = [agent.run(f"Task {i}") for i, agent in enumerate(agents)]
        results = await asyncio.gather(*tasks)
        assert all(r.success for r in results)
        assert len(results) == 20


# =====================================================================
# Tool stress tests
# =====================================================================


class TestToolStress:
    """Stress tests for tool execution."""

    @pytest.mark.asyncio
    async def test_parallel_shell_execution(self):
        """Execute 20 shell commands in parallel."""
        tool = ShellTool()
        tasks = [tool.execute({"command": f"echo test_{i}"}) for i in range(20)]
        results = await asyncio.gather(*tasks)
        assert all(r.success for r in results)
        for i, r in enumerate(results):
            assert f"test_{i}" in r.output

    @pytest.mark.asyncio
    async def test_sequential_tool_calls(self):
        """Execute 100 tool calls sequentially."""
        tool = ShellTool()
        for i in range(100):
            result = await tool.execute({"command": f"echo iter_{i}"})
            assert result.success


# =====================================================================
# Memory stress tests
# =====================================================================


class TestMemoryStress:
    """Stress tests for MemoryManager."""

    @pytest.mark.asyncio
    async def test_add_500_memories(self, tmp_path):
        """Adding 500 memories and listing them all."""
        mm = MemoryManager(str(tmp_path / "mem"))
        for i in range(500):
            await mm.add(
                f"Memory about topic {i} with Python and data analysis",
                MemoryType.FACT,
            )
        all_memories = mm.list_memories()
        assert len(all_memories) == 500

    @pytest.mark.asyncio
    async def test_search_performance(self, tmp_path):
        """Search across 500 memories completes quickly."""
        mm = MemoryManager(str(tmp_path / "mem"))
        for i in range(500):
            await mm.add(
                f"Memory about topic {i} with Python analysis and {i * 7} data points",
                MemoryType.FACT,
            )

        start = time.monotonic()
        results = await mm.search("Python analysis")
        elapsed = time.monotonic() - start
        assert elapsed < 2.0  # should be well under 2 seconds
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_context_generation_large(self, tmp_path):
        """get_context() handles hundreds of memories."""
        mm = MemoryManager(str(tmp_path / "mem"))
        for i in range(200):
            await mm.add(f"Fact {i}: Python is great for data science", MemoryType.FACT)
        context = mm.get_context(limit=20)
        assert "Relevant Memories" in context
        # Should contain at most 20 entries
        assert context.count("- [") <= 20


# =====================================================================
# KnowledgeGraph stress tests
# =====================================================================


class TestKnowledgeGraphStress:
    """Stress tests for the KnowledgeGraph."""

    def test_large_graph_500_nodes(self):
        """Build a graph with 500 nodes and 400 edges."""
        kg = KnowledgeGraph()
        for i in range(500):
            kg.add_node(GraphNode(id=f"n{i}", label=f"Entity {i}", node_type="concept"))
        for i in range(400):
            kg.add_edge(GraphEdge(source=f"n{i}", target=f"n{i + 1}", relation="related"))

        stats = kg.stats
        assert stats["nodes"] == 500
        assert stats["edges"] == 400

        # Query should still work
        results = kg._keyword_query("Entity 250")
        assert len(results) > 0

    def test_visualization_export_large(self):
        """to_visualization() handles a large graph."""
        kg = KnowledgeGraph()
        for i in range(200):
            kg.add_node(GraphNode(id=f"n{i}", label=f"Node {i}", node_type="concept"))
        for i in range(150):
            kg.add_edge(GraphEdge(source=f"n{i}", target=f"n{i + 1}", relation="links"))
        viz = kg.to_visualization()
        assert len(viz["nodes"]) == 200
        assert len(viz["edges"]) == 150

    def test_neighbors_performance(self):
        """neighbors() on a densely connected node."""
        kg = KnowledgeGraph()
        hub = GraphNode(id="hub", label="Hub", node_type="concept")
        kg.add_node(hub)
        for i in range(200):
            node = GraphNode(id=f"spoke{i}", label=f"Spoke {i}", node_type="concept")
            kg.add_node(node)
            kg.add_edge(GraphEdge(source="hub", target=f"spoke{i}", relation="connects"))

        start = time.monotonic()
        neighbors = kg.neighbors("hub")
        elapsed = time.monotonic() - start
        assert len(neighbors) == 200
        assert elapsed < 1.0


# =====================================================================
# Storage stress tests
# =====================================================================


class TestStorageStress:
    """Stress tests for storage backends."""

    @pytest.mark.asyncio
    async def test_json_store_1000_items(self, tmp_path):
        """Write and read back 1000 items from JSONStore."""
        store = JSONStore(str(tmp_path / "bench"))

        for i in range(1000):
            await store.put(f"key_{i}", {"value": i, "data": f"item_{i}" * 10})

        count = await store.count()
        assert count == 1000

        # Read back a specific item
        item = await store.get("key_500")
        assert item is not None
        assert item["value"] == 500

    @pytest.mark.asyncio
    async def test_memory_store_performance(self):
        """MemoryStore handles thousands of items."""
        store = MemoryStore()

        start = time.monotonic()
        for i in range(5000):
            await store.put(f"k{i}", {"v": i})
        elapsed = time.monotonic() - start
        assert elapsed < 2.0

        assert await store.count() == 5000
        assert await store.get("k2500") == {"v": 2500}

    @pytest.mark.asyncio
    async def test_json_store_search(self, tmp_path):
        """Field-level search across many items."""
        store = JSONStore(str(tmp_path / "search"))
        for i in range(100):
            await store.put(f"item_{i}", {"category": "A" if i % 2 == 0 else "B", "idx": i})

        results = await store.search({"category": "A"})
        assert len(results) == 50

    @pytest.mark.asyncio
    async def test_json_store_delete_and_list(self, tmp_path):
        """Delete items and verify listing is consistent."""
        store = JSONStore(str(tmp_path / "del"))
        for i in range(50):
            await store.put(f"key_{i}", {"i": i})

        # Delete every other key
        for i in range(0, 50, 2):
            await store.delete(f"key_{i}")

        keys = await store.list_keys()
        assert len(keys) == 25
        # All remaining keys should be odd indices
        for k in keys:
            idx = int(k.split("_")[1])
            assert idx % 2 == 1


# =====================================================================
# EventBus stress tests
# =====================================================================


class TestEventBusStress:
    """Stress tests for the EventBus."""

    @pytest.mark.asyncio
    async def test_publish_1000_events(self):
        """Publish 1000 events and verify all delivered."""
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(handler, topics=["stress.*"])

        for i in range(1000):
            await bus.publish_simple("stress.test", data={"i": i})

        assert len(received) == 1000

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """500 events delivered to 10 subscribers."""
        bus = EventBus()
        counters = [[] for _ in range(10)]

        for idx in range(10):
            async def make_handler(target):
                async def handler(event: Event):
                    target.append(event)
                return handler
            h = await make_handler(counters[idx])
            bus.subscribe(h, topics=["multi.*"])

        for i in range(500):
            await bus.publish_simple("multi.event", data={"i": i})

        for counter in counters:
            assert len(counter) == 500

    @pytest.mark.asyncio
    async def test_event_history_cap(self):
        """Event bus caps history at max_history."""
        bus = EventBus(max_history=100)

        for i in range(200):
            await bus.publish_simple("cap.test", data={"i": i})

        history = bus.get_history()
        assert len(history) <= 100

    @pytest.mark.asyncio
    async def test_dead_letter_tracking(self):
        """Failed handlers go to the dead letter queue."""
        bus = EventBus()

        async def failing_handler(event: Event):
            raise ValueError("intentional failure")

        bus.subscribe(failing_handler, topics=["fail.*"])

        for i in range(10):
            await bus.publish_simple("fail.test", data={"i": i})

        dead = bus.get_dead_letters()
        assert len(dead) == 10

    @pytest.mark.asyncio
    async def test_stats_accuracy(self):
        """Bus statistics correctly track published/delivered/failed."""
        bus = EventBus()
        received = []

        async def good_handler(event: Event):
            received.append(event)

        async def bad_handler(event: Event):
            raise RuntimeError("oops")

        bus.subscribe(good_handler, topics=["stats.*"])
        bus.subscribe(bad_handler, topics=["stats.*"])

        for i in range(50):
            await bus.publish_simple("stats.test", data={"i": i})

        stats = bus.get_stats()
        assert stats["published"] == 50
        assert stats["delivered"] == 50  # good handler delivered
        assert stats["failed"] == 50     # bad handler failed


# =====================================================================
# Concurrency tests
# =====================================================================


class TestConcurrency:
    """Tests for concurrent operations across modules."""

    @pytest.mark.asyncio
    async def test_concurrent_spec_constraint_adds(self):
        """Multiple concurrent constraint additions to the same spec."""
        engine = SpecEngine()
        spec = await engine.create("concurrent test")

        async def add_constraint(i: int):
            await engine.add_constraint(spec.id, f"Constraint {i}")

        await asyncio.gather(*[add_constraint(i) for i in range(20)])

        updated = engine.get(spec.id)
        assert len(updated.constraints) == 20

    @pytest.mark.asyncio
    async def test_concurrent_memory_adds(self, tmp_path):
        """Multiple concurrent memory additions."""
        mm = MemoryManager(str(tmp_path / "conc_mem"))

        async def add_memory(i: int):
            await mm.add(f"Concurrent memory {i}", MemoryType.FACT)

        await asyncio.gather(*[add_memory(i) for i in range(50)])
        assert len(mm.list_memories()) == 50

    @pytest.mark.asyncio
    async def test_concurrent_event_publishing(self):
        """Multiple concurrent event publishes."""
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(handler, topics=["conc.*"])

        tasks = [bus.publish_simple("conc.test", data={"i": i}) for i in range(100)]
        await asyncio.gather(*tasks)

        assert len(received) == 100

    @pytest.mark.asyncio
    async def test_concurrent_store_writes(self, tmp_path):
        """Multiple concurrent writes to MemoryStore."""
        store = MemoryStore()

        async def write(i: int):
            await store.put(f"key_{i}", {"value": i})

        await asyncio.gather(*[write(i) for i in range(200)])
        assert await store.count() == 200


# =====================================================================
# Security stress tests
# =====================================================================


class TestSecurityStress:
    """Stress tests for the security subsystem."""

    def test_permission_check_many_permissions(self):
        """Permission check with a large permissions list."""
        perms = [
            Permission(resource=f"resource_{i}", level=PermissionLevel.READ)
            for i in range(100)
        ]
        ctx = AuthContext(user_id="user1", permissions=perms)

        start = time.monotonic()
        for i in range(100):
            assert ctx.has_permission(f"resource_{i}", PermissionLevel.READ) is True
        elapsed = time.monotonic() - start
        assert elapsed < 1.0

    def test_secret_scanning_large_text(self):
        """Secret scanning on a large text block."""
        sm = SecurityManager()
        # 100KB of text with a few secrets buried in it
        clean_text = "This is normal text. " * 5000
        dirty_text = clean_text + " api_key=sk-abcdefghijklmnopqrstuvwxyz0123 " + clean_text
        findings = sm.scan_for_secrets(dirty_text)
        assert len(findings) >= 1

    def test_redact_large_text(self):
        """Redaction on a large text block."""
        sm = SecurityManager()
        text = "Normal text. " * 10000 + "sk-abcdefghijklmnopqrstuvwxyz0123" + " Normal text." * 10000
        redacted = sm.redact_secrets(text)
        assert "sk-" not in redacted


# =====================================================================
# Skill stress tests
# =====================================================================


class TestSkillStress:
    """Stress tests for the skill subsystem."""

    def test_register_100_skills(self, tmp_path):
        """Register 100 skills and verify search works."""
        registry = SkillRegistry(tmp_path / "skills")
        for i in range(100):
            skill = Skill(
                metadata=SkillMetadata(
                    name=f"skill-{i}",
                    description=f"Skill number {i} for testing",
                    tags=[f"tag-{i % 10}"],
                ),
                status=SkillStatus.ACTIVE,
            )
            registry.register(skill)
        assert len(registry) == 100

        results = registry.search("testing")
        assert len(results) == 100

    def test_skill_many_executions(self):
        """A skill with hundreds of recorded executions."""
        skill = Skill(
            metadata=SkillMetadata(name="heavy-use"),
            status=SkillStatus.ACTIVE,
        )
        for i in range(200):
            skill.record_execution(SkillExecution(
                success=i % 5 != 0,  # 80% success rate
                score=0.5 + (i % 10) * 0.05,
            ))
        assert skill.use_count == 200
        assert 0.75 <= skill.success_rate <= 0.85
