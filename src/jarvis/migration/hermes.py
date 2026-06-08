"""Migrate data from Hermes Agent into JARVIS.

Hermes Agent stores its data as:
- ``SOUL.md`` — user personality description
- ``memories/`` — JSON memory entries
- ``skills/`` — YAML skill definitions
- ``config.yaml`` — agent configuration
- ``conversations/`` — JSON conversation logs

This migrator reads each of those artefacts and converts them into the
corresponding JARVIS data model, persisting them under ``~/.jarvis/``.
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


class HermesMigrator:
    """Migrate data from Hermes Agent to JARVIS.

    Imports:
    - SOUL.md -> User Profile
    - memories/ -> JARVIS Memory
    - skills/ -> JARVIS Skills
    - config.yaml -> JARVIS Settings
    - conversation history -> Session data
    """

    def __init__(self, hermes_dir: str, output_dir: str = "~/.jarvis") -> None:
        self._hermes_dir = Path(hermes_dir).expanduser().resolve()
        self._output_dir = Path(output_dir).expanduser().resolve()
        self._report = MigrationReport(source="hermes")

    @property
    def report(self) -> MigrationReport:
        return self._report

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def migrate_all(self) -> MigrationReport:
        """Run every migration step and return the aggregated report."""
        self._report.status = MigrationStatus.IN_PROGRESS
        await self._migrate_soul()
        await self._migrate_memories()
        await self._migrate_skills()
        await self._migrate_config()
        await self._migrate_conversations()

        # Determine overall status
        if all(s.status == MigrationStatus.COMPLETED for s in self._report.steps):
            self._report.status = MigrationStatus.COMPLETED
        elif any(s.status == MigrationStatus.FAILED for s in self._report.steps):
            self._report.status = MigrationStatus.PARTIAL
        else:
            self._report.status = MigrationStatus.PARTIAL

        self._report.completed_at = datetime.now(timezone.utc)
        return self._report

    # ------------------------------------------------------------------
    # Step: SOUL.md -> UserProfile
    # ------------------------------------------------------------------

    async def _migrate_soul(self) -> None:
        """Convert ``SOUL.md`` to a :class:`UserProfile`."""
        step = MigrationStep(name="soul_to_profile", items_total=1)
        t0 = time.monotonic()

        soul_path = self._hermes_dir / "SOUL.md"
        if soul_path.exists():
            try:
                content = soul_path.read_text(encoding="utf-8")
                profile_data = self._parse_soul_md(content)

                from jarvis.user.profile import UserPreferences, UserProfile

                profile = UserProfile(
                    name=profile_data.get("name", ""),
                    soul_description=content,
                    goals=profile_data.get("goals", []),
                    preferences=UserPreferences(
                        communication_style=profile_data.get("style", "concise"),
                        code_language=profile_data.get("language", ""),
                    ),
                )

                output_path = self._output_dir / "user" / "profile.json"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                profile.save(output_path)

                step.items_processed = 1
                step.status = MigrationStatus.COMPLETED
            except Exception as exc:
                step.errors.append(f"SOUL.md: {exc}")
                step.status = MigrationStatus.FAILED
        else:
            step.items_total = 0
            step.status = MigrationStatus.COMPLETED
            self._report.warnings.append("No SOUL.md found in Hermes directory")

        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)

    # ------------------------------------------------------------------
    # Step: memories/ -> JARVIS Memory
    # ------------------------------------------------------------------

    async def _migrate_memories(self) -> None:
        """Convert Hermes memory JSON files to JARVIS memory entries."""
        step = MigrationStep(name="memories")
        t0 = time.monotonic()

        memories_dir = self._hermes_dir / "memories"
        if memories_dir.exists():
            from jarvis.memory import MemoryManager, MemoryType

            storage = str(self._output_dir / "memory")
            mm = MemoryManager(storage_path=storage)

            for mem_file in sorted(memories_dir.glob("*.json")):
                step.items_total += 1
                try:
                    data = json.loads(mem_file.read_text(encoding="utf-8"))
                    content = data.get("content", data.get("text", str(data)))
                    mem_type = self._map_memory_type(data.get("type", "general"))

                    await mm.add(
                        content,
                        mem_type,
                        metadata={
                            "migrated_from": "hermes",
                            "original_file": mem_file.name,
                        },
                    )
                    step.items_processed += 1
                except Exception as exc:
                    step.errors.append(f"{mem_file.name}: {exc}")

            mm.save()

        step.status = (
            MigrationStatus.COMPLETED if not step.errors else MigrationStatus.PARTIAL
        )
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)

    # ------------------------------------------------------------------
    # Step: skills/ -> JARVIS Skills
    # ------------------------------------------------------------------

    async def _migrate_skills(self) -> None:
        """Convert Hermes skill YAML files to JARVIS Skill objects."""
        step = MigrationStep(name="skills")
        t0 = time.monotonic()

        skills_dir = self._hermes_dir / "skills"
        if skills_dir.exists():
            from jarvis.skills.base import Skill, SkillMetadata, SkillStep

            for skill_file in sorted(skills_dir.rglob("*.yaml")):
                step.items_total += 1
                try:
                    data = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        step.errors.append(f"{skill_file.name}: not a YAML mapping")
                        continue

                    skill = Skill(
                        metadata=SkillMetadata(
                            name=data.get("name", skill_file.stem),
                            description=data.get("description", ""),
                            author="hermes-migration",
                            tags=data.get("tags", []),
                            domain=data.get("category", ""),
                        ),
                        system_prompt=data.get(
                            "system_prompt", data.get("prompt", "")
                        ),
                        steps=[
                            SkillStep(
                                order=i,
                                action=s.get("action", s.get("step", str(s)))
                                if isinstance(s, dict)
                                else str(s),
                            )
                            for i, s in enumerate(data.get("steps", []))
                        ],
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
        """Map Hermes ``config.yaml`` to JARVIS settings file."""
        step = MigrationStep(name="config", items_total=1)
        t0 = time.monotonic()

        config_path = self._hermes_dir / "config.yaml"
        if config_path.exists():
            try:
                data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("config.yaml root is not a mapping")

                jarvis_config: dict[str, Any] = {
                    "agents": {
                        "default_model": data.get(
                            "model", data.get("default_model", "gpt-4o-mini")
                        ),
                    },
                    "server": {
                        "port": data.get("port", 8000),
                    },
                    "llm": {
                        "default_model": data.get(
                            "model", data.get("default_model", "gpt-4o-mini")
                        ),
                        "temperature": data.get("temperature", 0.7),
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

    # ------------------------------------------------------------------
    # Step: conversations/ -> JARVIS sessions
    # ------------------------------------------------------------------

    async def _migrate_conversations(self) -> None:
        """Import conversation history as :class:`Session` objects."""
        step = MigrationStep(name="conversations")
        t0 = time.monotonic()

        conv_dir = self._hermes_dir / "conversations"
        if conv_dir.exists():
            from jarvis.session import SessionManager

            sm = SessionManager(
                storage_path=str(self._output_dir / "sessions")
            )

            for conv_file in sorted(conv_dir.glob("*.json")):
                step.items_total += 1
                try:
                    data = json.loads(conv_file.read_text(encoding="utf-8"))
                    session = sm.create(
                        user_id="hermes-migration", channel="hermes"
                    )

                    messages = data.get("messages", data if isinstance(data, list) else [])
                    for msg in messages:
                        if isinstance(msg, dict):
                            session.add_message(
                                role=msg.get("role", "user"),
                                content=msg.get("content", str(msg)),
                                agent_name=msg.get("agent", ""),
                            )

                    step.items_processed += 1
                except Exception as exc:
                    step.errors.append(f"{conv_file.name}: {exc}")

        step.status = (
            MigrationStatus.COMPLETED if not step.errors else MigrationStatus.PARTIAL
        )
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        self._report.steps.append(step)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_soul_md(content: str) -> dict[str, Any]:
        """Parse ``SOUL.md`` into structured profile data.

        Extracts:
        - ``name`` from the first ``# Heading``
        - ``goals`` from bullet items under ``## Goals``
        - ``style`` from ``## Style`` section (defaults to ``concise``)
        - ``language`` from mentions of ``python`` / ``typescript``
        """
        result: dict[str, Any] = {
            "name": "",
            "goals": [],
            "style": "concise",
            "language": "",
        }
        lines = content.split("\n")
        current_section = ""

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("# ") and not stripped.startswith("## "):
                result["name"] = stripped[2:].strip()
            elif stripped.startswith("## "):
                current_section = stripped[3:].strip().lower()
            elif stripped.startswith("- "):
                if current_section == "goals":
                    result["goals"].append(stripped[2:].strip())
            elif "python" in stripped.lower() and not result["language"]:
                result["language"] = "python"
            elif "typescript" in stripped.lower() and not result["language"]:
                result["language"] = "typescript"

            # Style detection
            if current_section == "style":
                for style in ("verbose", "detailed", "casual", "formal", "concise"):
                    if style in stripped.lower():
                        result["style"] = style

        return result

    @staticmethod
    def _map_memory_type(hermes_type: str) -> Any:
        """Map a Hermes memory type string to :class:`MemoryType`."""
        from jarvis.memory import MemoryType

        mapping = {
            "general": MemoryType.FACT,
            "fact": MemoryType.FACT,
            "preference": MemoryType.PREFERENCE,
            "skill": MemoryType.SKILL_LEARNED,
            "conversation": MemoryType.CONVERSATION,
        }
        return mapping.get(hermes_type, MemoryType.FACT)
