"""CLI command tests using typer.testing.CliRunner.

Tests all command groups produce output and handle errors.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from jarvis.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: Mock JarvisApp
# ---------------------------------------------------------------------------

def _mock_jarvis_app():
    """Create a mocked JarvisApp for testing CLI without real init."""
    mock_app = MagicMock()

    # Registry
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.card.description = "A test agent"
    mock_agent.card.skills = ["test"]
    mock_agent.card.domain = "testing"
    mock_agent.status.value = "active"
    mock_agent.card.can_delegate = False
    mock_agent.card.version = "1.0"
    mock_app.registry.list_agents.return_value = [mock_agent]
    mock_app.registry.__len__ = MagicMock(return_value=1)

    # Spec engine
    mock_spec = MagicMock()
    mock_spec.id = "spec-001"
    mock_spec.name = "Test Spec"
    mock_spec.intent = "test"
    mock_spec.status.value = "planning"
    mock_spec.progress = "0/3"
    mock_spec.constraints = []
    mock_spec.steps = []
    mock_spec.changelog = []
    mock_spec.model_dump.return_value = {"id": "spec-001", "status": "planning"}
    mock_app.spec_engine.create = AsyncMock(return_value=mock_spec)
    mock_app.spec_engine.list_specs.return_value = [mock_spec]
    mock_app.spec_engine.get.return_value = mock_spec

    # Executor
    mock_result = MagicMock()
    mock_result.id = "spec-001"
    mock_result.status.value = "completed"
    mock_result.model_dump.return_value = {"id": "spec-001", "status": "completed"}
    mock_app.executor.execute_spec = AsyncMock(return_value=mock_result)

    # Orchestrator
    orch_result = MagicMock()
    orch_result.success = True
    orch_result.agent_name = "test-agent"
    orch_result.output = "Test response"
    orch_result.error = None
    mock_app.orchestrator.handle = AsyncMock(return_value=orch_result)

    # Tools
    mock_tool = MagicMock()
    mock_tool.name = "echo"
    mock_tool.description = "Echo input"
    mock_app._tool_registry.list_tools.return_value = [mock_tool]

    # Spec registry
    mock_app.spec_registry.list_specs.return_value = []

    # Initialize
    mock_app.initialize = AsyncMock()

    return mock_app


# ---------------------------------------------------------------------------
# Tests: System Info
# ---------------------------------------------------------------------------

class TestSystemCommands:
    def test_info_command(self):
        async def _fake_init():
            return _mock_jarvis_app()
        with patch("jarvis.cli.main._init_app", side_effect=_fake_init):
            result = runner.invoke(app, ["info"])
            assert result.exit_code == 0
            assert "JARVIS" in result.output

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "JARVIS" in result.output


# ---------------------------------------------------------------------------
# Tests: Spec Commands
# ---------------------------------------------------------------------------

class TestSpecCommands:
    def test_spec_help(self):
        result = runner.invoke(app, ["spec", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output
        assert "run" in result.output

    def test_spec_create(self):
        async def _fake_init():
            return _mock_jarvis_app()
        with patch("jarvis.cli.main._init_app", side_effect=_fake_init):
            result = runner.invoke(app, ["spec", "create", "test task"])
            assert result.exit_code == 0

    def test_spec_list(self):
        async def _fake_init():
            return _mock_jarvis_app()
        with patch("jarvis.cli.main._init_app", side_effect=_fake_init):
            result = runner.invoke(app, ["spec", "list"])
            assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Tests: Agent Commands
# ---------------------------------------------------------------------------

class TestAgentCommands:
    def test_agent_help(self):
        result = runner.invoke(app, ["agent", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "chat" in result.output
        assert "route" in result.output

    def test_agent_list(self):
        async def _fake_init():
            return _mock_jarvis_app()
        with patch("jarvis.cli.main._init_app", side_effect=_fake_init):
            result = runner.invoke(app, ["agent", "list"])
            assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Tests: Tool Commands
# ---------------------------------------------------------------------------

class TestToolCommands:
    def test_tool_help(self):
        result = runner.invoke(app, ["tool", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "run" in result.output

    def test_tool_list(self):
        async def _fake_init():
            return _mock_jarvis_app()
        with patch("jarvis.cli.main._init_app", side_effect=_fake_init):
            result = runner.invoke(app, ["tool", "list"])
            assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Tests: Memory Commands
# ---------------------------------------------------------------------------

class TestMemoryCommands:
    def test_memory_help(self):
        result = runner.invoke(app, ["memory", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "search" in result.output
        assert "list" in result.output


# ---------------------------------------------------------------------------
# Tests: Knowledge Commands
# ---------------------------------------------------------------------------

class TestKnowledgeCommands:
    def test_knowledge_help(self):
        result = runner.invoke(app, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "stats" in result.output
        assert "extract" in result.output
        assert "query" in result.output


# ---------------------------------------------------------------------------
# Tests: Skill Commands
# ---------------------------------------------------------------------------

class TestSkillCommands:
    def test_skill_help(self):
        result = runner.invoke(app, ["skill", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output


# ---------------------------------------------------------------------------
# Tests: Server Commands
# ---------------------------------------------------------------------------

class TestServerCommands:
    def test_server_help(self):
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output


# ---------------------------------------------------------------------------
# Tests: Workflow Commands
# ---------------------------------------------------------------------------

class TestWorkflowCommands:
    def test_workflow_help(self):
        result = runner.invoke(app, ["workflow", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output
        assert "run" in result.output
        assert "templates" in result.output


# ---------------------------------------------------------------------------
# Tests: Event Commands
# ---------------------------------------------------------------------------

class TestEventCommands:
    def test_event_help(self):
        result = runner.invoke(app, ["event", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "publish" in result.output


# ---------------------------------------------------------------------------
# Tests: Notification Commands
# ---------------------------------------------------------------------------

class TestNotificationCommands:
    def test_notification_help(self):
        result = runner.invoke(app, ["notification", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "send" in result.output


# ---------------------------------------------------------------------------
# Tests: Migration Commands
# ---------------------------------------------------------------------------

class TestMigrationCommands:
    def test_migration_help(self):
        result = runner.invoke(app, ["migration", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
        assert "run" in result.output

    def test_migration_validate_nonexistent(self):
        result = runner.invoke(app, ["migration", "validate", "hermes", "/nonexistent"])
        assert result.exit_code == 0
        assert "FAIL" in result.output

    def test_migration_validate_empty_dir(self, tmp_path):
        result = runner.invoke(app, ["migration", "validate", "hermes", str(tmp_path)])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Tests: Diagnostics Commands
# ---------------------------------------------------------------------------

class TestDiagnosticCommands:
    def test_diagnose_help(self):
        result = runner.invoke(app, ["diagnose", "--help"])
        assert result.exit_code == 0

    def test_benchmark_help(self):
        result = runner.invoke(app, ["benchmark", "--help"])
        assert result.exit_code == 0
