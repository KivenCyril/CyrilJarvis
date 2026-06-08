"""Tests for the jarvis.migration package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from jarvis.migration.base import MigrationReport, MigrationStatus, MigrationStep
from jarvis.migration.hermes import HermesMigrator
from jarvis.migration.openclaw import OpenClawMigrator
from jarvis.migration.manager import MigrationManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# MigrationStep tests
# ---------------------------------------------------------------------------


class TestMigrationStep:
    def test_default_status(self):
        step = MigrationStep(name="test")
        assert step.status == MigrationStatus.PENDING
        assert step.items_processed == 0
        assert step.items_total == 0
        assert step.errors == []

    def test_success_rate_empty(self):
        step = MigrationStep(name="test")
        assert step.success_rate == 1.0

    def test_success_rate_partial(self):
        step = MigrationStep(name="test", items_processed=3, items_total=10)
        assert step.success_rate == pytest.approx(0.3)

    def test_success_rate_full(self):
        step = MigrationStep(name="test", items_processed=5, items_total=5)
        assert step.success_rate == 1.0


# ---------------------------------------------------------------------------
# MigrationReport tests
# ---------------------------------------------------------------------------


class TestMigrationReport:
    def test_default_state(self):
        report = MigrationReport(source="test")
        assert report.status == MigrationStatus.PENDING
        assert report.source == "test"
        assert report.completed_at is None
        assert report.steps == []
        assert report.warnings == []

    def test_success_rate_no_steps(self):
        report = MigrationReport(source="test")
        assert report.success_rate == 1.0

    def test_success_rate_with_steps(self):
        report = MigrationReport(
            source="test",
            steps=[
                MigrationStep(name="a", items_processed=5, items_total=10),
                MigrationStep(name="b", items_processed=10, items_total=10),
            ],
        )
        assert report.success_rate == pytest.approx(0.75)

    def test_total_errors(self):
        report = MigrationReport(
            source="test",
            steps=[
                MigrationStep(name="a", errors=["e1", "e2"]),
                MigrationStep(name="b", errors=["e3"]),
            ],
        )
        assert report.total_errors == 3

    def test_total_items(self):
        report = MigrationReport(
            source="test",
            steps=[
                MigrationStep(name="a", items_total=5, items_processed=3),
                MigrationStep(name="b", items_total=10, items_processed=10),
            ],
        )
        assert report.total_items == 15
        assert report.total_processed == 13

    def test_summary_output(self):
        report = MigrationReport(
            source="hermes",
            status=MigrationStatus.COMPLETED,
            steps=[
                MigrationStep(
                    name="memories",
                    items_processed=5,
                    items_total=5,
                    status=MigrationStatus.COMPLETED,
                ),
            ],
            warnings=["No config.yaml found"],
        )
        summary = report.summary()
        assert "hermes" in summary
        assert "completed" in summary
        assert "5/5" in summary
        assert "Warnings: 1" in summary

    def test_summary_with_errors_truncated(self):
        report = MigrationReport(
            source="test",
            steps=[
                MigrationStep(
                    name="step1",
                    items_total=5,
                    items_processed=1,
                    errors=["e1", "e2", "e3", "e4", "e5"],
                    status=MigrationStatus.PARTIAL,
                ),
            ],
        )
        summary = report.summary()
        assert "e1" in summary
        assert "e3" in summary
        assert "2 more" in summary

    def test_to_dict(self):
        report = MigrationReport(source="test")
        d = report.to_dict()
        assert d["source"] == "test"
        assert isinstance(d["started_at"], str)


# ---------------------------------------------------------------------------
# HermesMigrator tests
# ---------------------------------------------------------------------------


class TestHermesMigrator:
    @pytest.mark.asyncio
    async def test_migrate_empty_dir(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        hermes_dir.mkdir()
        output_dir = tmp_path / "output"
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        assert report.source == "hermes"
        assert all(s.status in (MigrationStatus.COMPLETED, MigrationStatus.PARTIAL) for s in report.steps)
        assert "No SOUL.md found" in report.warnings[0]

    @pytest.mark.asyncio
    async def test_migrate_soul_md(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        hermes_dir.mkdir()
        output_dir = tmp_path / "output"
        soul_content = "# John Doe\n\n## Goals\n- Build amazing software\n- Learn Rust\n\n## Style\nI prefer concise communication\n\n## Languages\nI mainly use python for my projects\n"
        _write_text(hermes_dir / "SOUL.md", soul_content)
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        soul_step = next(s for s in report.steps if s.name == "soul_to_profile")
        assert soul_step.status == MigrationStatus.COMPLETED
        assert soul_step.items_processed == 1
        profile_path = output_dir / "user" / "profile.json"
        assert profile_path.exists()
        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
        assert profile_data["name"] == "John Doe"
        assert "Build amazing software" in profile_data["goals"]
        assert profile_data["preferences"]["code_language"] == "python"

    @pytest.mark.asyncio
    async def test_migrate_memories(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        output_dir = tmp_path / "output"
        mem_dir = hermes_dir / "memories"
        _write_json(mem_dir / "mem1.json", {"content": "User likes dark mode", "type": "preference"})
        _write_json(mem_dir / "mem2.json", {"text": "Python is great", "type": "general"})
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        mem_step = next(s for s in report.steps if s.name == "memories")
        assert mem_step.items_total == 2
        assert mem_step.items_processed == 2
        assert mem_step.status == MigrationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_migrate_memories_with_bad_file(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        output_dir = tmp_path / "output"
        mem_dir = hermes_dir / "memories"
        _write_json(mem_dir / "good.json", {"content": "ok", "type": "general"})
        _write_text(mem_dir / "bad.json", "NOT VALID JSON {{{")
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        mem_step = next(s for s in report.steps if s.name == "memories")
        assert mem_step.items_total == 2
        assert mem_step.items_processed == 1
        assert mem_step.status == MigrationStatus.PARTIAL
        assert len(mem_step.errors) == 1

    @pytest.mark.asyncio
    async def test_migrate_skills(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        output_dir = tmp_path / "output"
        skills_dir = hermes_dir / "skills"
        _write_yaml(skills_dir / "code_review.yaml", {
            "name": "code-review", "description": "Review code for quality",
            "tags": ["code", "review"], "category": "development",
            "system_prompt": "You are a code reviewer.",
            "steps": [{"action": "Read the code"}, {"action": "Check for bugs"}],
        })
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        skill_step = next(s for s in report.steps if s.name == "skills")
        assert skill_step.items_processed == 1
        assert skill_step.status == MigrationStatus.COMPLETED
        assert (output_dir / "skills" / "code-review.yaml").exists()

    @pytest.mark.asyncio
    async def test_migrate_config(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        output_dir = tmp_path / "output"
        _write_yaml(hermes_dir / "config.yaml", {"model": "gpt-4", "port": 9000, "temperature": 0.5})
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        config_step = next(s for s in report.steps if s.name == "config")
        assert config_step.status == MigrationStatus.COMPLETED
        migrated = yaml.safe_load((output_dir / "jarvis.migrated.yaml").read_text(encoding="utf-8"))
        assert migrated["agents"]["default_model"] == "gpt-4"
        assert migrated["server"]["port"] == 9000

    @pytest.mark.asyncio
    async def test_migrate_conversations(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        output_dir = tmp_path / "output"
        conv_dir = hermes_dir / "conversations"
        _write_json(conv_dir / "conv1.json", {
            "messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]
        })
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        conv_step = next(s for s in report.steps if s.name == "conversations")
        assert conv_step.items_processed == 1
        assert conv_step.status == MigrationStatus.COMPLETED

    def test_parse_soul_md_extracts_name(self):
        result = HermesMigrator._parse_soul_md("# Alice\n\nSome description")
        assert result["name"] == "Alice"

    def test_parse_soul_md_extracts_goals(self):
        result = HermesMigrator._parse_soul_md("# Test\n## Goals\n- Goal A\n- Goal B\n## Other\n- Not a goal")
        assert result["goals"] == ["Goal A", "Goal B"]

    def test_parse_soul_md_detects_language(self):
        result = HermesMigrator._parse_soul_md("# Dev\nI love TypeScript")
        assert result["language"] == "typescript"

    def test_map_memory_type_known(self):
        from jarvis.memory import MemoryType
        assert HermesMigrator._map_memory_type("preference") == MemoryType.PREFERENCE
        assert HermesMigrator._map_memory_type("conversation") == MemoryType.CONVERSATION
        assert HermesMigrator._map_memory_type("skill") == MemoryType.SKILL_LEARNED

    def test_map_memory_type_unknown(self):
        from jarvis.memory import MemoryType
        assert HermesMigrator._map_memory_type("unknown_type") == MemoryType.FACT

    @pytest.mark.asyncio
    async def test_full_migration(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        output_dir = tmp_path / "output"
        _write_text(hermes_dir / "SOUL.md", "# Test User\n## Goals\n- Be awesome")
        _write_json(hermes_dir / "memories" / "m1.json", {"content": "fact1", "type": "general"})
        _write_yaml(hermes_dir / "skills" / "s1.yaml", {"name": "skill-one", "steps": [{"action": "do stuff"}]})
        _write_yaml(hermes_dir / "config.yaml", {"model": "claude-3"})
        _write_json(hermes_dir / "conversations" / "c1.json", {"messages": [{"role": "user", "content": "test"}]})
        migrator = HermesMigrator(str(hermes_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        assert report.status in (MigrationStatus.COMPLETED, MigrationStatus.PARTIAL)
        assert len(report.steps) == 5
        assert report.total_errors == 0


# ---------------------------------------------------------------------------
# OpenClawMigrator tests
# ---------------------------------------------------------------------------


class TestOpenClawMigrator:
    @pytest.mark.asyncio
    async def test_migrate_empty_dir(self, tmp_path: Path):
        oc_dir = tmp_path / "openclaw"
        oc_dir.mkdir()
        output_dir = tmp_path / "output"
        migrator = OpenClawMigrator(str(oc_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        assert report.source == "openclaw"
        assert len(report.steps) == 5

    @pytest.mark.asyncio
    async def test_migrate_channels(self, tmp_path: Path):
        oc_dir = tmp_path / "openclaw"
        output_dir = tmp_path / "output"
        _write_yaml(oc_dir / "channels" / "slack.yaml", {
            "name": "slack", "type": "slack", "enabled": True, "webhook_url": "https://hooks.slack.com/x",
        })
        migrator = OpenClawMigrator(str(oc_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        chan_step = next(s for s in report.steps if s.name == "channels")
        assert chan_step.items_processed == 1
        assert (output_dir / "gateway_channels.yaml").exists()

    @pytest.mark.asyncio
    async def test_migrate_sessions(self, tmp_path: Path):
        oc_dir = tmp_path / "openclaw"
        output_dir = tmp_path / "output"
        _write_json(oc_dir / "sessions" / "s1.json", {
            "user_id": "u1", "channel": "web",
            "messages": [{"role": "user", "content": "Hello OpenClaw"}],
        })
        migrator = OpenClawMigrator(str(oc_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        sess_step = next(s for s in report.steps if s.name == "sessions")
        assert sess_step.items_processed == 1

    @pytest.mark.asyncio
    async def test_migrate_tools(self, tmp_path: Path):
        oc_dir = tmp_path / "openclaw"
        output_dir = tmp_path / "output"
        _write_yaml(oc_dir / "tools" / "defaults.yaml", {"allowed": ["ls", "cat", "grep"], "blocked": ["rm", "sudo"]})
        migrator = OpenClawMigrator(str(oc_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        tools_step = next(s for s in report.steps if s.name == "tools")
        assert tools_step.items_processed == 1
        security_yaml = yaml.safe_load((output_dir / "security_tools.yaml").read_text(encoding="utf-8"))
        assert "ls" in security_yaml["security"]["allowed_commands"]
        assert "sudo" in security_yaml["security"]["blocked_commands"]

    @pytest.mark.asyncio
    async def test_migrate_skills(self, tmp_path: Path):
        oc_dir = tmp_path / "openclaw"
        output_dir = tmp_path / "output"
        _write_yaml(oc_dir / "skills" / "search.yaml", {
            "metadata": {"name": "web-search", "description": "Search the web", "tags": ["search"]},
            "spec": {"system_prompt": "You search the web.", "steps": [{"action": "Query the search engine"}]},
        })
        migrator = OpenClawMigrator(str(oc_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        skill_step = next(s for s in report.steps if s.name == "skills")
        assert skill_step.items_processed == 1
        assert (output_dir / "skills" / "web-search.yaml").exists()

    @pytest.mark.asyncio
    async def test_migrate_config(self, tmp_path: Path):
        oc_dir = tmp_path / "openclaw"
        output_dir = tmp_path / "output"
        _write_yaml(oc_dir / "config.yaml", {
            "default_model": "gpt-4-turbo", "port": 3000, "host": "0.0.0.0",
            "mcp_servers": [{"name": "fs", "command": "fs-server"}],
        })
        migrator = OpenClawMigrator(str(oc_dir), output_dir=str(output_dir))
        report = await migrator.migrate_all()
        config_step = next(s for s in report.steps if s.name == "config")
        assert config_step.status == MigrationStatus.COMPLETED
        migrated = yaml.safe_load((output_dir / "jarvis.migrated.yaml").read_text(encoding="utf-8"))
        assert migrated["agents"]["default_model"] == "gpt-4-turbo"
        assert migrated["server"]["port"] == 3000


# ---------------------------------------------------------------------------
# MigrationManager tests
# ---------------------------------------------------------------------------


class TestMigrationManager:
    @pytest.mark.asyncio
    async def test_migrate_from_hermes(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        hermes_dir.mkdir()
        output_dir = tmp_path / "output"
        mgr = MigrationManager(output_dir=str(output_dir))
        report = await mgr.migrate_from_hermes(str(hermes_dir))
        assert report.source == "hermes"
        assert mgr.get_latest_report() is report

    @pytest.mark.asyncio
    async def test_migrate_from_openclaw(self, tmp_path: Path):
        oc_dir = tmp_path / "openclaw"
        oc_dir.mkdir()
        output_dir = tmp_path / "output"
        mgr = MigrationManager(output_dir=str(output_dir))
        report = await mgr.migrate_from_openclaw(str(oc_dir))
        assert report.source == "openclaw"

    @pytest.mark.asyncio
    async def test_list_reports(self, tmp_path: Path):
        hermes_dir = tmp_path / "h"
        hermes_dir.mkdir()
        oc_dir = tmp_path / "oc"
        oc_dir.mkdir()
        output_dir = tmp_path / "output"
        mgr = MigrationManager(output_dir=str(output_dir))
        await mgr.migrate_from_hermes(str(hermes_dir))
        await mgr.migrate_from_openclaw(str(oc_dir))
        assert len(mgr.list_reports()) == 2

    def test_get_latest_report_empty(self):
        mgr = MigrationManager()
        assert mgr.get_latest_report() is None

    @pytest.mark.asyncio
    async def test_validate_source_hermes(self, tmp_path: Path):
        hermes_dir = tmp_path / "hermes"
        (hermes_dir / "memories").mkdir(parents=True)
        _write_text(hermes_dir / "SOUL.md", "# Test")
        _write_json(hermes_dir / "memories" / "m1.json", {"content": "x"})
        mgr = MigrationManager()
        result = await mgr.validate_source(str(hermes_dir), "hermes")
        assert result["exists"] is True
        assert result["categories"]["soul"]["found"] is True
        assert result["categories"]["memories"]["count"] == 1

    @pytest.mark.asyncio
    async def test_validate_source_nonexistent(self, tmp_path: Path):
        mgr = MigrationManager()
        result = await mgr.validate_source(str(tmp_path / "nope"), "hermes")
        assert result["exists"] is False
        assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_validate_source_openclaw(self, tmp_path: Path):
        oc_dir = tmp_path / "oc"
        (oc_dir / "channels").mkdir(parents=True)
        _write_yaml(oc_dir / "channels" / "web.yaml", {"name": "web"})
        mgr = MigrationManager()
        result = await mgr.validate_source(str(oc_dir), "openclaw")
        assert result["categories"]["channels"]["count"] == 1

    @pytest.mark.asyncio
    async def test_validate_source_unknown_platform(self, tmp_path: Path):
        mgr = MigrationManager()
        result = await mgr.validate_source(str(tmp_path), "unknown_platform")
        assert any("Unknown platform" in w for w in result["warnings"])
