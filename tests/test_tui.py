"""Tests for the JARVIS TUI package.

Covers:
- TUIApp initialization and command routing
- DashboardView rendering
- ChatView message rendering
- SpecView detail and DAG rendering
- Help command output
"""

from __future__ import annotations

import pytest
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

# ---------------------------------------------------------------------------
# Helpers – lightweight fakes for the objects the TUI renders
# ---------------------------------------------------------------------------


class _FakeStatus:
    def __init__(self, value: str = "idle"):
        self.value = value


class _FakeCard:
    def __init__(
        self,
        name: str = "test-agent",
        domain: str = "test",
        description: str = "A test agent",
        skills: list[str] | None = None,
        can_delegate: bool = False,
    ):
        self.name = name
        self.domain = domain
        self.description = description
        self.skills = skills or ["skill-a", "skill-b"]
        self.can_delegate = can_delegate


class _FakeAgent:
    def __init__(
        self,
        name: str = "test-agent",
        domain: str = "test",
        status: str = "idle",
        skills: list[str] | None = None,
    ):
        self.name = name
        self.card = _FakeCard(name=name, domain=domain, skills=skills)
        self.status = _FakeStatus(status)


class _FakeConstraint:
    def __init__(self, content: str = "must be fast", active: bool = True, added_by_val: str = "human"):
        self.content = content
        self.active = active
        self.added_by = _FakeStatus(added_by_val)  # reuse value holder
        self.id = "c1"


class _FakeStep:
    def __init__(
        self,
        step_id: str = "s1",
        name: str = "Step 1",
        status: str = "pending",
        depends_on: list[str] | None = None,
        output: str | None = None,
    ):
        self.id = step_id
        self.name = name
        self.status = _FakeStatus(status)
        self.depends_on = depends_on or []
        self.output = output


class _FakeSpec:
    def __init__(
        self,
        spec_id: str = "spec123456",
        name: str = "Test Spec",
        intent: str = "Do something",
        status: str = "planning",
        steps: list[_FakeStep] | None = None,
        constraints: list[_FakeConstraint] | None = None,
    ):
        self.id = spec_id
        self.name = name
        self.intent = intent
        self.status = _FakeStatus(status)
        self.steps = steps or []
        self.constraints = constraints or []
        self.changelog: list = []
        self.progress = "0/0 (0%)"

    def get_step(self, step_id: str):
        for s in self.steps:
            if s.id == step_id:
                return s
        return None


# ---------------------------------------------------------------------------
# TUIApp tests
# ---------------------------------------------------------------------------


class TestTUIApp:
    """Tests for TUIApp initialisation and command routing."""

    def test_init(self):
        """TUIApp can be instantiated without side effects."""
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        assert app._running is False
        assert app._current_view == "dashboard"
        assert app.jarvis is not None

    @pytest.mark.asyncio
    async def test_handle_command_routes_help(self):
        """'help' and 'h' both invoke the help handler."""
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        app._cmd_help = AsyncMock()

        await app._handle_command("help")
        app._cmd_help.assert_awaited_once_with("")

        app._cmd_help.reset_mock()
        await app._handle_command("h")
        app._cmd_help.assert_awaited_once_with("")

    @pytest.mark.asyncio
    async def test_handle_command_routes_dashboard(self):
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        app._cmd_dashboard = AsyncMock()
        await app._handle_command("dashboard")
        app._cmd_dashboard.assert_awaited_once_with("")

    @pytest.mark.asyncio
    async def test_handle_command_routes_shortcut_d(self):
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        app._cmd_dashboard = AsyncMock()
        await app._handle_command("d")
        app._cmd_dashboard.assert_awaited_once_with("")

    @pytest.mark.asyncio
    async def test_handle_command_chat_with_args(self):
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        app._cmd_chat = AsyncMock()
        await app._handle_command("chat hello world")
        app._cmd_chat.assert_awaited_once_with("hello world")

    @pytest.mark.asyncio
    async def test_handle_command_unknown_falls_to_chat(self):
        """Unknown commands are treated as chat messages."""
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        app._cmd_chat = AsyncMock()
        await app._handle_command("what is the weather?")
        app._cmd_chat.assert_awaited_once_with("what is the weather?")

    @pytest.mark.asyncio
    async def test_handle_command_quit(self):
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        app._shutdown = AsyncMock()
        app._running = True
        await app._handle_command("quit")
        assert app._running is False

    @pytest.mark.asyncio
    async def test_cmd_help_output(self):
        """Help command prints a table with all documented commands."""
        from jarvis.tui.app import TUIApp

        app = TUIApp()

        buf = StringIO()
        test_console = Console(file=buf, force_terminal=True, width=120)
        with patch("jarvis.tui.app.console", test_console):
            await app._cmd_help()

        output = buf.getvalue()
        assert "JARVIS Commands" in output
        assert "help" in output
        assert "dashboard" in output
        assert "chat" in output
        assert "quit" in output

    def test_commands_list_completeness(self):
        """All routable commands appear in the COMMANDS help list."""
        from jarvis.tui.app import TUIApp

        app = TUIApp()
        # Gather all documented command words (first column, before any space)
        documented = {row[0].split()[0] for row in app.COMMANDS}
        # Every documented command should have a handler
        for cmd_word in documented:
            if cmd_word in ("quit", "clear"):
                continue  # quit/clear are simple
            # At least one of the handler keys should start with the command
            assert any(
                cmd_word.startswith(k) for k in [
                    "help", "dashboard", "chat", "agents", "tools",
                    "spec", "skills", "memory", "knowledge", "clear", "quit",
                ]
            ), f"Command '{cmd_word}' not documented"


# ---------------------------------------------------------------------------
# DashboardView tests
# ---------------------------------------------------------------------------


class TestDashboardView:
    def test_render_agent_cards_returns_table(self):
        from jarvis.tui.views import DashboardView

        agents = [
            _FakeAgent("code-agent", "code", "idle", ["python", "debug"]),
            _FakeAgent("data-agent", "data", "busy", ["sql", "pandas", "viz", "ml"]),
        ]
        table = DashboardView.render_agent_cards(agents)
        assert isinstance(table, Table)
        assert table.row_count == 2

    def test_render_agent_cards_empty(self):
        from jarvis.tui.views import DashboardView

        table = DashboardView.render_agent_cards([])
        assert isinstance(table, Table)
        assert table.row_count == 0

    def test_render_agent_cards_truncates_skills(self):
        """When an agent has > 3 skills, the display truncates with '+N'."""
        from jarvis.tui.views import DashboardView

        agents = [_FakeAgent("a", "d", "idle", ["s1", "s2", "s3", "s4", "s5"])]
        table = DashboardView.render_agent_cards(agents)

        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        c.print(table)
        output = buf.getvalue()
        assert "+2" in output

    def test_render_spec_timeline_panel(self):
        from jarvis.tui.views import DashboardView

        specs = [
            _FakeSpec("s1", "Build API", status="executing"),
            _FakeSpec("s2", "Deploy", status="completed"),
        ]
        panel = DashboardView.render_spec_timeline(specs)
        assert isinstance(panel, Panel)

    def test_render_spec_timeline_empty(self):
        from jarvis.tui.views import DashboardView

        panel = DashboardView.render_spec_timeline([])
        assert isinstance(panel, Panel)

    def test_render_system_tree(self):
        from jarvis.tui.views import DashboardView

        app = MagicMock()
        app.registry.list_agents.return_value = [
            _FakeAgent("code-agent", "code"),
        ]
        app._tool_registry = None
        app.spec_engine.list_specs.return_value = []
        app.knowledge_graph.stats = {"nodes": 5, "edges": 3}

        tree = DashboardView.render_system_tree(app)
        assert isinstance(tree, Tree)


# ---------------------------------------------------------------------------
# ChatView tests
# ---------------------------------------------------------------------------


class TestChatView:
    def test_render_user_message(self):
        from jarvis.tui.views import ChatView

        panel = ChatView.render_message("user", "Hello JARVIS")
        assert isinstance(panel, Panel)
        assert panel.title is not None
        # Title contains "You"
        assert "You" in str(panel.title)

    def test_render_agent_message_plain(self):
        from jarvis.tui.views import ChatView

        panel = ChatView.render_message("agent", "I can help with that.", "code-agent")
        assert isinstance(panel, Panel)
        assert "code-agent" in str(panel.title)

    def test_render_agent_message_markdown(self):
        from jarvis.tui.views import ChatView

        content = "# Heading\n\n```python\nprint('hi')\n```"
        panel = ChatView.render_message("agent", content, "code-agent")
        assert isinstance(panel, Panel)

    def test_render_agent_message_default_name(self):
        """When no agent name is given, title defaults to 'JARVIS'."""
        from jarvis.tui.views import ChatView

        panel = ChatView.render_message("agent", "Hello")
        assert "JARVIS" in str(panel.title)

    def test_render_conversation(self):
        from jarvis.tui.views import ChatView

        messages = [
            {"role": "user", "content": "Hello", "agent": ""},
            {"role": "agent", "content": "Hi there!", "agent": "code-agent"},
        ]
        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        with patch("jarvis.tui.views.console", c):
            ChatView.render_conversation(messages)
        output = buf.getvalue()
        assert "Hello" in output
        assert "Hi there" in output


# ---------------------------------------------------------------------------
# SpecView tests
# ---------------------------------------------------------------------------


class TestSpecView:
    def test_render_spec_detail_basic(self):
        """render_spec_detail prints without error for a minimal spec."""
        from jarvis.tui.views import SpecView

        spec = _FakeSpec(
            steps=[
                _FakeStep("s1", "StepAlpha", "completed"),
                _FakeStep("s2", "StepBeta", "pending", depends_on=["s1"]),
            ],
            constraints=[_FakeConstraint()],
        )
        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        with patch("jarvis.tui.views.console", c):
            SpecView.render_spec_detail(spec)
        output = buf.getvalue()
        assert "Test Spec" in output
        assert "StepAlpha" in output
        assert "StepBeta" in output
        assert "must be fast" in output

    def test_render_spec_detail_no_constraints(self):
        from jarvis.tui.views import SpecView

        spec = _FakeSpec(steps=[_FakeStep("s1", "Only step")])
        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        with patch("jarvis.tui.views.console", c):
            SpecView.render_spec_detail(spec)
        output = buf.getvalue()
        assert "Only step" in output
        assert "Constraints" not in output

    def test_render_spec_detail_with_output(self):
        from jarvis.tui.views import SpecView

        spec = _FakeSpec(
            steps=[_FakeStep("s1", "Step 1", "completed", output="result data")]
        )
        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        with patch("jarvis.tui.views.console", c):
            SpecView.render_spec_detail(spec)
        output = buf.getvalue()
        assert "result data" in output

    def test_render_dag_tree(self):
        from jarvis.tui.views import SpecView

        spec = _FakeSpec(
            steps=[
                _FakeStep("s1", "Root", "completed"),
                _FakeStep("s2", "Child A", "executing", depends_on=["s1"]),
                _FakeStep("s3", "Child B", "pending", depends_on=["s1"]),
                _FakeStep("s4", "Grandchild", "pending", depends_on=["s2"]),
            ]
        )
        tree = SpecView.render_dag_tree(spec)
        assert isinstance(tree, Tree)

        # Render to string and verify structure
        buf = StringIO()
        c = Console(file=buf, force_terminal=True, width=120)
        c.print(tree)
        output = buf.getvalue()
        assert "Root" in output
        assert "Child A" in output
        assert "Grandchild" in output

    def test_render_dag_tree_no_steps(self):
        from jarvis.tui.views import SpecView

        spec = _FakeSpec(steps=[])
        tree = SpecView.render_dag_tree(spec)
        assert isinstance(tree, Tree)

    def test_status_icons_coverage(self):
        """All StepStatus values have an entry in STATUS_ICONS."""
        from jarvis.tui.views import SpecView
        from jarvis.models.streaming_spec import StepStatus

        for status in StepStatus:
            assert status.value in SpecView.STATUS_ICONS, (
                f"Missing STATUS_ICONS entry for {status.value}"
            )


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------


class TestImports:
    def test_tui_package_exports(self):
        from jarvis.tui import TUIApp, ChatView, SpecView, DashboardView

        assert TUIApp is not None
        assert ChatView is not None
        assert SpecView is not None
        assert DashboardView is not None
