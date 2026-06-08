#!/usr/bin/env python3
"""notifications_demo.py -- Notification system demonstration.

Shows JARVIS's notification manager: sending to different channels,
priority levels, quiet hours, rate limiting, and history.

Run:
    python examples/notifications_demo.py
"""

from __future__ import annotations

import asyncio
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.notifications.manager import NotificationManager
    from jarvis.notifications.models import (
        NotificationChannel,
        NotificationPriority,
    )
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Notifications Demo[/bold cyan]",
                        subtitle="Multi-Channel, Priority, Rate Limiting"))

    manager = NotificationManager(rate_limit=10)

    # -------------------------------------------------------------------
    # 1. Send notifications to different channels
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Sending notifications:[/bold]")

    # Console notification
    n1 = await manager.notify(
        title="Spec Completed",
        body="Auth API spec finished with 4/4 steps completed.",
        priority=NotificationPriority.NORMAL,
        channel=NotificationChannel.CONSOLE,
        source="spec_engine",
        category="spec_completed",
    )
    console.print(f"   Sent: {n1.title} (status={n1.status.value})")

    # Log notification
    n2 = await manager.notify(
        title="Agent Error",
        body="Code agent failed on task: timeout exceeded.",
        priority=NotificationPriority.HIGH,
        channel=NotificationChannel.LOG,
        source="orchestrator",
        category="agent_error",
    )
    console.print(f"   Sent: {n2.title} (status={n2.status.value})")

    # Low priority
    n3 = await manager.notify(
        title="Skill Evolved",
        body="deploy-fastapi skill evolved from v1.0.0 to v1.1.0.",
        priority=NotificationPriority.LOW,
        channel=NotificationChannel.LOG,
        source="skill_evolver",
        category="skill_evolved",
    )
    console.print(f"   Sent: {n3.title} (status={n3.status.value})")

    # -------------------------------------------------------------------
    # 2. Priority levels
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Priority levels:[/bold]")
    for prio in NotificationPriority:
        n = await manager.notify(
            title=f"Priority: {prio.value}",
            body=f"This is a {prio.value} priority notification.",
            priority=prio,
            channel=NotificationChannel.LOG,
            source="demo",
        )
        console.print(f"   [{prio.value}] status={n.status.value}")

    # -------------------------------------------------------------------
    # 3. Quiet hours
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Quiet hours:[/bold]")
    manager.set_quiet_hours(0, 6)  # midnight to 6am
    console.print("   Quiet hours set: 00:00 - 06:00")

    n_low = await manager.notify(
        title="Low-prio during quiet",
        body="This may be suppressed.",
        priority=NotificationPriority.LOW,
    )
    n_urgent = await manager.notify(
        title="Urgent bypasses quiet",
        body="Urgent notifications always get through.",
        priority=NotificationPriority.URGENT,
    )
    console.print(f"   Low-prio status: {n_low.status.value}")
    console.print(f"   Urgent status: {n_urgent.status.value}")

    manager.clear_quiet_hours()
    console.print("   Quiet hours cleared")

    # -------------------------------------------------------------------
    # 4. Rate limiting
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Rate limiting:[/bold]")
    manager.set_rate_limit(5)
    console.print("   Rate limit set to 5/minute")

    sent_count = 0
    limited_count = 0
    for i in range(8):
        n = await manager.notify(
            title=f"Batch {i+1}",
            body="Testing rate limit",
            channel=NotificationChannel.LOG,
        )
        if n.status.value == "sent":
            sent_count += 1
        else:
            limited_count += 1
    console.print(f"   Sent: {sent_count}, Rate-limited: {limited_count}")
    manager.set_rate_limit(30)  # reset

    # -------------------------------------------------------------------
    # 5. Read tracking
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Read tracking:[/bold]")
    unread = manager.get_unread()
    console.print(f"   Unread notifications: {len(unread)}")

    # Mark some as read
    if unread:
        manager.mark_read(unread[0].id)
        console.print(f"   Marked '{unread[0].title}' as read")

    all_read = manager.mark_all_read()
    console.print(f"   Marked all as read: {all_read} notifications")

    # -------------------------------------------------------------------
    # 6. History and stats
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Notification history and stats:[/bold]")
    history = manager.get_history(limit=5)
    table = Table(title="Recent Notifications")
    table.add_column("Title", style="cyan")
    table.add_column("Priority", style="yellow")
    table.add_column("Channel")
    table.add_column("Status", style="bold")
    for n in history:
        table.add_row(n.title, n.priority.value, n.channel.value, n.status.value)
    console.print(table)

    stats = manager.get_stats()
    console.print(f"\n   Stats:")
    for key, val in stats.items():
        console.print(f"   - {key}: {val}")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
