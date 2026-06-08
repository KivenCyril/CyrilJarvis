"""Migrate data from OpenClaw into JARVIS.

OpenClaw stores its data as:
- ``channels/`` — channel configuration YAML files
- ``sessions/`` — session data as JSON
- ``tools/`` — tool allowlist configurations
- ``skills/`` — Skill Hub skill definitions (YAML)
- ``config.yaml`` — global configuration
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from jarvis.migration.base import MigrationReport, MigrationStatus, MigrationStep

logger = logging.getLogger(__name__)


class OpenClawMigrator:
    """Migrate data from OpenClaw to JARVIS.

    Imports:
    - channels/ -> JARVIS Gateway channel configs
    - sessions/ -> JARVIS Session data
    - tools/ -> JARVIS tool allowlists / security config
    - skills/ -> JARVIS Skills
    - config.yaml -> JARVIS Settings
    """

    def __init__(self, openclaw_dir: str, output_dir: str = "~/.jarvis") -> None:
        self._openclaw_dir = Path(openclaw_dir).expanduser().resolve()
        self._output_dir = Path(output_dir).expanduser().resolve()
        self._report = MigrationReport(source="openclaw")

    @property
    def report(self) -> MigrationReport:
        return self._report

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def migrate_all(self) -> MigrationReport:
        """Run every migration step and return the aggregated report."""
        self._report.status = MigrationStatus.IN_PROGRESS
        await self._migrate_channels()
        await self._migrate_sessions()
        await self._migrate_tools()
        await self._migrate_skills()
        await self._migrate_config()

        if all(s.status == MigrationStatus.COMPLETED for s in self._report.steps):
            self._report.status = MigrationStatus.COMPLETED
        elif any(s.status == MigrationStatus.FAILED for s in self._report.steps):
            self._report.status = MigrationStatus.PARTIAL
        else:
            self._report.status = MigrationStatus.PARTIAL

        self._report.completed_at = datetime.now(timezone.utc)
        return self._report

    # ------------------------------------------------------------------
    # Step: channels/ -> JARVIS Gateway channel configs
    # ------------------------------------------------------------------

    async def _migrate_channels(self) -> None:
        """Convert OpenClaw channel configs to JARVIS gateway configuration."""
        step = MigrationStep(name="channels")
        t0 = time.monotonic()

        channels_dir = self._openclaw_dir / "channels"
        if channels_dir.exists():
            gateway_config: dict[str, Any] = {"enabled_channels": [], "channels": {}}

            for chan_file in sorted(channels_dir.glob("*.yaml")):
                step.items_total += 1
                try:
                    data = yaml.safe_load(chan_file.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        step.errors.append(f"{chan_file.name}: not a YAML mapping")
                        continue

                    channel_name = data.get("name", chan_file.stem)
                    gateway_config["enabled_channels"].append(channel_name)
                    gateway_config["channels"][channel_name] = {
                        "type": data.get("type", channel_name),
                        "enabled": data.get("enabled", True),
                        "webhook_url": data.get("webhook_url", ""),
                        "token": data.get("token", ""),
                    }
                    step.items_processed += 1
                except Exception as exc:
                    step.errors.append(f"{chan_file.name}: {exc}")

            if gateway_config["enabled_channels"]:
                output = self._output_dir / "gateway_channels.yaml"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    yaml.dump(gateway_config, default_flow_style=False),
                    encoding="utf-8",
                )

        step.status = (
            MigrationStatus.COMPLETED if not step.errors else MigrationStatus.PARTIAL
        )
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)

    # ------------------------------------------------------------------
    # Step: sessions/ -> JARVIS Sessions
    # ------------------------------------------------------------------

    async def _migrate_sessions(self) -> None:
        """Import OpenClaw session data as JARVIS sessions."""
        step = MigrationStep(name="sessions")
        t0 = time.monotonic()

        sessions_dir = self._openclaw_dir / "sessions"
        if sessions_dir.exists():
            from jarvis.session import SessionManager

            sm = SessionManager(
                storage_path=str(self._output_dir / "sessions")
            )

            for sess_file in sorted(sessions_dir.glob("*.json")):
                step.items_total += 1
                try:
                    data = json.loads(sess_file.read_text(encoding="utf-8"))
                    session = sm.create(
                        user_id=data.get("user_id", "openclaw-migration"),
                        channel=data.get("channel", "openclaw"),
                    )

                    messages = data.get("messages", [])
                    for msg in messages:
                        if isinstance(msg, dict):
                            session.add_message(
                                role=msg.get("role", "user"),
                                content=msg.get("content", str(msg)),
                                agent_name=msg.get("agent_name", ""),
                            )

                    step.items_processed += 1
                except Exception as exc:
                    step.errors.append(f"{sess_file.name}: {exc}")

        step.status = (
            MigrationStatus.COMPLETED if not step.errors else MigrationStatus.PARTIAL
        )
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)

    # ------------------------------------------------------------------
    # Step: tools/ -> JARVIS security / tool allowlists
    # ------------------------------------------------------------------

    async def _migrate_tools(self) -> None:
        """Convert OpenClaw tool allowlist to JARVIS security config."""
        step = MigrationStep(name="tools")
        t0 = time.monotonic()

        tools_dir = self._openclaw_dir / "tools"
        if tools_dir.exists():
            allowed_commands: list[str] = []
            blocked_commands: list[str] = []

            for tool_file in sorted(tools_dir.glob("*.yaml")):
                step.items_total += 1
                try:
                    data = yaml.safe_load(tool_file.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        step.errors.append(f"{tool_file.name}: not a YAML mapping")
                        continue

                    allowed = data.get("allowed", data.get("allowlist", []))
                    blocked = data.get("blocked", data.get("blocklist", []))
                    if isinstance(allowed, list):
                        allowed_commands.extend(allowed)
                    if isinstance(blocked, list):
                        blocked_commands.extend(blocked)
                    step.items_processed += 1
                except Exception as exc:
                    step.errors.append(f"{tool_file.name}: {exc}")

            if allowed_commands or blocked_commands:
                security_config = {
                    "security": {
                        "allowed_commands": sorted(set(allowed_commands)),
                        "blocked_commands": sorted(set(blocked_commands)),
                    }
                }
                output = self._output_dir / "security_tools.yaml"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    yaml.dump(security_config, default_flow_style=False),
                    encoding="utf-8",
                )

        step.status = (
            MigrationStatus.COMPLETED if not step.errors else MigrationStatus.PARTIAL
        )
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)

    # ------------------------------------------------------------------
    # Step: skills/ -> JARVIS Skills
    # ------------------------------------------------------------------

    async def _migrate_skills(self) -> None:
        """Convert OpenClaw Skill Hub skills to JARVIS Skill format."""
        step = MigrationStep(name="skills")
        t0 = time.monotonic()

        skills_dir = self._openclaw_dir / "skills"
        if skills_dir.exists():
            from jarvis.skills.base import Skill, SkillMetadata, SkillStep

            for skill_file in sorted(skills_dir.rglob("*.yaml")):
                step.items_total += 1
                try:
                    data = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        step.errors.append(f"{skill_file.name}: not a YAML mapping")
                        continue

                    # OpenClaw skills may nest metadata under a "metadata" key
                    meta = data.get("metadata", data)
                    spec = data.get("spec", data)

                    skill = Skill(
                        metadata=SkillMetadata(
                            name=meta.get("name", skill_file.stem),
                            description=meta.get("description", ""),
                            author="openclaw-migration",
                            tags=meta.get("tags", []),
                            domain=meta.get("domain", meta.get("category", "")),
                            version=meta.get("version", "1.0.0"),
                        ),
                        system_prompt=spec.get("system_prompt", ""),
                        steps=[
                            SkillStep(
                                order=i,
                                action=(
                                    s.get("action", str(s))
                                    if isinstance(s, dict)
                                    else str(s)
                                ),
                                tool=(
                                    s.get("tool") if isinstance(s, dict) else None
                                ),
                            )
                            for i, s in enumerate(spec.get("steps", []))
                        ],
                        constraints=spec.get("constraints", []),
                    )

                    output_dir = self._output_dir / "skills"
                    skill.save(output_dir)
                    step.items_processed += 1
                except Exception as exc:
                    step.errors.append(f"{skill_file.name}: {exc}")

        step.status = (
            MigrationStatus.COMPLETED if not step.errors else MigrationStatus.PARTIAL
        )
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)

    # ------------------------------------------------------------------
    # Step: config.yaml -> JARVIS settings
    # ------------------------------------------------------------------

    async def _migrate_config(self) -> None:
        """Map OpenClaw ``config.yaml`` to JARVIS settings."""
        step = MigrationStep(name="config", items_total=1)
        t0 = time.monotonic()

        config_path = self._openclaw_dir / "config.yaml"
        if config_path.exists():
            try:
                data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("config.yaml root is not a mapping")

                jarvis_config: dict[str, Any] = {
                    "agents": {
                        "default_model": data.get(
                            "default_model", data.get("model", "gpt-4o-mini")
                        ),
                        "enabled_agents": data.get("enabled_agents", []),
                    },
                    "server": {
                        "host": data.get("host", "127.0.0.1"),
                        "port": data.get("port", 8000),
                    },
                    "mcp": {
                        "servers": data.get("mcp_servers", []),
                    },
                }

                output = self._output_dir / "jarvis.migrated.yaml"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    yaml.dump(jarvis_config, default_flow_style=False),
                    encoding="utf-8",
                )

                step.items_processed = 1
                step.status = MigrationStatus.COMPLETED
            except Exception as exc:
                step.errors.append(str(exc))
                step.status = MigrationStatus.FAILED
        else:
            step.items_total = 0
            step.status = MigrationStatus.COMPLETED
            self._report.warnings.append("No config.yaml found")

        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)
