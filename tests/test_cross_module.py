"""Cross-module integration tests verifying JARVIS modules work together.

These tests exercise real interactions between two or more subsystems
(e.g., Spec + Skill, Agent + Memory, Security + Tools) to catch
integration issues that unit tests miss.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

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
from jarvis.agents.orchestrator import Orchestrator
from jarvis.agents.context import ContextBuilder
from jarvis.memory.manager import MemoryManager, MemoryType
from jarvis.knowledge.graph import KnowledgeGraph, GraphNode, GraphEdge
from jarvis.skills.base import Skill, SkillMetadata, SkillStep, SkillExecution, SkillStatus
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.evolve import SkillEvolver
from jarvis.events.bus import EventBus, Event
from jarvis.security.manager import SecurityManager
from jarvis.security.permissions import AuthContext, Permission, PermissionLevel
from jarvis.security.sandbox import SandboxConfig, SandboxValidator
from jarvis.storage.json_store import JSONStore
from jarvis.storage.memory_store import MemoryStore
from jarvis.observability.tracer import Tracer
from jarvis.notifications.manager import NotificationManager
from jarvis.notifications.models import NotificationChannel, NotificationPriority
from jarvis.i18n.core import I18n
from jarvis.validation.core import ValidationSeverity


# =====================================================================
# Helper agents
# =====================================================================


class MockCodeAgent(BaseAgent):
    """Code agent stub for integration testing."""

    def __init__(self):
        super().__init__(AgentCard(
            name="code-agent",
            description="Code review and generation",
            skills=["code", "review", "debug"],
            domain="engineering",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"code-review: analyzed '{message[:50]}'",
        )


class MockKnowledgeAgent(BaseAgent):
    """Knowledge agent stub for integration testing."""

    def __init__(self):
        super().__init__(AgentCard(
            name="knowledge-agent",
            description="Knowledge search and graph queries",
            skills=["search", "knowledge", "docs"],
            domain="research",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"search-result: found docs for '{message[:50]}'",
        )


class MockOpsAgent(BaseAgent):
    """Ops agent stub for integration testing."""

    def __init__(self):
        super().__init__(AgentCard(
            name="ops-agent",
            description="Operations and deployment",
            skills=["deploy", "monitor", "alert"],
            domain="ops",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"ops-result: handled '{message[:50]}'",
        )


# =====================================================================
# Spec -> Skill pipeline
# =====================================================================


class TestSpecToSkillPipeline:
    """Test the full Spec -> Execute -> Distill Skill -> Evolve pipeline."""

    @pytest.mark.asyncio
    async def test_spec_to_skill_roundtrip(self, tmp_path):
        """Create a spec, complete it, distill it into a skill."""
        # 1. Create and execute a spec
        engine = SpecEngine()
        spec = await engine.create("migrate CI to GitHub Actions")
        for step in spec.steps:
            await engine.update_step(spec.id, step.id, status=StepStatus.COMPLETED, output="done")
        completed_spec = engine.get(spec.id)
        assert completed_spec.status == SpecStatus.COMPLETED

        # 2. Distill into a skill
        skill_registry = SkillRegistry(tmp_path / "skills")
        evolver = SkillEvolver(skill_registry)
        skill = await evolver.distill_from_spec(completed_spec)
        assert skill.metadata.name is not None
        assert skill.parent_spec_id == completed_spec.id
        assert skill.status == SkillStatus.DRAFT
        assert len(skill.steps) == len(completed_spec.steps)

        # 3. Verify skill is in the registry
        found = skill_registry.get(skill.metadata.name)
        assert found is not None
        assert found.id == skill.id

    @pytest.mark.asyncio
    async def test_skill_improves_over_executions(self, tmp_path):
        """Execute a skill multiple times and check evolution triggers."""
        skill_registry = SkillRegistry(tmp_path / "skills")

        skill = Skill(
            metadata=SkillMetadata(name="ci-migration", version="1.0.0"),
            status=SkillStatus.ACTIVE,
            steps=[
                SkillStep(order=0, action="Analyze current CI"),
                SkillStep(order=1, action="Create GitHub Actions config"),
            ],
        )
        skill_registry.register(skill)

        evolver = SkillEvolver(skill_registry)

        # Not enough executions yet
        assert await evolver.should_evolve(skill) is False

        # Record some poor executions
        for i in range(5):
            skill.record_execution(SkillExecution(
                success=i % 3 != 0,  # ~67% success
                output=f"Result {i}",
                feedback="Could be better" if i % 3 == 0 else "",
                score=0.5,
            ))

        # Now should evolve (success_rate < 0.8)
        assert await evolver.should_evolve(skill) is True

        # Attempt improvement
        improved = await evolver.improve_skill(skill)
        assert improved is not None
        assert improved.metadata.version == "1.1.0"
        assert improved.parent_skill_id == skill.id

    @pytest.mark.asyncio
    async def test_distilled_skill_saves_and_loads(self, tmp_path):
        """A distilled skill can be saved to disk and reloaded."""
        engine = SpecEngine()
        spec = await engine.create("analyze data pipeline")
        for step in spec.steps:
            await engine.update_step(spec.id, step.id, status=StepStatus.COMPLETED, output="ok")

        skill_registry = SkillRegistry(tmp_path / "skills")
        evolver = SkillEvolver(skill_registry)
        skill = await evolver.distill_from_spec(engine.get(spec.id))

        # Save and reload
        saved_path = skill.save(tmp_path / "saved_skills")
        loaded = Skill.from_yaml(saved_path)
        assert loaded.metadata.name == skill.metadata.name
        assert len(loaded.steps) == len(skill.steps)


# =====================================================================
# Agent + Memory integration
# =====================================================================


class TestAgentWithMemory:
    """Test agents using memory context."""

    @pytest.mark.asyncio
    async def test_agent_gets_memory_context(self, tmp_path):
        """ContextBuilder includes memory context in the prompt."""
        mm = MemoryManager(str(tmp_path / "mem"))
        await mm.add("User prefers Python 3.12", MemoryType.PREFERENCE)
        await mm.add("Project uses pytest for testing", MemoryType.FACT)

        memory_context = mm.get_context(limit=5)
        assert "Python" in memory_context

        builder = ContextBuilder()
        prompt = builder.build(
            system_prompt="You are a code review agent.",
            memory_context=memory_context,
            constraints=["Do not modify production code"],
        )
        assert "code review agent" in prompt
        assert "Do not modify production code" in prompt
        assert "Python" in prompt

    @pytest.mark.asyncio
    async def test_memory_persists_across_sessions(self, tmp_path):
        """Memories added in one session are available in the next."""
        path = str(tmp_path / "persist_mem")
        mm1 = MemoryManager(path)
        await mm1.add("Important fact about the system architecture", MemoryType.FACT)
        mm1.save()

        # Simulate new session
        mm2 = MemoryManager(path)
        mm2.load()
        memories = mm2.list_memories()
        assert len(memories) == 1
        assert "architecture" in memories[0].content


# =====================================================================
# Security + Tools integration
# =====================================================================


class TestSecurityIntegration:
    """Test security checks integrate with tools and agents."""

    def test_sandbox_blocks_dangerous_commands(self):
        """SandboxValidator correctly blocks dangerous shell commands."""
        config = SandboxConfig()
        sv = SandboxValidator(config)

        dangerous = ["rm -rf /", "rm -rf /*", "shutdown", "mkfs.ext4 /dev/sda"]
        for cmd in dangerous:
            ok, msg = sv.validate_command(cmd)
            assert ok is False, f"Should block: {cmd}"

        safe = ["ls -la", "echo hello", "cat file.txt", "python script.py"]
        for cmd in safe:
            ok, msg = sv.validate_command(cmd)
            assert ok is True, f"Should allow: {cmd}"

    def test_secret_redaction_in_output(self):
        """SecurityManager redacts API keys and tokens from output text."""
        sm = SecurityManager()
        output = (
            "Connecting with API key api_key=sk-proj-abcdefghijklmnopqrstuvwxyz\n"
            "Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz\n"
            "Result: success"
        )
        redacted = sm.redact_secrets(output)
        assert "sk-proj-" not in redacted
        assert "ghp_" not in redacted
        assert "[REDACTED]" in redacted
        assert "Result: success" in redacted

    def test_permission_hierarchy(self):
        """Higher permission levels encompass lower ones."""
        ctx = AuthContext(
            user_id="user1",
            permissions=[
                Permission(resource="filesystem", level=PermissionLevel.EXECUTE),
            ],
        )
        # EXECUTE (3) >= READ (1) and WRITE (2)
        assert ctx.has_permission("filesystem", PermissionLevel.READ) is True
        assert ctx.has_permission("filesystem", PermissionLevel.WRITE) is True
        assert ctx.has_permission("filesystem", PermissionLevel.EXECUTE) is True
        # But not ADMIN (4)
        assert ctx.has_permission("filesystem", PermissionLevel.ADMIN) is False


# =====================================================================
# Observability integration
# =====================================================================


class TestObservabilityIntegration:
    """Test tracing and metrics work across modules."""

    @pytest.mark.asyncio
    async def test_trace_spans_cover_spec_execution(self):
        """Creating trace spans for spec step execution."""
        tracer = Tracer()
        engine = SpecEngine()

        spec = await engine.create("traced task")
        trace_id = tracer.start_trace("spec_execution")

        root_span = tracer.start_span(trace_id, "execute_spec", spec_id=spec.id)

        for step in spec.steps:
            async with tracer.trace_operation(trace_id, f"step_{step.name}", parent_span_id=root_span.span_id):
                await engine.update_step(spec.id, step.id, status=StepStatus.COMPLETED, output="ok")

        root_span.end("ok")

        trace = tracer.get_trace(trace_id)
        # Root span + one span per step
        assert len(trace) == 1 + len(spec.steps)
        assert all(s["status"] == "ok" for s in trace)

    @pytest.mark.asyncio
    async def test_trace_error_propagation(self):
        """Error spans are correctly recorded in traces."""
        tracer = Tracer()
        trace_id = tracer.start_trace("error_test")

        with pytest.raises(ValueError):
            async with tracer.trace_operation(trace_id, "failing_op"):
                raise ValueError("test error")

        trace = tracer.get_trace(trace_id)
        assert len(trace) == 1
        assert trace[0]["status"] == "error"
        assert "test error" in trace[0]["attributes"].get("error.message", "")

    def test_tracer_persistence(self, tmp_path):
        """Tracer can save and list traces."""
        tracer = Tracer(storage_path=str(tmp_path / "traces"))
        trace_id = tracer.start_trace("persist")
        span = tracer.start_span(trace_id, "test_op")
        span.end()
        tracer.save_trace(trace_id)

        traces = tracer.list_traces()
        assert len(traces) == 1
        assert traces[0]["trace_id"] == trace_id


# =====================================================================
# EventBus integration
# =====================================================================


class TestEventBusIntegration:
    """Test event bus connects modules."""

    @pytest.mark.asyncio
    async def test_spec_events_reach_subscribers(self):
        """Events emitted by SpecEngine are receivable by subscribers."""
        engine = SpecEngine()
        events_received = []

        async def on_event(spec_id, event_type, data):
            events_received.append((spec_id, event_type))

        engine.on_event(on_event)

        spec = await engine.create("event test")
        await asyncio.sleep(0.05)  # let tasks complete
        assert any(e[1] == "spec_created" for e in events_received)

        # Add a constraint and check for event
        await engine.add_constraint(spec.id, "no breaking changes")
        await asyncio.sleep(0.05)
        assert any(e[1] == "constraint_added" for e in events_received)

    @pytest.mark.asyncio
    async def test_eventbus_with_middleware(self):
        """Middleware can transform or drop events."""
        bus = EventBus()
        received = []

        # Middleware that drops events with "drop" in the topic
        def drop_middleware(event: Event) -> Event | None:
            if "drop" in event.topic:
                return None
            return event

        bus.add_middleware(drop_middleware)

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(handler, topics=["*"])

        await bus.publish_simple("keep.this")
        await bus.publish_simple("drop.this")
        await bus.publish_simple("keep.also")

        assert len(received) == 2
        assert all("drop" not in e.topic for e in received)


# =====================================================================
# Notification integration
# =====================================================================


class TestNotificationOnEvents:
    """Test notifications triggered by system events."""

    @pytest.mark.asyncio
    async def test_notification_on_spec_complete(self):
        """Completing a spec triggers a notification."""
        engine = SpecEngine()
        nm = NotificationManager()
        notifications_sent = []

        async def on_event(spec_id, event_type, data):
            if event_type == "step_updated":
                # Check if spec is now completed
                spec = engine.get(spec_id)
                if spec and spec.status == SpecStatus.COMPLETED:
                    n = await nm.notify(
                        title=f"Spec {spec_id} completed",
                        body=f"All {len(spec.steps)} steps finished",
                        priority=NotificationPriority.NORMAL,
                        channel=NotificationChannel.LOG,
                        source="spec-engine",
                    )
                    notifications_sent.append(n)

        engine.on_event(on_event)

        spec = await engine.create("notify test")
        for step in spec.steps:
            await engine.update_step(spec.id, step.id, status=StepStatus.COMPLETED)

        await asyncio.sleep(0.1)  # let async callbacks complete
        assert len(notifications_sent) >= 1
        assert "completed" in notifications_sent[0].title.lower()

    @pytest.mark.asyncio
    async def test_notification_rate_limiting(self):
        """Rate limiter prevents notification flooding."""
        nm = NotificationManager(rate_limit=5)

        for i in range(10):
            await nm.notify(
                title=f"Alert {i}",
                channel=NotificationChannel.LOG,
            )

        stats = nm.get_stats()
        # At most 5 should be SENT, rest PENDING
        sent_count = stats["by_status"].get("sent", 0)
        pending_count = stats["by_status"].get("pending", 0)
        assert sent_count <= 5
        assert sent_count + pending_count == 10


# =====================================================================
# I18n integration
# =====================================================================


class TestI18nIntegration:
    """Test i18n strings used correctly across modules."""

    def test_locale_switching(self):
        """Switching locales changes the returned translations."""
        I18n.reset()
        i18n = I18n.instance()

        # Add test strings
        i18n.add_strings("en", {"greeting": "Hello", "farewell": "Goodbye"})
        i18n.add_strings("zh", {"greeting": "你好", "farewell": "再见"})

        i18n.set_locale("en")
        assert i18n.t("greeting") == "Hello"

        i18n.set_locale("zh")
        assert i18n.t("greeting") == "你好"

        # Fallback for missing key
        i18n.add_strings("en", {"only_en": "English only"})
        i18n.set_locale("zh")
        assert i18n.t("only_en") == "English only"  # falls back to en

        I18n.reset()

    def test_interpolation(self):
        """String interpolation works correctly."""
        I18n.reset()
        i18n = I18n.instance()
        i18n.add_strings("en", {"welcome": "Welcome, {name}! You have {count} tasks."})
        i18n.set_locale("en")
        result = i18n.t("welcome", name="JARVIS", count=5)
        assert result == "Welcome, JARVIS! You have 5 tasks."
        I18n.reset()

    def test_missing_key_returns_key(self):
        """Missing keys return the key itself."""
        I18n.reset()
        i18n = I18n.instance()
        i18n.set_locale("en")
        assert i18n.t("nonexistent.key") == "nonexistent.key"
        I18n.reset()

    def test_coverage_analysis(self):
        """Coverage analysis detects missing translations."""
        I18n.reset()
        i18n = I18n.instance()
        # Replace (not merge) fallback locale with a known set
        i18n.load_locale_file("en", {"a": "A", "b": "B", "c": "C"})
        i18n.load_locale_file("zh", {"a": "A_zh"})
        i18n.set_fallback_locale("en")

        missing = i18n.missing_keys("zh")
        assert "b" in missing
        assert "c" in missing

        coverage = i18n.coverage("zh")
        assert coverage == pytest.approx(1 / 3, rel=0.01)
        I18n.reset()


# =====================================================================
# Storage backends equivalence
# =====================================================================


class TestStorageBackends:
    """Test all storage backends produce equivalent results."""

    @pytest.mark.asyncio
    async def test_json_and_memory_stores_equivalent(self, tmp_path):
        """JSONStore and MemoryStore return the same data for the same operations."""
        json_store = JSONStore(str(tmp_path / "json"))
        mem_store = MemoryStore()

        test_data = {"key": "value", "nested": {"a": 1, "list": [1, 2, 3]}}

        await json_store.put("test", test_data)
        await mem_store.put("test", test_data)

        json_result = await json_store.get("test")
        mem_result = await mem_store.get("test")
        assert json_result == mem_result

    @pytest.mark.asyncio
    async def test_delete_consistency(self, tmp_path):
        """Delete semantics are consistent across backends."""
        json_store = JSONStore(str(tmp_path / "json"))
        mem_store = MemoryStore()

        for store in [json_store, mem_store]:
            await store.put("k1", {"v": 1})
            await store.put("k2", {"v": 2})
            assert await store.exists("k1") is True
            result = await store.delete("k1")
            assert result is True
            assert await store.exists("k1") is False
            # Deleting non-existent key
            result = await store.delete("nonexistent")
            assert result is False

    @pytest.mark.asyncio
    async def test_list_keys_consistency(self, tmp_path):
        """list_keys returns the same keys from both backends."""
        json_store = JSONStore(str(tmp_path / "json"))
        mem_store = MemoryStore()

        for store in [json_store, mem_store]:
            for i in range(10):
                await store.put(f"key_{i:02d}", {"idx": i})
            keys = await store.list_keys()
            assert len(keys) == 10
            assert keys == sorted(keys)

    @pytest.mark.asyncio
    async def test_count_consistency(self, tmp_path):
        """count() returns the same value from both backends."""
        json_store = JSONStore(str(tmp_path / "json"))
        mem_store = MemoryStore()

        for store in [json_store, mem_store]:
            for i in range(15):
                await store.put(f"item_{i}", {"v": i})
            assert await store.count() == 15

    @pytest.mark.asyncio
    async def test_get_many_consistency(self, tmp_path):
        """get_many returns consistent results."""
        json_store = JSONStore(str(tmp_path / "json"))
        mem_store = MemoryStore()

        for store in [json_store, mem_store]:
            await store.put("a", {"v": 1})
            await store.put("b", {"v": 2})
            result = await store.get_many(["a", "b", "missing"])
            assert result["a"] == {"v": 1}
            assert result["b"] == {"v": 2}
            assert result["missing"] is None


# =====================================================================
# Knowledge Graph + Memory integration
# =====================================================================


class TestKnowledgeMemoryIntegration:
    """Test knowledge graph and memory working together for context."""

    @pytest.mark.asyncio
    async def test_graph_and_memory_context_combined(self, tmp_path):
        """Both graph and memory context feed into the agent prompt."""
        # Set up memory
        mm = MemoryManager(str(tmp_path / "mem"))
        await mm.add("User uses FastAPI for web services", MemoryType.FACT)
        memory_ctx = mm.get_context()

        # Set up knowledge graph
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="fastapi", label="FastAPI", node_type="tool"))
        kg.add_node(GraphNode(id="python", label="Python", node_type="language"))
        kg.add_edge(GraphEdge(source="fastapi", target="python", relation="built_with"))

        # Build agent context
        graph_nodes = kg._keyword_query("FastAPI")
        knowledge_ctx = "\n".join(f"- {n.label} ({n.node_type})" for n in graph_nodes)

        builder = ContextBuilder()
        prompt = builder.build(
            system_prompt="You are a helpful coding assistant.",
            memory_context=memory_ctx,
            knowledge_context=knowledge_ctx,
        )

        assert "FastAPI" in prompt
        assert "coding assistant" in prompt

    @pytest.mark.asyncio
    async def test_graph_save_load_with_search(self, tmp_path):
        """Graph is saved, reloaded, and then queried via keyword search."""
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="react", label="React", node_type="framework"))
        kg.add_node(GraphNode(id="vue", label="Vue.js", node_type="framework"))
        kg.add_node(GraphNode(id="frontend", label="Frontend", node_type="concept"))
        kg.add_edge(GraphEdge(source="react", target="frontend", relation="is_a"))
        kg.add_edge(GraphEdge(source="vue", target="frontend", relation="is_a"))

        path = str(tmp_path / "graph.json")
        kg.save(path)

        kg2 = KnowledgeGraph()
        kg2.load(path)

        results = kg2._keyword_query("React")
        assert any(n.label == "React" for n in results)

        # Check neighbors after reload
        neighbors = kg2.neighbors("react")
        assert len(neighbors) == 1
        assert neighbors[0][1].label == "Frontend"


# =====================================================================
# Spec + Event + Notification full pipeline
# =====================================================================


class TestFullPipeline:
    """End-to-end test combining spec execution, events, and notifications."""

    @pytest.mark.asyncio
    async def test_spec_execution_to_notification(self):
        """Full pipeline: create spec -> execute steps -> notify on completion."""
        engine = SpecEngine()
        bus = EventBus()
        nm = NotificationManager()
        events_log = []

        async def spec_event_handler(spec_id, event_type, data):
            events_log.append(event_type)
            # Publish to EventBus for broader consumption
            await bus.publish_simple(
                f"spec.{event_type}",
                source="spec-engine",
                spec_id=spec_id,
            )

        engine.on_event(spec_event_handler)

        # Subscribe bus to spec events
        spec_notifications = []

        async def notification_handler(event: Event):
            if event.data.get("spec_id"):
                n = await nm.notify(
                    title=f"Spec event: {event.topic}",
                    channel=NotificationChannel.LOG,
                )
                spec_notifications.append(n)

        bus.subscribe(notification_handler, topics=["spec.*"])

        # Execute a spec
        spec = await engine.create("full pipeline test")
        await asyncio.sleep(0.05)

        for step in spec.steps:
            await engine.update_step(spec.id, step.id, status=StepStatus.COMPLETED)
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.1)

        # Verify events flowed through the pipeline
        assert "spec_created" in events_log
        assert len(spec_notifications) > 0

    @pytest.mark.asyncio
    async def test_constraint_change_triggers_events(self):
        """Adding and removing constraints triggers proper events."""
        engine = SpecEngine()
        events_log = []

        async def event_handler(spec_id, event_type, data):
            events_log.append(event_type)

        engine.on_event(event_handler)

        spec = await engine.create("constraint test")
        await asyncio.sleep(0.05)

        await engine.add_constraint(spec.id, "must use HTTPS")
        await asyncio.sleep(0.05)

        constraint_id = engine.get(spec.id).constraints[0].id
        await engine.remove_constraint(spec.id, constraint_id)
        await asyncio.sleep(0.05)

        assert "constraint_added" in events_log
        assert "constraint_removed" in events_log
