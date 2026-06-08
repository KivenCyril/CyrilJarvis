from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class LogConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True


class AgentConfig(BaseModel):
    enabled_agents: list[str] = Field(
        default_factory=lambda: [
            "code-agent",
            "calendar-agent",
            "knowledge-agent",
            "comms-agent",
            "ops-agent",
        ]
    )
    default_model: str = "claude-sonnet-4-6"


class HookConfig(BaseModel):
    enabled: bool = True
    cron_check_interval: int = 60


class KnowledgeConfig(BaseModel):
    graph_backend: str = "in-memory"
    lightrag_endpoint: str = ""


class LLMConfig(BaseModel):
    default_model: str = "gpt-4o-mini"
    fallback_model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.7
    max_retries: int = 3
    timeout_seconds: int = 60
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SecurityConfig(BaseModel):
    sandbox_mode: str = "basic"
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(default_factory=list)
    secret_scanning: bool = True
    audit_logging: bool = True


class GatewayConfig(BaseModel):
    enabled_channels: list[str] = Field(
        default_factory=lambda: ["cli", "web", "api"]
    )
    rate_limit_per_minute: int = 30
    channels: dict[str, dict[str, Any]] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    storage_path: str = "~/.jarvis/memory"
    max_memories: int = 10000
    prune_interval_hours: int = 24
    prune_max_age_days: int = 90


class SkillConfig(BaseModel):
    skills_dir: str = "~/.jarvis/skills"
    auto_evolve: bool = True
    evolution_threshold_executions: int = 3


class MCPConfig(BaseModel):
    servers: list[dict[str, Any]] = Field(default_factory=list)
    auto_connect: bool = True


class ObservabilityConfig(BaseModel):
    tracing_enabled: bool = True
    trace_storage_path: str = "~/.jarvis/traces"
    metrics_enabled: bool = True


class Settings(BaseModel):
    app_name: str = "JARVIS"
    version: str = "0.2.0"
    specs_dir: str = "specs"
    log: LogConfig = Field(default_factory=LogConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    hooks: HookConfig = Field(default_factory=HookConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillConfig = Field(default_factory=SkillConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Settings:
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Settings:
        """Load settings from default locations or a specific path."""
        if config_path:
            return cls.from_yaml(config_path)

        candidates = [
            Path("jarvis.yaml"),
            Path("jarvis.yml"),
            Path.home() / ".jarvis" / "config.yaml",
        ]
        for path in candidates:
            if path.exists():
                return cls.from_yaml(path)

        return cls()


def setup_logging(config: LogConfig) -> None:
    import logging

    logging.basicConfig(level=config.level, format=config.format)
