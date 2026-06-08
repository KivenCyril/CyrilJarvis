"""Tests for the jarvis.config.settings module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from jarvis.config.settings import (
    Settings,
    LogConfig,
    ServerConfig,
    AgentConfig,
    HookConfig,
    KnowledgeConfig,
    LLMConfig,
    SecurityConfig,
    GatewayConfig,
    MemoryConfig,
    SkillConfig,
    MCPConfig,
    ObservabilityConfig,
)


class TestSettingsDefaults:
    def test_default_settings(self):
        s = Settings()
        assert s.app_name == "JARVIS"
        assert s.version == "0.2.0"
        assert s.specs_dir == "specs"

    def test_log_defaults(self):
        s = Settings()
        assert s.log.level == "INFO"
        assert "%(asctime)s" in s.log.format

    def test_server_defaults(self):
        s = Settings()
        assert s.server.host == "127.0.0.1"
        assert s.server.port == 8000

    def test_agents_defaults(self):
        s = Settings()
        assert "code-agent" in s.agents.enabled_agents
        assert s.agents.default_model == "claude-sonnet-4-6"

    def test_hooks_defaults(self):
        s = Settings()
        assert s.hooks.enabled is True
        assert s.hooks.cron_check_interval == 60

    def test_knowledge_defaults(self):
        s = Settings()
        assert s.knowledge.graph_backend == "in-memory"

    def test_llm_defaults(self):
        s = Settings()
        assert s.llm.default_model == "gpt-4o-mini"
        assert s.llm.fallback_model == "gpt-4o-mini"
        assert s.llm.max_tokens == 4096
        assert s.llm.temperature == 0.7
        assert s.llm.max_retries == 3
        assert s.llm.timeout_seconds == 60
        assert s.llm.providers == {}

    def test_security_defaults(self):
        s = Settings()
        assert s.security.sandbox_mode == "basic"
        assert s.security.secret_scanning is True
        assert s.security.audit_logging is True

    def test_gateway_defaults(self):
        s = Settings()
        assert "cli" in s.gateway.enabled_channels
        assert "web" in s.gateway.enabled_channels
        assert "api" in s.gateway.enabled_channels
        assert s.gateway.rate_limit_per_minute == 30

    def test_memory_defaults(self):
        s = Settings()
        assert s.memory.storage_path == "~/.jarvis/memory"
        assert s.memory.max_memories == 10000
        assert s.memory.prune_interval_hours == 24
        assert s.memory.prune_max_age_days == 90

    def test_skills_defaults(self):
        s = Settings()
        assert s.skills.skills_dir == "~/.jarvis/skills"
        assert s.skills.auto_evolve is True
        assert s.skills.evolution_threshold_executions == 3

    def test_mcp_defaults(self):
        s = Settings()
        assert s.mcp.servers == []
        assert s.mcp.auto_connect is True

    def test_observability_defaults(self):
        s = Settings()
        assert s.observability.tracing_enabled is True
        assert s.observability.trace_storage_path == "~/.jarvis/traces"
        assert s.observability.metrics_enabled is True


class TestSettingsFromYaml:
    def test_from_yaml_with_overrides(self, tmp_path: Path):
        config_data = {
            "app_name": "TestBot",
            "version": "9.9.9",
            "llm": {
                "default_model": "claude-opus-4-6",
                "temperature": 0.1,
            },
            "security": {
                "sandbox_mode": "strict",
                "secret_scanning": False,
            },
            "gateway": {
                "rate_limit_per_minute": 100,
            },
        }
        yaml_path = tmp_path / "test_config.yaml"
        yaml_path.write_text(yaml.dump(config_data))

        s = Settings.from_yaml(yaml_path)
        assert s.app_name == "TestBot"
        assert s.version == "9.9.9"
        assert s.llm.default_model == "claude-opus-4-6"
        assert s.llm.temperature == 0.1
        # Non-overridden fields keep defaults
        assert s.llm.max_tokens == 4096
        assert s.security.sandbox_mode == "strict"
        assert s.security.secret_scanning is False
        assert s.gateway.rate_limit_per_minute == 100

    def test_from_yaml_nonexistent_returns_defaults(self):
        s = Settings.from_yaml("/nonexistent/path/config.yaml")
        assert s.app_name == "JARVIS"
        assert s.version == "0.2.0"

    def test_from_yaml_empty_file(self, tmp_path: Path):
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("")
        s = Settings.from_yaml(yaml_path)
        assert s.app_name == "JARVIS"


class TestSettingsLoad:
    def test_load_with_explicit_path(self, tmp_path: Path):
        config_data = {"app_name": "Loaded"}
        yaml_path = tmp_path / "explicit.yaml"
        yaml_path.write_text(yaml.dump(config_data))

        s = Settings.load(config_path=yaml_path)
        assert s.app_name == "Loaded"

    def test_load_fallback_to_defaults(self, monkeypatch, tmp_path: Path):
        """When no config files exist, load() returns defaults."""
        monkeypatch.chdir(tmp_path)
        s = Settings.load()
        assert s.app_name == "JARVIS"
        assert s.version == "0.2.0"
