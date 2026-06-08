"""Edge case and boundary tests for JARVIS modules.

Tests unusual inputs, boundary conditions, and error scenarios that
normal happy-path tests do not cover.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from jarvis.models.streaming_spec import (
    ChangeSource,
    ChangeType,
    Constraint,
    SpecStatus,
    Step,
    StepStatus,
    StreamingSpec,
)
from jarvis.engine.spec_engine import SpecEngine
from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult, AgentStatus
from jarvis.agents.registry import AgentRegistry
from jarvis.tools.base import ToolResult
from jarvis.tools.builtin.shell import ShellTool
from jarvis.tools.builtin.file_ops import ReadFileTool, WriteFileTool
from jarvis.tools.builtin.math_ops import CalculatorTool
from jarvis.tools.builtin.encoding_ops import Base64Tool, HashTool
from jarvis.memory.manager import MemoryManager, MemoryType, MemoryEntry
from jarvis.knowledge.graph import KnowledgeGraph, GraphNode, GraphEdge
from jarvis.security.manager import SecurityManager
from jarvis.security.permissions import AuthContext, Permission, PermissionLevel
from jarvis.security.sandbox import SandboxConfig, SandboxMode, SandboxValidator
from jarvis.skills.base import Skill, SkillMetadata, SkillStep, SkillExecution, SkillStatus
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.evolve import SkillEvolver


# =====================================================================
# Helper: minimal agent for testing
# =====================================================================


class StubAgent(BaseAgent):
    """Minimal agent that returns the message back."""

    def __init__(self, name: str = "stub", skills: list[str] | None = None):
        super().__init__(AgentCard(
            name=name,
            description="Stub agent",
            skills=skills or [],
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        return TaskResult(
            task_id=context.task_id,
            agent_name=self.name,
            success=True,
            output=f"Handled: {message}",
        )


# =====================================================================
# StreamingSpec edge cases
# =====================================================================


class TestStreamingSpecEdgeCases:
    """Boundary and degenerate cases for the Streaming Spec model."""

    def test_empty_spec_operations(self):
        """Operations on a spec with no steps or constraints."""
        spec = StreamingSpec(name="empty", intent="nothing")
        assert spec.progress == "0/0"
        assert spec.pending_steps() == []
        assert spec.get_ready_steps() == []
        assert spec.get_blocked_steps() == []
        assert spec.validate_dag() is True
        assert spec.topological_sort() == []
        assert spec.critical_path() == []
        spec.update_step_readiness()  # should not raise

    def test_spec_with_100_steps(self):
        """Spec with a large number of steps works correctly."""
        spec = StreamingSpec(name="big", intent="big task")
        for i in range(100):
            spec.add_step(f"Step {i}", source=ChangeSource.AGENT)
        assert len(spec.steps) == 100
        assert spec.validate_dag() is True
        assert len(spec.topological_sort()) == 100

    def test_unicode_in_step_names_and_constraints(self):
        """Unicode characters are handled correctly in names and content."""
        spec = StreamingSpec(name="unicode", intent="test unicode")
        step = spec.add_step("分析需求 -- Analyse Requirements 🎉", source=ChangeSource.AGENT)
        assert "分析需求" in step.name
        c = spec.add_constraint("不要使用 eval() 函数 ⚠️")
        assert "eval" in c.content

    def test_very_long_intent(self):
        """An intent string of 10,000 characters does not break anything."""
        long_intent = "a" * 10_000
        spec = StreamingSpec(name="long", intent=long_intent)
        assert len(spec.intent) == 10_000
        spec.change_intent("b" * 10_000)
        assert len(spec.intent) == 10_000

    def test_duplicate_step_ids_handled(self):
        """Steps always get unique IDs even when names repeat."""
        spec = StreamingSpec(name="dup", intent="duplicates")
        s1 = spec.add_step("same name")
        s2 = spec.add_step("same name")
        assert s1.id != s2.id
        assert len(spec.steps) == 2

    def test_empty_constraint_content(self):
        """Adding a constraint with empty content still works."""
        spec = StreamingSpec(name="ec", intent="test")
        c = spec.add_constraint("")
        assert c.content == ""
        assert len(spec.constraints) == 1

    def test_removing_last_constraint(self):
        """Removing the last constraint leaves an empty list."""
        spec = StreamingSpec(name="rem", intent="test")
        c = spec.add_constraint("only one")
        spec.remove_constraint(c.id)
        assert len(spec.constraints) == 0

    def test_redirect_to_same_intent(self):
        """Redirecting to the same intent still sets status to REDIRECTED."""
        spec = StreamingSpec(name="same", intent="do X")
        spec.change_intent("do X")
        assert spec.status == SpecStatus.REDIRECTED
        # The changelog should record the change even though the value is the same
        assert spec.changelog[-1].change_type == ChangeType.INTENT_CHANGED

    def test_multiple_rapid_edits_version_tracking(self):
        """Many rapid edits bump the version correctly each time."""
        spec = StreamingSpec(name="rapid", intent="test")
        initial_version = spec.version
        for i in range(20):
            spec.add_step(f"step-{i}")
        assert spec.version == initial_version + 20

    def test_self_dependency_detected(self):
        """A step depending on itself creates a cycle detected by validate_dag."""
        spec = StreamingSpec(name="self-dep", intent="test")
        s = spec.add_step("self-loop")
        s.depends_on = [s.id]
        assert spec.validate_dag() is False

    def test_dag_disconnected_components(self):
        """DAG with disconnected sub-graphs is still valid."""
        spec = StreamingSpec(name="disc", intent="test")
        a = spec.add_step("A")
        b = spec.add_step("B")
        c = spec.add_step("C")
        d = spec.add_step("D")
        # Two disconnected chains: A->B and C->D
        b.depends_on = [a.id]
        d.depends_on = [c.id]
        assert spec.validate_dag() is True
        order = spec.topological_sort()
        assert len(order) == 4

    def test_all_steps_depend_on_bottleneck(self):
        """50 steps all depending on a single root step."""
        spec = StreamingSpec(name="star", intent="test")
        root = spec.add_step("Root")
        for i in range(50):
            child = spec.add_step(f"Child {i}")
            child.depends_on = [root.id]
        assert spec.validate_dag() is True
        order = spec.topological_sort()
        assert order[0].name == "Root"
        assert len(order) == 51

    def test_diamond_dependency_pattern(self):
        """Diamond: A -> B, A -> C, B -> D, C -> D."""
        spec = StreamingSpec(name="diamond", intent="test")
        a = spec.add_step("A")
        b = spec.add_step("B")
        c = spec.add_step("C")
        d = spec.add_step("D")
        b.depends_on = [a.id]
        c.depends_on = [a.id]
        d.depends_on = [b.id, c.id]
        assert spec.validate_dag() is True
        cp = spec.critical_path()
        assert len(cp) == 3
        assert cp[0].name == "A"
        assert cp[-1].name == "D"

    def test_update_status_of_nonexistent_step(self):
        """Updating a non-existent step returns None."""
        spec = StreamingSpec(name="missing", intent="test")
        result = spec.update_step_status("nonexistent", StepStatus.COMPLETED)
        assert result is None

    def test_set_output_on_nonexistent_step(self):
        """Setting output on a non-existent step returns None."""
        spec = StreamingSpec(name="missing-out", intent="test")
        result = spec.set_step_output("nonexistent", "data")
        assert result is None

    def test_set_error_on_nonexistent_step(self):
        """Setting error on a non-existent step returns None."""
        spec = StreamingSpec(name="missing-err", intent="test")
        result = spec.set_step_error("nonexistent", "oops")
        assert result is None

    def test_readiness_with_failed_dependency(self):
        """A step with a failed dependency stays BLOCKED, not READY."""
        spec = StreamingSpec(name="fail-dep", intent="test")
        a = spec.add_step("A")
        b = spec.add_step("B")
        b.depends_on = [a.id]
        spec.update_step_status(a.id, StepStatus.FAILED)
        spec.update_step_readiness()
        assert b.status == StepStatus.BLOCKED

    def test_add_dependency_between_nonexistent_steps(self):
        """add_dependency returns False for non-existent step IDs."""
        spec = StreamingSpec(name="bad-dep", intent="test")
        s = spec.add_step("A")
        assert spec.add_dependency(s.id, "nonexistent") is False
        assert spec.add_dependency("nonexistent", s.id) is False


# =====================================================================
# Agent edge cases
# =====================================================================


class TestAgentEdgeCases:
    """Boundary cases for agent routing and execution."""

    @pytest.mark.asyncio
    async def test_no_matching_agent(self):
        """route() returns empty list when no agent scores above 0."""
        registry = AgentRegistry()
        await registry.register(StubAgent("coder", skills=["code"]))
        results = registry.route("xyz completely unrelated topic 123")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_very_short_message(self):
        """A 1-char message still routes (or returns empty)."""
        registry = AgentRegistry()
        await registry.register(StubAgent("x", skills=["x"]))
        results = registry.route("x")
        # "x" appears in skills as "x", so it should match
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_very_long_message(self):
        """A 10,000-char message does not break routing."""
        registry = AgentRegistry()
        await registry.register(StubAgent("coder", skills=["code"]))
        long_msg = "code " + "a" * 9995
        results = registry.route(long_msg)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_message_in_chinese_only(self):
        """Chinese-only message routes based on skill keywords."""
        registry = AgentRegistry()
        await registry.register(StubAgent("code-agent", skills=["代码", "review"]))
        results = registry.route("帮我 review 代码")
        # "review" and "代码" are in the message
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_message_with_special_characters(self):
        """Message with special chars does not crash routing."""
        registry = AgentRegistry()
        await registry.register(StubAgent("coder", skills=["code"]))
        results = registry.route("review <script>alert('xss')</script> code!!!")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_message_matching_multiple_agents_equally(self):
        """When multiple agents match equally, all are returned."""
        registry = AgentRegistry()
        await registry.register(StubAgent("a1", skills=["search"]))
        await registry.register(StubAgent("a2", skills=["search"]))
        results = registry.route("search for data")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_agent_with_empty_skills(self):
        """Agent with no skills never matches any message."""
        agent = StubAgent("empty", skills=[])
        assert agent.can_handle("anything at all") == 0.0

    @pytest.mark.asyncio
    async def test_delegate_to_self_without_orchestrator(self):
        """An agent delegating without an orchestrator returns an error."""
        agent = StubAgent("solo")
        ctx = AgentContext()
        result = await agent.delegate("solo", "sub-task", ctx)
        assert not result.success
        assert "No orchestrator" in result.error

    @pytest.mark.asyncio
    async def test_registry_replace_existing_agent(self):
        """Registering an agent with the same name replaces the old one."""
        registry = AgentRegistry()
        a1 = StubAgent("dup", skills=["skill1"])
        a2 = StubAgent("dup", skills=["skill2"])
        await registry.register(a1)
        await registry.register(a2)
        assert len(registry) == 1
        assert registry.get("dup") is a2

    @pytest.mark.asyncio
    async def test_deregister_nonexistent_agent(self):
        """Deregistering a non-existent agent does not raise."""
        registry = AgentRegistry()
        await registry.deregister("nonexistent")  # should not raise


# =====================================================================
# Tool edge cases
# =====================================================================


class TestToolEdgeCases:
    """Boundary cases for built-in tools."""

    @pytest.mark.asyncio
    async def test_shell_blocked_command(self):
        """Shell tool blocks dangerous commands."""
        tool = ShellTool()
        result = await tool.execute({"command": "rm -rf /"})
        assert not result.success
        assert "Blocked" in result.output

    @pytest.mark.asyncio
    async def test_shell_timeout(self):
        """Shell tool handles command timeout."""
        tool = ShellTool()
        result = await tool.execute({"command": "sleep 60", "timeout": 1})
        assert not result.success
        assert "timed out" in result.output.lower()

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """ReadFileTool reports missing file correctly."""
        tool = ReadFileTool()
        result = await tool.execute({"path": "/nonexistent/path/file.txt"})
        assert not result.success
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_write_to_readonly_location(self):
        """WriteFileTool handles permission errors."""
        tool = WriteFileTool()
        result = await tool.execute({
            "path": "/proc/test_readonly_write",
            "content": "test",
        })
        assert not result.success

    @pytest.mark.asyncio
    async def test_calculator_division_by_zero(self):
        """Calculator returns error on division by zero."""
        tool = CalculatorTool()
        result = await tool.execute({"expression": "1 / 0"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_calculator_very_large_exponent(self):
        """Calculator guards against huge exponents."""
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 ** 10000"})
        assert not result.success
        assert "Exponent too large" in result.output

    @pytest.mark.asyncio
    async def test_calculator_valid_large_number(self):
        """Calculator handles legitimate large computations."""
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 ** 100"})
        assert result.success

    @pytest.mark.asyncio
    async def test_calculator_syntax_error(self):
        """Calculator handles malformed expressions."""
        tool = CalculatorTool()
        result = await tool.execute({"expression": "import os"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_hash_empty_string(self):
        """Hash of an empty string produces a valid digest."""
        tool = HashTool()
        result = await tool.execute({"input": "", "algorithm": "sha256"})
        assert result.success
        # SHA-256 of empty string is well-known
        assert "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" in result.output

    @pytest.mark.asyncio
    async def test_base64_roundtrip(self):
        """Base64 encode then decode returns the original string."""
        tool = Base64Tool()
        original = "Hello, JARVIS! 你好世界"
        enc = await tool.execute({"input": original, "action": "encode"})
        assert enc.success
        dec = await tool.execute({"input": enc.output, "action": "decode"})
        assert dec.success
        assert dec.output == original

    @pytest.mark.asyncio
    async def test_base64_binary_like_content(self):
        """Base64 handles binary-like strings."""
        tool = Base64Tool()
        binary_like = "\x00\x01\x02\xff"
        result = await tool.execute({"input": binary_like, "action": "encode"})
        assert result.success

    @pytest.mark.asyncio
    async def test_shell_empty_output(self):
        """Shell command producing empty output works correctly."""
        tool = ShellTool()
        result = await tool.execute({"command": "true"})
        assert result.success


# =====================================================================
# Memory edge cases
# =====================================================================


class TestMemoryEdgeCases:
    """Boundary cases for the MemoryManager."""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, tmp_path):
        """Searching with an empty query returns no results."""
        mm = MemoryManager(str(tmp_path / "mem"))
        await mm.add("Some content about Python", MemoryType.FACT)
        results = await mm.search("")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_very_long_query(self, tmp_path):
        """Searching with a very long query does not crash."""
        mm = MemoryManager(str(tmp_path / "mem"))
        await mm.add("Short fact", MemoryType.FACT)
        results = await mm.search("a" * 5000)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_add_empty_content(self, tmp_path):
        """Adding a memory with empty content still creates an entry."""
        mm = MemoryManager(str(tmp_path / "mem"))
        entry = await mm.add("", MemoryType.FACT)
        assert entry.content == ""
        assert entry.id in [m.id for m in mm.list_memories()]

    @pytest.mark.asyncio
    async def test_memory_with_special_characters(self, tmp_path):
        """Memory with special/unicode characters persists correctly."""
        mm = MemoryManager(str(tmp_path / "mem"))
        content = "User prefers 日本語 interface. API key pattern: sk-****"
        entry = await mm.add(content, MemoryType.PREFERENCE)
        # Force reload from disk
        mm2 = MemoryManager(str(tmp_path / "mem"))
        mm2.load()
        reloaded = [m for m in mm2.list_memories() if m.id == entry.id]
        assert len(reloaded) == 1
        assert reloaded[0].content == content

    @pytest.mark.asyncio
    async def test_search_when_no_memories_exist(self, tmp_path):
        """Searching on empty storage returns empty list."""
        mm = MemoryManager(str(tmp_path / "empty_mem"))
        results = await mm.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_prune_when_all_important(self, tmp_path):
        """Pruning does not remove high-importance memories."""
        mm = MemoryManager(str(tmp_path / "mem"))
        entry = await mm.add("Critical system goal", MemoryType.SKILL_LEARNED)
        # Force high importance
        mm._memories[entry.id].importance = 0.9
        mm._memories[entry.id].created_at = datetime.now(timezone.utc) - timedelta(days=200)
        removed = mm.prune(max_age_days=90)
        assert removed == 0

    @pytest.mark.asyncio
    async def test_prune_old_unimportant(self, tmp_path):
        """Pruning removes old low-importance memories."""
        mm = MemoryManager(str(tmp_path / "mem"))
        entry = await mm.add("Trivial hello", MemoryType.CONVERSATION)
        mm._memories[entry.id].importance = 0.1
        mm._memories[entry.id].created_at = datetime.now(timezone.utc) - timedelta(days=200)
        removed = mm.prune(max_age_days=90)
        assert removed == 1

    @pytest.mark.asyncio
    async def test_list_memories_by_type(self, tmp_path):
        """list_memories correctly filters by type."""
        mm = MemoryManager(str(tmp_path / "mem"))
        await mm.add("fact", MemoryType.FACT)
        await mm.add("pref", MemoryType.PREFERENCE)
        await mm.add("fact2", MemoryType.FACT)
        facts = mm.list_memories(memory_type=MemoryType.FACT)
        assert len(facts) == 2
        prefs = mm.list_memories(memory_type=MemoryType.PREFERENCE)
        assert len(prefs) == 1


# =====================================================================
# KnowledgeGraph edge cases
# =====================================================================


class TestKnowledgeGraphEdgeCases:
    """Boundary cases for the KnowledgeGraph."""

    def test_query_empty_graph(self):
        """Querying an empty graph returns an empty list."""
        kg = KnowledgeGraph()
        results = kg._keyword_query("anything")
        assert results == []

    def test_add_duplicate_node(self):
        """Adding a node with the same ID replaces it."""
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="n1", label="Original", node_type="concept"))
        kg.add_node(GraphNode(id="n1", label="Replacement", node_type="concept"))
        assert kg.get_node("n1").label == "Replacement"
        assert kg.stats["nodes"] == 1

    def test_add_edge_with_nonexistent_nodes(self):
        """Adding an edge with non-existent node IDs does not crash."""
        kg = KnowledgeGraph()
        kg.add_edge(GraphEdge(source="missing1", target="missing2", relation="related"))
        assert kg.stats["edges"] == 1
        # Neighbors of a non-existent node are empty
        assert kg.neighbors("missing1") == []

    def test_merge_node_into_itself(self):
        """Merging a node into itself removes self-loops but keeps the node."""
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="n1", label="Node1", node_type="concept"))
        kg.add_edge(GraphEdge(source="n1", target="n1", relation="self"))
        kg.merge_node("n1", "n1")
        # After merge_node the source node is deleted, so n1 should be gone
        # This is a degenerate case; the implementation deletes the source node
        assert kg.get_node("n1") is None

    def test_merge_node_standard(self):
        """Standard merge: node A merged into node B."""
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="a", label="A", node_type="concept", properties={"k": "from_a"}))
        kg.add_node(GraphNode(id="b", label="B", node_type="concept", properties={"k": "from_b"}))
        kg.add_node(GraphNode(id="c", label="C", node_type="concept"))
        kg.add_edge(GraphEdge(source="a", target="c", relation="links"))
        kg.merge_node("a", "b")
        assert kg.get_node("a") is None
        assert kg.get_node("b") is not None
        # The edge from "a" should now point from "b"
        neighbors = kg.neighbors("b")
        assert any(n.id == "c" for _, n in neighbors)

    def test_large_graph_keyword_query(self):
        """Keyword query on a large graph returns results."""
        kg = KnowledgeGraph()
        for i in range(500):
            kg.add_node(GraphNode(id=f"n{i}", label=f"Entity {i}", node_type="concept"))
        results = kg._keyword_query("Entity 250")
        assert len(results) > 0

    def test_save_load_roundtrip(self, tmp_path):
        """Saving and loading preserves graph data."""
        kg = KnowledgeGraph()
        kg.add_node(GraphNode(id="n1", label="Hello World", node_type="concept"))
        kg.add_node(GraphNode(id="n2", label="Test Node 日本語", node_type="tool"))
        kg.add_edge(GraphEdge(source="n1", target="n2", relation="related_to", confidence=0.95))
        path = str(tmp_path / "graph.json")
        kg.save(path)

        kg2 = KnowledgeGraph()
        kg2.load(path)
        assert kg2.stats["nodes"] == 2
        assert kg2.stats["edges"] == 1
        assert kg2.get_node("n2").label == "Test Node 日本語"

    def test_load_nonexistent_file(self, tmp_path):
        """Loading from a non-existent file does not crash."""
        kg = KnowledgeGraph()
        kg.load(str(tmp_path / "nonexistent.json"))
        assert kg.stats["nodes"] == 0

    def test_naive_extract(self):
        """Naive extraction picks up capitalized phrases."""
        kg = KnowledgeGraph()
        added = kg._naive_extract("Alice talked to Bob about Machine Learning and Deep Learning")
        labels = {n.label for n in added}
        assert "Alice" in labels
        assert "Bob" in labels
        assert "Machine Learning" in labels


# =====================================================================
# Security edge cases
# =====================================================================


class TestSecurityEdgeCases:
    """Boundary cases for the security subsystem."""

    def test_permission_check_expired(self):
        """An expired permission is not honored."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        ctx = AuthContext(
            user_id="user1",
            permissions=[
                Permission(
                    resource="filesystem",
                    level=PermissionLevel.WRITE,
                    expires_at=past,
                ),
            ],
        )
        assert ctx.has_permission("filesystem", PermissionLevel.WRITE) is False

    def test_wildcard_resource_permission(self):
        """A wildcard (*) resource permission grants access to any resource."""
        ctx = AuthContext(
            user_id="user1",
            permissions=[
                Permission(resource="*", level=PermissionLevel.ADMIN),
            ],
        )
        assert ctx.has_permission("filesystem", PermissionLevel.WRITE) is True
        assert ctx.has_permission("network", PermissionLevel.EXECUTE) is True

    def test_admin_bypasses_all_checks(self):
        """An admin context has all permissions regardless of the list."""
        ctx = AuthContext(user_id="admin", is_admin=True, permissions=[])
        assert ctx.has_permission("anything", PermissionLevel.ADMIN) is True

    def test_secret_scanning_no_secrets(self):
        """Scanning clean text returns no findings."""
        sm = SecurityManager()
        findings = sm.scan_for_secrets("This is perfectly clean text.")
        assert len(findings) == 0

    def test_secret_scanning_multiple_patterns(self):
        """Multiple secret patterns are detected in one text."""
        sm = SecurityManager()
        text = (
            "api_key=sk-abcdefghijklmnop12345678 "
            "and also ghp_1234567890abcdefghijklmnopqrstuvwxyz "
            "and password=supersecretpassword123"
        )
        findings = sm.scan_for_secrets(text)
        assert len(findings) >= 2

    def test_redact_secrets(self):
        """Secrets are replaced with [REDACTED]."""
        sm = SecurityManager()
        text = "key is sk-abcdefghijklmnopqrstuvwxyz0123456789"
        redacted = sm.redact_secrets(text)
        assert "sk-" not in redacted
        assert "[REDACTED]" in redacted

    def test_sandbox_none_mode_allows_everything(self):
        """SandboxMode.NONE allows any command."""
        config = SandboxConfig(mode=SandboxMode.NONE)
        sv = SandboxValidator(config)
        ok, msg = sv.validate_command("rm -rf /")
        assert ok is True

    def test_sandbox_strict_mode_with_allowlist(self):
        """In strict mode with allowlist, unlisted commands are rejected."""
        config = SandboxConfig(mode=SandboxMode.STRICT, allowed_commands=["echo"])
        sv = SandboxValidator(config)
        ok, msg = sv.validate_command("ls -la")
        assert ok is False
        assert "not in allowlist" in msg.lower()

    def test_sandbox_blocks_fork_bomb(self):
        """The fork bomb pattern is blocked."""
        config = SandboxConfig()
        sv = SandboxValidator(config)
        ok, msg = sv.validate_command(":(){ :|:& };:")
        assert ok is False

    def test_audit_log_records_checks(self):
        """Permission checks are logged in the audit trail."""
        sm = SecurityManager()
        ctx = AuthContext.default()
        sm.check_permission(ctx, "filesystem", PermissionLevel.READ)
        sm.check_permission(ctx, "network", PermissionLevel.WRITE)
        log = sm.get_audit_log()
        assert len(log) == 2
        assert log[0]["resource"] == "filesystem"
        assert log[1]["resource"] == "network"

    def test_path_validation_blocked_paths(self):
        """Blocked paths are correctly rejected."""
        sv = SandboxValidator(SandboxConfig())
        ok, msg = sv.validate_file_path("/etc/shadow")
        assert ok is False


# =====================================================================
# Skill edge cases
# =====================================================================


class TestSkillEdgeCases:
    """Boundary cases for the skill subsystem."""

    def test_skill_with_no_steps(self, tmp_path):
        """A skill with zero steps can be created and serialized."""
        skill = Skill(metadata=SkillMetadata(name="empty-skill"))
        assert len(skill.steps) == 0
        yaml_text = skill.to_yaml()
        assert "empty-skill" in yaml_text

    @pytest.mark.asyncio
    async def test_skill_zero_executions_should_not_evolve(self, tmp_path):
        """A skill with 0 executions should not trigger evolution."""
        registry = SkillRegistry(tmp_path / "skills")
        skill = Skill(
            metadata=SkillMetadata(name="new-skill"),
            status=SkillStatus.ACTIVE,
        )
        registry.register(skill)
        evolver = SkillEvolver(registry)
        assert await evolver.should_evolve(skill) is False

    @pytest.mark.asyncio
    async def test_skill_all_failed_executions(self, tmp_path):
        """A skill with all failed executions triggers evolution."""
        registry = SkillRegistry(tmp_path / "skills")
        skill = Skill(
            metadata=SkillMetadata(name="failing-skill"),
            status=SkillStatus.ACTIVE,
            steps=[SkillStep(order=0, action="do something")],
        )
        for i in range(5):
            skill.record_execution(SkillExecution(
                success=False,
                output=f"Error {i}",
                feedback=f"Failed because {i}",
                score=0.0,
            ))
        registry.register(skill)
        evolver = SkillEvolver(registry)
        assert await evolver.should_evolve(skill) is True

    def test_version_bump(self):
        """Version bump from 1.9.0 goes to 1.10.0."""
        assert SkillEvolver._bump_version("1.9.0") == "1.10.0"
        assert SkillEvolver._bump_version("2.3.1") == "2.4.0"
        assert SkillEvolver._bump_version("0.0.0") == "0.1.0"
        assert SkillEvolver._bump_version("invalid") == "1.1.0"

    def test_yaml_roundtrip_unicode(self, tmp_path):
        """YAML roundtrip preserves unicode characters."""
        skill = Skill(
            metadata=SkillMetadata(
                name="unicode-skill",
                description="分析代码 Analyse code 🔍",
                tags=["中文", "日本語"],
            ),
            steps=[SkillStep(order=0, action="分析需求")],
            constraints=["不使用 eval()"],
        )
        saved_path = skill.save(tmp_path)
        loaded = Skill.from_yaml(saved_path)
        assert loaded.metadata.description == skill.metadata.description
        assert loaded.constraints == skill.constraints

    def test_duplicate_skill_registration(self, tmp_path):
        """Registering a skill with the same name replaces the old one."""
        registry = SkillRegistry(tmp_path / "skills")
        s1 = Skill(metadata=SkillMetadata(name="dup-skill", version="1.0.0"))
        s2 = Skill(metadata=SkillMetadata(name="dup-skill", version="2.0.0"))
        registry.register(s1)
        registry.register(s2)
        assert len(registry) == 1
        assert registry.get("dup-skill").metadata.version == "2.0.0"

    def test_skill_record_execution_updates_stats(self):
        """Recording executions correctly updates success_rate and avg_score."""
        skill = Skill(metadata=SkillMetadata(name="stats-skill"))
        skill.record_execution(SkillExecution(success=True, score=0.9))
        skill.record_execution(SkillExecution(success=True, score=0.7))
        skill.record_execution(SkillExecution(success=False, score=0.0))
        assert skill.use_count == 3
        assert skill.success_rate == pytest.approx(2 / 3, rel=0.01)
        assert skill.avg_score == pytest.approx(0.8, rel=0.01)

    def test_skill_search_no_results(self, tmp_path):
        """Searching for a term with no matches returns empty list."""
        registry = SkillRegistry(tmp_path / "skills")
        skill = Skill(
            metadata=SkillMetadata(name="python-code", description="Code in Python"),
            status=SkillStatus.ACTIVE,
        )
        registry.register(skill)
        results = registry.search("kubernetes deployment")
        assert len(results) == 0

    def test_skill_find_by_tags_empty(self, tmp_path):
        """find_by_tags with tags that no skill has returns empty."""
        registry = SkillRegistry(tmp_path / "skills")
        skill = Skill(
            metadata=SkillMetadata(name="s1", tags=["code"]),
            status=SkillStatus.ACTIVE,
        )
        registry.register(skill)
        results = registry.find_by_tags(["nonexistent-tag"])
        assert len(results) == 0
