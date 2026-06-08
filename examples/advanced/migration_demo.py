"""Migration Demo.

Demonstrates migrating from Hermes and OpenClaw platforms to JARVIS.
Shows the full migration workflow including:
- Source validation
- Agent/skill/workflow migration
- Data transformation
- Results reporting

Usage:
    python examples/advanced/migration_demo.py
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Migration Models
# ---------------------------------------------------------------------------

@dataclass
class MigrationItem:
    """A single item to be migrated."""
    source_path: str
    target_path: str
    item_type: str  # agent, workflow, config, skill, plugin, prompt, data
    status: str = "pending"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def migrate(self) -> bool:
        """Simulate migrating this item."""
        try:
            self.status = "migrated"
            return True
        except Exception as exc:
            self.status = "failed"
            self.error = str(exc)
            return False


@dataclass
class MigrationPlan:
    """A plan for migrating from one platform to JARVIS."""
    source_platform: str
    source_path: str
    items: list[MigrationItem] = field(default_factory=list)
    validated: bool = False
    validation_errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def migrated_count(self) -> int:
        return sum(1 for i in self.items if i.status == "migrated")

    @property
    def failed_count(self) -> int:
        return sum(1 for i in self.items if i.status == "failed")

    @property
    def success_rate(self) -> float:
        if not self.items:
            return 0.0
        return round(self.migrated_count / self.total * 100, 1)


class HermesMigrator:
    """Migrate from Hermes to JARVIS."""

    EXPECTED_FILES = ["config.yaml"]
    EXPECTED_DIRS = ["agents", "workflows"]

    def validate(self, source_path: str) -> tuple[bool, list[str]]:
        """Validate the source directory."""
        errors = []
        if not os.path.isdir(source_path):
            return False, [f"Directory not found: {source_path}"]

        for f in self.EXPECTED_FILES:
            if not os.path.isfile(os.path.join(source_path, f)):
                errors.append(f"Missing required file: {f}")

        for d in self.EXPECTED_DIRS:
            if not os.path.isdir(os.path.join(source_path, d)):
                errors.append(f"Missing required directory: {d}")

        return len(errors) == 0, errors

    def plan(self, source_path: str) -> MigrationPlan:
        """Create a migration plan."""
        plan = MigrationPlan(
            source_platform="hermes",
            source_path=source_path,
        )

        valid, errors = self.validate(source_path)
        plan.validated = valid
        plan.validation_errors = errors

        if not valid:
            return plan

        # Config
        config_path = os.path.join(source_path, "config.yaml")
        if os.path.isfile(config_path):
            plan.items.append(MigrationItem(
                source_path=config_path,
                target_path="config/jarvis.yaml",
                item_type="config",
            ))

        # Agents
        agents_dir = os.path.join(source_path, "agents")
        if os.path.isdir(agents_dir):
            for f in os.listdir(agents_dir):
                if f.endswith(".json"):
                    plan.items.append(MigrationItem(
                        source_path=os.path.join(agents_dir, f),
                        target_path=f"agents/{f}",
                        item_type="agent",
                    ))

        # Workflows
        wf_dir = os.path.join(source_path, "workflows")
        if os.path.isdir(wf_dir):
            for f in os.listdir(wf_dir):
                if f.endswith(".json"):
                    plan.items.append(MigrationItem(
                        source_path=os.path.join(wf_dir, f),
                        target_path=f"workflows/{f}",
                        item_type="workflow",
                    ))

        return plan

    def execute(self, plan: MigrationPlan, dry_run: bool = False) -> MigrationPlan:
        """Execute the migration plan."""
        print(f"\n{'='*50}")
        print(f"Migrating from Hermes ({plan.source_path})")
        print(f"Items to migrate: {plan.total}")
        print(f"Dry run: {dry_run}")
        print(f"{'='*50}\n")

        for item in plan.items:
            if dry_run:
                item.status = "dry_run"
                print(f"  [DRY] {item.item_type}: {item.source_path} -> {item.target_path}")
            else:
                success = item.migrate()
                status = "OK" if success else "FAIL"
                print(f"  [{status}] {item.item_type}: {os.path.basename(item.source_path)}")

        print(f"\nMigration {'preview' if dry_run else 'complete'}:")
        print(f"  Total: {plan.total}")
        print(f"  Migrated: {plan.migrated_count}")
        print(f"  Failed: {plan.failed_count}")
        print(f"  Success rate: {plan.success_rate}%")

        return plan


class OpenClawMigrator:
    """Migrate from OpenClaw to JARVIS."""

    EXPECTED_FILES = ["manifest.json"]
    EXPECTED_DIRS = ["skills", "plugins"]

    def validate(self, source_path: str) -> tuple[bool, list[str]]:
        errors = []
        if not os.path.isdir(source_path):
            return False, [f"Directory not found: {source_path}"]

        for f in self.EXPECTED_FILES:
            if not os.path.isfile(os.path.join(source_path, f)):
                errors.append(f"Missing: {f}")

        for d in self.EXPECTED_DIRS:
            if not os.path.isdir(os.path.join(source_path, d)):
                errors.append(f"Missing: {d}")

        return len(errors) == 0, errors

    def plan(self, source_path: str) -> MigrationPlan:
        plan = MigrationPlan(
            source_platform="openclaw",
            source_path=source_path,
        )

        valid, errors = self.validate(source_path)
        plan.validated = valid
        plan.validation_errors = errors

        if not valid:
            return plan

        # Manifest
        plan.items.append(MigrationItem(
            source_path=os.path.join(source_path, "manifest.json"),
            target_path="config/manifest.json",
            item_type="config",
        ))

        # Skills
        skills_dir = os.path.join(source_path, "skills")
        if os.path.isdir(skills_dir):
            for f in os.listdir(skills_dir):
                if f.endswith(".json"):
                    plan.items.append(MigrationItem(
                        source_path=os.path.join(skills_dir, f),
                        target_path=f"skills/{f}",
                        item_type="skill",
                    ))

        # Plugins
        plugins_dir = os.path.join(source_path, "plugins")
        if os.path.isdir(plugins_dir):
            for f in os.listdir(plugins_dir):
                if f.endswith(".json"):
                    plan.items.append(MigrationItem(
                        source_path=os.path.join(plugins_dir, f),
                        target_path=f"plugins/{f}",
                        item_type="plugin",
                    ))

        return plan

    def execute(self, plan: MigrationPlan, dry_run: bool = False) -> MigrationPlan:
        print(f"\n{'='*50}")
        print(f"Migrating from OpenClaw ({plan.source_path})")
        print(f"Items: {plan.total}")
        print(f"{'='*50}\n")

        for item in plan.items:
            if dry_run:
                item.status = "dry_run"
                print(f"  [DRY] {item.item_type}: {item.source_path}")
            else:
                item.migrate()
                print(f"  [OK] {item.item_type}: {os.path.basename(item.source_path)}")

        print(f"\nResult: {plan.migrated_count}/{plan.total} migrated")
        return plan


# ---------------------------------------------------------------------------
# Setup demo data
# ---------------------------------------------------------------------------

def setup_hermes_demo(base_dir: str) -> str:
    """Create a sample Hermes project structure."""
    path = os.path.join(base_dir, "hermes-project")
    os.makedirs(os.path.join(path, "agents"), exist_ok=True)
    os.makedirs(os.path.join(path, "workflows"), exist_ok=True)

    with open(os.path.join(path, "config.yaml"), "w") as f:
        json.dump({"version": "1.0", "name": "demo", "model": "gpt-4"}, f)

    for name in ["assistant", "coder", "reviewer"]:
        with open(os.path.join(path, "agents", f"{name}.json"), "w") as f:
            json.dump({"name": name, "type": "agent", "model": "gpt-4"}, f)

    for name in ["ci-pipeline", "deploy", "review-flow"]:
        with open(os.path.join(path, "workflows", f"{name}.json"), "w") as f:
            json.dump({"name": name, "steps": [{"name": "step1"}]}, f)

    return path


def setup_openclaw_demo(base_dir: str) -> str:
    """Create a sample OpenClaw project structure."""
    path = os.path.join(base_dir, "openclaw-project")
    os.makedirs(os.path.join(path, "skills"), exist_ok=True)
    os.makedirs(os.path.join(path, "plugins"), exist_ok=True)

    with open(os.path.join(path, "manifest.json"), "w") as f:
        json.dump({"name": "demo", "version": "2.0"}, f)

    for name in ["coding", "analysis", "writing", "testing"]:
        with open(os.path.join(path, "skills", f"{name}.json"), "w") as f:
            json.dump({"name": name, "version": "1.0"}, f)

    for name in ["github", "slack", "jira"]:
        with open(os.path.join(path, "plugins", f"{name}.json"), "w") as f:
            json.dump({"name": name, "api": f"https://api.{name}.com"}, f)

    return path


# ---------------------------------------------------------------------------
# Main Demo
# ---------------------------------------------------------------------------

def main():
    """Run the migration demo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up demo projects
        hermes_path = setup_hermes_demo(tmpdir)
        openclaw_path = setup_openclaw_demo(tmpdir)

        # Demo 1: Hermes migration
        print("=" * 60)
        print("DEMO: Hermes to JARVIS Migration")
        print("=" * 60)

        hermes_migrator = HermesMigrator()

        # Validate
        valid, errors = hermes_migrator.validate(hermes_path)
        print(f"\nValidation: {'PASS' if valid else 'FAIL'}")
        if errors:
            for e in errors:
                print(f"  - {e}")

        # Plan
        plan = hermes_migrator.plan(hermes_path)
        print(f"\nMigration plan: {plan.total} items")
        for item in plan.items:
            print(f"  {item.item_type}: {os.path.basename(item.source_path)} -> {item.target_path}")

        # Execute (dry run first)
        hermes_migrator.execute(plan, dry_run=True)

        # Execute for real
        plan2 = hermes_migrator.plan(hermes_path)
        hermes_migrator.execute(plan2, dry_run=False)

        # Demo 2: OpenClaw migration
        print("\n" + "=" * 60)
        print("DEMO: OpenClaw to JARVIS Migration")
        print("=" * 60)

        openclaw_migrator = OpenClawMigrator()
        plan = openclaw_migrator.plan(openclaw_path)
        print(f"\nMigration plan: {plan.total} items")
        openclaw_migrator.execute(plan, dry_run=False)

        # Demo 3: Invalid source
        print("\n" + "=" * 60)
        print("DEMO: Invalid Source Validation")
        print("=" * 60)

        valid, errors = hermes_migrator.validate("/nonexistent/path")
        print(f"\nValidation: {'PASS' if valid else 'FAIL'}")
        for e in errors:
            print(f"  - {e}")

    print("\n" + "=" * 60)
    print("Migration demos complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
