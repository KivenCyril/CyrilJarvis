"""Advanced migration tests.

Tests Hermes and OpenClaw migration with various data types,
validation for different directory structures, and edge cases.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Migration Data Structures
# ---------------------------------------------------------------------------

@dataclass
class MigrationItem:
    source_path: str
    target_path: str
    item_type: str  # agent, workflow, config, skill, plugin
    status: str = "pending"  # pending, migrated, skipped, failed
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def mark_migrated(self) -> None:
        self.status = "migrated"

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.error = error

    def mark_skipped(self, reason: str) -> None:
        self.status = "skipped"
        self.error = reason


@dataclass
class MigrationResult:
    source_platform: str
    source_path: str
    items: list[MigrationItem] = field(default_factory=list)

    @property
    def migrated_count(self) -> int:
        return sum(1 for i in self.items if i.status == "migrated")

    @property
    def skipped_count(self) -> int:
        return sum(1 for i in self.items if i.status == "skipped")

    @property
    def failed_count(self) -> int:
        return sum(1 for i in self.items if i.status == "failed")

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def success_rate(self) -> float:
        if not self.items:
            return 0.0
        return self.migrated_count / self.total_count

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source_platform,
            "total": self.total_count,
            "migrated": self.migrated_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
            "success_rate": round(self.success_rate * 100, 1),
        }


@dataclass
class MigrationValidator:
    """Validate source directories for migration readiness."""

    required_files: list[str] = field(default_factory=list)
    required_dirs: list[str] = field(default_factory=list)
    optional_files: list[str] = field(default_factory=list)

    def validate(self, source_path: str) -> tuple[bool, list[str]]:
        errors = []
        if not os.path.isdir(source_path):
            return False, [f"Source directory not found: {source_path}"]

        for f in self.required_files:
            full = os.path.join(source_path, f)
            if not os.path.isfile(full):
                errors.append(f"Required file missing: {f}")

        for d in self.required_dirs:
            full = os.path.join(source_path, d)
            if not os.path.isdir(full):
                errors.append(f"Required directory missing: {d}")

        return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Migration Simulators
# ---------------------------------------------------------------------------

def _create_hermes_structure(base_dir: str) -> None:
    """Create a realistic Hermes directory structure."""
    os.makedirs(os.path.join(base_dir, "agents"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "workflows"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "config"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "data"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "plugins"), exist_ok=True)

    # Config file
    config = {
        "version": "1.0",
        "name": "hermes-project",
        "agents": ["assistant", "coder", "reviewer"],
        "default_model": "gpt-4",
        "max_tokens": 4096,
    }
    with open(os.path.join(base_dir, "config.yaml"), "w") as f:
        json.dump(config, f)

    # Agent definitions
    for agent_name in ["assistant", "coder", "reviewer"]:
        agent = {
            "name": agent_name,
            "type": "hermes-agent",
            "model": "gpt-4",
            "system_prompt": f"You are a {agent_name}.",
            "tools": ["search", "code"],
            "temperature": 0.7,
        }
        with open(os.path.join(base_dir, "agents", f"{agent_name}.json"), "w") as f:
            json.dump(agent, f)

    # Workflow definitions
    for wf_name in ["review", "deploy", "test"]:
        wf = {
            "name": wf_name,
            "steps": [
                {"name": "init", "agent": "assistant"},
                {"name": "execute", "agent": "coder"},
                {"name": "verify", "agent": "reviewer"},
            ],
        }
        with open(os.path.join(base_dir, "workflows", f"{wf_name}.json"), "w") as f:
            json.dump(wf, f)

    # Data files
    with open(os.path.join(base_dir, "data", "knowledge.json"), "w") as f:
        json.dump({"entries": [{"text": "fact 1"}, {"text": "fact 2"}]}, f)


def _create_openclaw_structure(base_dir: str) -> None:
    """Create a realistic OpenClaw directory structure."""
    os.makedirs(os.path.join(base_dir, "skills"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "plugins"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "prompts"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "models"), exist_ok=True)

    # Manifest
    manifest = {
        "name": "openclaw-project",
        "version": "2.0",
        "skills": ["coding", "analysis", "writing"],
        "plugins": ["github", "slack"],
        "settings": {"max_context": 8192, "temperature": 0.5},
    }
    with open(os.path.join(base_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    # Skills
    for skill_name in ["coding", "analysis", "writing"]:
        skill = {
            "name": skill_name,
            "version": "1.0",
            "description": f"Skill for {skill_name}",
            "prompts": [f"Do {skill_name}"],
            "tools": ["execute"],
        }
        with open(os.path.join(base_dir, "skills", f"{skill_name}.json"), "w") as f:
            json.dump(skill, f)

    # Plugins
    for plugin_name in ["github", "slack"]:
        plugin = {
            "name": plugin_name,
            "version": "1.0",
            "api_base": f"https://api.{plugin_name}.com",
            "auth_type": "oauth2",
        }
        with open(os.path.join(base_dir, "plugins", f"{plugin_name}.json"), "w") as f:
            json.dump(plugin, f)

    # Prompts
    for prompt_name in ["system", "task", "review"]:
        with open(os.path.join(base_dir, "prompts", f"{prompt_name}.txt"), "w") as f:
            f.write(f"This is the {prompt_name} prompt template.")


def simulate_hermes_migration(source_path: str) -> MigrationResult:
    """Simulate migrating from Hermes to JARVIS."""
    result = MigrationResult(source_platform="hermes", source_path=source_path)

    # Migrate config
    config_path = os.path.join(source_path, "config.yaml")
    if os.path.isfile(config_path):
        item = MigrationItem(
            source_path=config_path,
            target_path="config/jarvis.yaml",
            item_type="config",
        )
        item.mark_migrated()
        result.items.append(item)

    # Migrate agents
    agents_dir = os.path.join(source_path, "agents")
    if os.path.isdir(agents_dir):
        for fname in os.listdir(agents_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(agents_dir, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    item = MigrationItem(
                        source_path=fpath,
                        target_path=f"agents/{fname}",
                        item_type="agent",
                        metadata={"original_name": data.get("name", "")},
                    )
                    item.mark_migrated()
                    result.items.append(item)
                except (json.JSONDecodeError, IOError) as exc:
                    item = MigrationItem(
                        source_path=fpath,
                        target_path=f"agents/{fname}",
                        item_type="agent",
                    )
                    item.mark_failed(str(exc))
                    result.items.append(item)

    # Migrate workflows
    wf_dir = os.path.join(source_path, "workflows")
    if os.path.isdir(wf_dir):
        for fname in os.listdir(wf_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(wf_dir, fname)
                item = MigrationItem(
                    source_path=fpath,
                    target_path=f"workflows/{fname}",
                    item_type="workflow",
                )
                item.mark_migrated()
                result.items.append(item)

    # Migrate data
    data_dir = os.path.join(source_path, "data")
    if os.path.isdir(data_dir):
        for fname in os.listdir(data_dir):
            fpath = os.path.join(data_dir, fname)
            item = MigrationItem(
                source_path=fpath,
                target_path=f"data/{fname}",
                item_type="data",
            )
            item.mark_migrated()
            result.items.append(item)

    return result


def simulate_openclaw_migration(source_path: str) -> MigrationResult:
    """Simulate migrating from OpenClaw to JARVIS."""
    result = MigrationResult(source_platform="openclaw", source_path=source_path)

    # Migrate manifest
    manifest_path = os.path.join(source_path, "manifest.json")
    if os.path.isfile(manifest_path):
        item = MigrationItem(
            source_path=manifest_path,
            target_path="config/manifest.json",
            item_type="config",
        )
        item.mark_migrated()
        result.items.append(item)

    # Migrate skills
    skills_dir = os.path.join(source_path, "skills")
    if os.path.isdir(skills_dir):
        for fname in os.listdir(skills_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(skills_dir, fname)
                item = MigrationItem(
                    source_path=fpath,
                    target_path=f"skills/{fname}",
                    item_type="skill",
                )
                item.mark_migrated()
                result.items.append(item)

    # Migrate plugins
    plugins_dir = os.path.join(source_path, "plugins")
    if os.path.isdir(plugins_dir):
        for fname in os.listdir(plugins_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(plugins_dir, fname)
                item = MigrationItem(
                    source_path=fpath,
                    target_path=f"plugins/{fname}",
                    item_type="plugin",
                )
                item.mark_migrated()
                result.items.append(item)

    # Migrate prompts
    prompts_dir = os.path.join(source_path, "prompts")
    if os.path.isdir(prompts_dir):
        for fname in os.listdir(prompts_dir):
            fpath = os.path.join(prompts_dir, fname)
            item = MigrationItem(
                source_path=fpath,
                target_path=f"prompts/{fname}",
                item_type="prompt",
            )
            item.mark_migrated()
            result.items.append(item)

    return result


# ---------------------------------------------------------------------------
# Tests: MigrationItem
# ---------------------------------------------------------------------------

class TestMigrationItem:
    def test_create_item(self):
        item = MigrationItem(
            source_path="/src/a.json",
            target_path="/dst/a.json",
            item_type="agent",
        )
        assert item.status == "pending"
        assert item.error is None

    def test_mark_migrated(self):
        item = MigrationItem(source_path="a", target_path="b", item_type="config")
        item.mark_migrated()
        assert item.status == "migrated"

    def test_mark_failed(self):
        item = MigrationItem(source_path="a", target_path="b", item_type="agent")
        item.mark_failed("file corrupt")
        assert item.status == "failed"
        assert item.error == "file corrupt"

    def test_mark_skipped(self):
        item = MigrationItem(source_path="a", target_path="b", item_type="workflow")
        item.mark_skipped("already exists")
        assert item.status == "skipped"
        assert item.error == "already exists"


# ---------------------------------------------------------------------------
# Tests: MigrationResult
# ---------------------------------------------------------------------------

class TestMigrationResult:
    def test_empty_result(self):
        result = MigrationResult(source_platform="test", source_path="/tmp")
        assert result.total_count == 0
        assert result.success_rate == 0.0

    def test_all_migrated(self):
        result = MigrationResult(source_platform="hermes", source_path="/tmp")
        for i in range(5):
            item = MigrationItem(source_path=f"s{i}", target_path=f"t{i}", item_type="agent")
            item.mark_migrated()
            result.items.append(item)
        assert result.migrated_count == 5
        assert result.success_rate == 1.0

    def test_mixed_results(self):
        result = MigrationResult(source_platform="openclaw", source_path="/tmp")
        items = [
            ("migrated", None),
            ("migrated", None),
            ("failed", "error"),
            ("skipped", "exists"),
        ]
        for status, error in items:
            item = MigrationItem(source_path="s", target_path="t", item_type="skill")
            if status == "migrated":
                item.mark_migrated()
            elif status == "failed":
                item.mark_failed(error)
            else:
                item.mark_skipped(error)
            result.items.append(item)
        assert result.migrated_count == 2
        assert result.failed_count == 1
        assert result.skipped_count == 1
        assert result.success_rate == 0.5

    def test_summary(self):
        result = MigrationResult(source_platform="hermes", source_path="/tmp")
        item = MigrationItem(source_path="s", target_path="t", item_type="config")
        item.mark_migrated()
        result.items.append(item)
        summary = result.summary()
        assert summary["source"] == "hermes"
        assert summary["total"] == 1
        assert summary["success_rate"] == 100.0


# ---------------------------------------------------------------------------
# Tests: MigrationValidator
# ---------------------------------------------------------------------------

class TestMigrationValidator:
    def test_validate_valid_hermes(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        validator = MigrationValidator(
            required_files=["config.yaml"],
            required_dirs=["agents", "workflows"],
        )
        valid, errors = validator.validate(str(tmp_path))
        assert valid is True
        assert errors == []

    def test_validate_missing_file(self, tmp_path):
        os.makedirs(tmp_path / "agents")
        validator = MigrationValidator(
            required_files=["config.yaml"],
            required_dirs=["agents"],
        )
        valid, errors = validator.validate(str(tmp_path))
        assert valid is False
        assert any("config.yaml" in e for e in errors)

    def test_validate_missing_dir(self, tmp_path):
        (tmp_path / "config.yaml").write_text("{}")
        validator = MigrationValidator(
            required_files=["config.yaml"],
            required_dirs=["agents"],
        )
        valid, errors = validator.validate(str(tmp_path))
        assert valid is False
        assert any("agents" in e for e in errors)

    def test_validate_nonexistent_path(self):
        validator = MigrationValidator()
        valid, errors = validator.validate("/nonexistent/path")
        assert valid is False
        assert any("not found" in e for e in errors)

    def test_validate_valid_openclaw(self, tmp_path):
        _create_openclaw_structure(str(tmp_path))
        validator = MigrationValidator(
            required_files=["manifest.json"],
            required_dirs=["skills", "plugins"],
        )
        valid, errors = validator.validate(str(tmp_path))
        assert valid is True


# ---------------------------------------------------------------------------
# Tests: Full Hermes Migration
# ---------------------------------------------------------------------------

class TestHermesMigration:
    def test_full_migration(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        result = simulate_hermes_migration(str(tmp_path))
        assert result.source_platform == "hermes"
        assert result.migrated_count >= 7  # config + 3 agents + 3 workflows
        assert result.failed_count == 0

    def test_migration_includes_config(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        result = simulate_hermes_migration(str(tmp_path))
        config_items = [i for i in result.items if i.item_type == "config"]
        assert len(config_items) == 1
        assert config_items[0].status == "migrated"

    def test_migration_includes_agents(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        result = simulate_hermes_migration(str(tmp_path))
        agent_items = [i for i in result.items if i.item_type == "agent"]
        assert len(agent_items) == 3

    def test_migration_includes_workflows(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        result = simulate_hermes_migration(str(tmp_path))
        wf_items = [i for i in result.items if i.item_type == "workflow"]
        assert len(wf_items) == 3

    def test_migration_includes_data(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        result = simulate_hermes_migration(str(tmp_path))
        data_items = [i for i in result.items if i.item_type == "data"]
        assert len(data_items) >= 1

    def test_empty_source(self, tmp_path):
        result = simulate_hermes_migration(str(tmp_path))
        assert result.total_count == 0

    def test_corrupt_agent_file(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        # Corrupt an agent file
        corrupt_path = os.path.join(str(tmp_path), "agents", "corrupt.json")
        with open(corrupt_path, "w") as f:
            f.write("{invalid json")
        result = simulate_hermes_migration(str(tmp_path))
        failed = [i for i in result.items if i.status == "failed"]
        assert len(failed) == 1
        assert "corrupt" in failed[0].source_path


# ---------------------------------------------------------------------------
# Tests: Full OpenClaw Migration
# ---------------------------------------------------------------------------

class TestOpenClawMigration:
    def test_full_migration(self, tmp_path):
        _create_openclaw_structure(str(tmp_path))
        result = simulate_openclaw_migration(str(tmp_path))
        assert result.source_platform == "openclaw"
        assert result.migrated_count >= 8  # manifest + 3 skills + 2 plugins + 3 prompts
        assert result.failed_count == 0

    def test_migration_includes_manifest(self, tmp_path):
        _create_openclaw_structure(str(tmp_path))
        result = simulate_openclaw_migration(str(tmp_path))
        config_items = [i for i in result.items if i.item_type == "config"]
        assert len(config_items) == 1

    def test_migration_includes_skills(self, tmp_path):
        _create_openclaw_structure(str(tmp_path))
        result = simulate_openclaw_migration(str(tmp_path))
        skill_items = [i for i in result.items if i.item_type == "skill"]
        assert len(skill_items) == 3

    def test_migration_includes_plugins(self, tmp_path):
        _create_openclaw_structure(str(tmp_path))
        result = simulate_openclaw_migration(str(tmp_path))
        plugin_items = [i for i in result.items if i.item_type == "plugin"]
        assert len(plugin_items) == 2

    def test_migration_includes_prompts(self, tmp_path):
        _create_openclaw_structure(str(tmp_path))
        result = simulate_openclaw_migration(str(tmp_path))
        prompt_items = [i for i in result.items if i.item_type == "prompt"]
        assert len(prompt_items) == 3

    def test_empty_source(self, tmp_path):
        result = simulate_openclaw_migration(str(tmp_path))
        assert result.total_count == 0

    def test_summary_output(self, tmp_path):
        _create_openclaw_structure(str(tmp_path))
        result = simulate_openclaw_migration(str(tmp_path))
        summary = result.summary()
        assert summary["source"] == "openclaw"
        assert summary["success_rate"] == 100.0


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------

class TestMigrationEdgeCases:
    def test_empty_directory(self, tmp_path):
        result = simulate_hermes_migration(str(tmp_path))
        assert result.total_count == 0
        assert result.success_rate == 0.0

    def test_nonexistent_directory(self):
        result = simulate_hermes_migration("/nonexistent/path")
        assert result.total_count == 0

    def test_migration_with_nested_dirs(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        # Add nested structure
        nested = tmp_path / "agents" / "subdir"
        nested.mkdir()
        (nested / "nested_agent.json").write_text(
            json.dumps({"name": "nested", "type": "agent"})
        )
        result = simulate_hermes_migration(str(tmp_path))
        # Should still work (nested not picked up by default)
        assert result.migrated_count >= 7

    def test_migration_with_non_json_files(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        # Add non-JSON file in agents dir
        (tmp_path / "agents" / "readme.txt").write_text("not a json file")
        result = simulate_hermes_migration(str(tmp_path))
        # Should skip non-json files
        assert result.failed_count == 0

    def test_migration_with_empty_json(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        (tmp_path / "agents" / "empty.json").write_text("{}")
        result = simulate_hermes_migration(str(tmp_path))
        empty_items = [
            i for i in result.items
            if "empty.json" in i.source_path
        ]
        assert len(empty_items) == 1
        assert empty_items[0].status == "migrated"

    def test_mixed_platform_dir(self, tmp_path):
        """A directory containing both Hermes and OpenClaw files."""
        _create_hermes_structure(str(tmp_path))
        # Add OpenClaw manifest alongside
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "mixed"}))
        hermes_result = simulate_hermes_migration(str(tmp_path))
        openclaw_result = simulate_openclaw_migration(str(tmp_path))
        # Both should work independently
        assert hermes_result.migrated_count >= 1
        assert openclaw_result.migrated_count >= 1

    def test_large_agent_file(self, tmp_path):
        _create_hermes_structure(str(tmp_path))
        large_data = {
            "name": "large-agent",
            "type": "agent",
            "prompts": [f"prompt {i}" for i in range(1000)],
        }
        with open(tmp_path / "agents" / "large.json", "w") as f:
            json.dump(large_data, f)
        result = simulate_hermes_migration(str(tmp_path))
        large_items = [i for i in result.items if "large.json" in i.source_path]
        assert len(large_items) == 1
        assert large_items[0].status == "migrated"
