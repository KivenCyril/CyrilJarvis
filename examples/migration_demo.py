#!/usr/bin/env python3
"""migration_demo.py -- Migration system demonstration.

Shows JARVIS's migration capabilities: validating Hermes and OpenClaw
source directories, running migrations, and viewing reports.

Run:
    python examples/migration_demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.migration.manager import MigrationManager
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


def create_mock_hermes_dir(base: str) -> str:
    """Create a mock Hermes agent directory for demo purposes."""
    hermes_dir = Path(base) / "hermes-agent"
    hermes_dir.mkdir(parents=True)

    # SOUL.md
    (hermes_dir / "SOUL.md").write_text(
        "# Hermes Agent\nI am a helpful assistant with memory and skills.\n",
        encoding="utf-8",
    )

    # config.yaml
    (hermes_dir / "config.yaml").write_text(
        "model: gpt-4\ntemperature: 0.7\nmax_tokens: 2048\n",
        encoding="utf-8",
    )

    # Memories
    memories_dir = hermes_dir / "memories"
    memories_dir.mkdir()
    for i in range(3):
        (memories_dir / f"memory_{i}.json").write_text(
            json.dumps({"content": f"Memory {i}", "importance": 0.5 + i * 0.1}),
            encoding="utf-8",
        )

    # Skills
    skills_dir = hermes_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "deploy.yaml").write_text(
        "name: deploy\nsteps:\n  - action: build\n  - action: deploy\n",
        encoding="utf-8",
    )

    # Conversations
    convs_dir = hermes_dir / "conversations"
    convs_dir.mkdir()
    (convs_dir / "conv_1.json").write_text(
        json.dumps([{"role": "user", "content": "Hello"}]),
        encoding="utf-8",
    )

    return str(hermes_dir)


def create_mock_openclaw_dir(base: str) -> str:
    """Create a mock OpenClaw directory for demo purposes."""
    oc_dir = Path(base) / "openclaw-project"
    oc_dir.mkdir(parents=True)

    # config.yaml
    (oc_dir / "config.yaml").write_text(
        "channels:\n  - cli\n  - web\n",
        encoding="utf-8",
    )

    # Channels
    channels_dir = oc_dir / "channels"
    channels_dir.mkdir()
    (channels_dir / "cli.yaml").write_text("type: cli\n", encoding="utf-8")
    (channels_dir / "web.yaml").write_text("type: web\n", encoding="utf-8")

    # Sessions
    sessions_dir = oc_dir / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "sess_1.json").write_text(
        json.dumps({"id": "sess_1", "messages": []}),
        encoding="utf-8",
    )

    # Tools
    tools_dir = oc_dir / "tools"
    tools_dir.mkdir()
    (tools_dir / "shell.yaml").write_text("name: shell\ntype: builtin\n", encoding="utf-8")

    return str(oc_dir)


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Migration Demo[/bold cyan]",
                        subtitle="Hermes & OpenClaw Migration"))

    tmpdir = tempfile.mkdtemp(prefix="jarvis_migration_")

    # -------------------------------------------------------------------
    # 1. Set up mock source directories
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Creating mock source directories...[/bold]")
    hermes_dir = create_mock_hermes_dir(tmpdir)
    openclaw_dir = create_mock_openclaw_dir(tmpdir)
    console.print(f"   Hermes: {hermes_dir}")
    console.print(f"   OpenClaw: {openclaw_dir}")

    output_dir = f"{tmpdir}/jarvis_output"
    manager = MigrationManager(output_dir=output_dir)

    # -------------------------------------------------------------------
    # 2. Validate Hermes source
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Validating Hermes source:[/bold]")
    hermes_val = await manager.validate_source(hermes_dir, "hermes")

    table = Table(title="Hermes Validation")
    table.add_column("Category", style="cyan")
    table.add_column("Found", style="bold")
    table.add_column("Count", justify="right", style="yellow")

    for cat, info in hermes_val.get("categories", {}).items():
        found = info.get("found", False)
        style = "green" if found else "red"
        table.add_row(cat, f"[{style}]{found}[/{style}]", str(info.get("count", 0)))
    console.print(table)

    if hermes_val.get("warnings"):
        for w in hermes_val["warnings"]:
            console.print(f"   [yellow]Warning: {w}[/yellow]")

    # -------------------------------------------------------------------
    # 3. Validate OpenClaw source
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Validating OpenClaw source:[/bold]")
    oc_val = await manager.validate_source(openclaw_dir, "openclaw")

    table = Table(title="OpenClaw Validation")
    table.add_column("Category", style="cyan")
    table.add_column("Found", style="bold")
    table.add_column("Count", justify="right", style="yellow")

    for cat, info in oc_val.get("categories", {}).items():
        found = info.get("found", False)
        style = "green" if found else "red"
        table.add_row(cat, f"[{style}]{found}[/{style}]", str(info.get("count", 0)))
    console.print(table)

    # -------------------------------------------------------------------
    # 4. Validate non-existent directory
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Validating non-existent directory:[/bold]")
    bad_val = await manager.validate_source("/tmp/does_not_exist_xyz", "hermes")
    console.print(f"   Exists: {bad_val['exists']}")
    console.print(f"   Warnings: {bad_val['warnings']}")

    # -------------------------------------------------------------------
    # 5. Run Hermes migration
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Running Hermes migration:[/bold]")
    try:
        hermes_report = await manager.migrate_from_hermes(hermes_dir)
        console.print(f"   Status: {hermes_report.status.value}")
        console.print(f"   Items: {hermes_report.total_processed}/{hermes_report.total_items}")
        if hasattr(hermes_report, "summary"):
            console.print(f"   Summary: {hermes_report.summary()[:200]}")
    except Exception as e:
        console.print(f"   [yellow]Migration result: {e}[/yellow]")

    # -------------------------------------------------------------------
    # 6. Run OpenClaw migration
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Running OpenClaw migration:[/bold]")
    try:
        oc_report = await manager.migrate_from_openclaw(openclaw_dir)
        console.print(f"   Status: {oc_report.status.value}")
        console.print(f"   Items: {oc_report.total_processed}/{oc_report.total_items}")
    except Exception as e:
        console.print(f"   [yellow]Migration result: {e}[/yellow]")

    # -------------------------------------------------------------------
    # 7. View all reports
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Migration reports:[/bold]")
    reports = manager.list_reports()
    console.print(f"   Total reports: {len(reports)}")
    for i, report in enumerate(reports, 1):
        console.print(f"   {i}. {report.status.value}: "
                      f"{report.total_processed}/{report.total_items} items")

    latest = manager.get_latest_report()
    if latest:
        console.print(f"   Latest: {latest.status.value}")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
