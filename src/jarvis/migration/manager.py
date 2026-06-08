"""Migration orchestrator — coordinate platform-specific migrators."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jarvis.migration.base import MigrationReport, MigrationStatus
from jarvis.migration.hermes import HermesMigrator
from jarvis.migration.openclaw import OpenClawMigrator

logger = logging.getLogger(__name__)


class MigrationManager:
    """Orchestrates migration from different platforms to JARVIS.

    Usage::

        mgr = MigrationManager()
        report = await mgr.migrate_from_hermes("~/hermes-agent")
        print(report.summary())
    """

    def __init__(self, output_dir: str = "~/.jarvis") -> None:
        self._output_dir = output_dir
        self._reports: list[MigrationReport] = []

    # ------------------------------------------------------------------
    # Migration entry points
    # ------------------------------------------------------------------

    async def migrate_from_hermes(self, hermes_dir: str) -> MigrationReport:
        """Run the Hermes Agent migrator."""
        migrator = HermesMigrator(hermes_dir, output_dir=self._output_dir)
        report = await migrator.migrate_all()
        self._reports.append(report)
        logger.info(
            "Hermes migration %s: %d/%d items",
            report.status.value,
            report.total_processed,
            report.total_items,
        )
        return report

    async def migrate_from_openclaw(self, openclaw_dir: str) -> MigrationReport:
        """Run the OpenClaw migrator."""
        migrator = OpenClawMigrator(openclaw_dir, output_dir=self._output_dir)
        report = await migrator.migrate_all()
        self._reports.append(report)
        logger.info(
            "OpenClaw migration %s: %d/%d items",
            report.status.value,
            report.total_processed,
            report.total_items,
        )
        return report

    # ------------------------------------------------------------------
    # Report access
    # ------------------------------------------------------------------

    def list_reports(self) -> list[MigrationReport]:
        """Return all reports generated in this manager's lifetime."""
        return list(self._reports)

    def get_latest_report(self) -> MigrationReport | None:
        """Return the most recent migration report, if any."""
        return self._reports[-1] if self._reports else None

    # ------------------------------------------------------------------
    # Pre-migration validation
    # ------------------------------------------------------------------

    async def validate_source(self, source_dir: str, platform: str) -> dict[str, Any]:
        """Check what can be migrated without actually migrating.

        Returns a dict describing each category and how many items were found.
        """
        source = Path(source_dir).expanduser().resolve()
        result: dict[str, Any] = {
            "platform": platform,
            "source_dir": str(source),
            "exists": source.is_dir(),
            "categories": {},
            "warnings": [],
        }

        if not source.is_dir():
            result["warnings"].append(f"Directory does not exist: {source}")
            return result

        if platform == "hermes":
            result["categories"] = self._validate_hermes(source)
        elif platform == "openclaw":
            result["categories"] = self._validate_openclaw(source)
        else:
            result["warnings"].append(f"Unknown platform: {platform}")

        return result

    @staticmethod
    def _validate_hermes(source: Path) -> dict[str, Any]:
        """Inspect a Hermes directory and report what is available."""
        cats: dict[str, Any] = {}

        soul = source / "SOUL.md"
        cats["soul"] = {"found": soul.exists(), "count": 1 if soul.exists() else 0}

        memories = source / "memories"
        if memories.is_dir():
            files = list(memories.glob("*.json"))
            cats["memories"] = {"found": True, "count": len(files)}
        else:
            cats["memories"] = {"found": False, "count": 0}

        skills = source / "skills"
        if skills.is_dir():
            files = list(skills.rglob("*.yaml"))
            cats["skills"] = {"found": True, "count": len(files)}
        else:
            cats["skills"] = {"found": False, "count": 0}

        config = source / "config.yaml"
        cats["config"] = {"found": config.exists(), "count": 1 if config.exists() else 0}

        convs = source / "conversations"
        if convs.is_dir():
            files = list(convs.glob("*.json"))
            cats["conversations"] = {"found": True, "count": len(files)}
        else:
            cats["conversations"] = {"found": False, "count": 0}

        return cats

    @staticmethod
    def _validate_openclaw(source: Path) -> dict[str, Any]:
        """Inspect an OpenClaw directory and report what is available."""
        cats: dict[str, Any] = {}

        for name, pattern in [
            ("channels", "*.yaml"),
            ("sessions", "*.json"),
            ("tools", "*.yaml"),
            ("skills", "*.yaml"),
        ]:
            subdir = source / name
            if subdir.is_dir():
                files = list(subdir.glob(pattern))
                cats[name] = {"found": True, "count": len(files)}
            else:
                cats[name] = {"found": False, "count": 0}

        config = source / "config.yaml"
        cats["config"] = {"found": config.exists(), "count": 1 if config.exists() else 0}

        return cats
