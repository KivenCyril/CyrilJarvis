#!/usr/bin/env python3
"""event_driven.py -- Event bus demonstration.

Shows JARVIS's event system: topic-based pub/sub, wildcard matching,
event filtering, middleware, history, and replay.

Run:
    python examples/event_driven.py
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
    from jarvis.events.bus import Event, EventBus, EventFilter, EventPriority
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Event-Driven Demo[/bold cyan]",
                        subtitle="Pub/Sub with Wildcards, Filters, Middleware"))

    bus = EventBus()
    received_events: list[str] = []

    # -------------------------------------------------------------------
    # 1. Basic subscription and publishing
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Basic pub/sub:[/bold]")

    async def on_spec_created(event: Event) -> None:
        received_events.append(f"spec_created: {event.data.get('name', '?')}")

    async def on_agent_event(event: Event) -> None:
        received_events.append(f"agent: {event.topic}")

    bus.subscribe(on_spec_created, topics=["spec.created"])
    bus.subscribe(on_agent_event, topics=["agent.executed"])

    # Publish events
    await bus.publish(Event(topic="spec.created", source="engine",
                            data={"name": "Auth API"}))
    await bus.publish(Event(topic="agent.executed", source="orchestrator",
                            data={"agent": "code", "success": True}))
    await bus.publish(Event(topic="tool.called", source="code_agent",
                            data={"tool": "read_file"}))  # no subscriber

    console.print(f"   Published 3 events, received {len(received_events)}:")
    for e in received_events:
        console.print(f"   - {e}")

    # -------------------------------------------------------------------
    # 2. Wildcard matching
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Wildcard subscriptions:[/bold]")
    wildcard_events: list[str] = []

    async def on_any_spec(event: Event) -> None:
        wildcard_events.append(f"spec.*: {event.topic}")

    async def on_everything(event: Event) -> None:
        wildcard_events.append(f"*: {event.topic}")

    bus.subscribe(on_any_spec, topics=["spec.*"])
    sub_all_id = bus.subscribe(on_everything, topics=["*"])

    await bus.publish(Event(topic="spec.completed", source="engine"))
    await bus.publish(Event(topic="spec.failed", source="engine"))
    await bus.publish(Event(topic="memory.stored", source="memory"))

    console.print(f"   Wildcard events received: {len(wildcard_events)}")
    for e in wildcard_events:
        console.print(f"   - {e}")

    bus.unsubscribe(sub_all_id)

    # -------------------------------------------------------------------
    # 3. Event filtering
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Event filtering:[/bold]")
    filtered_events: list[str] = []

    async def on_high_priority(event: Event) -> None:
        filtered_events.append(f"HIGH: {event.topic} from {event.source}")

    # Only high-priority events from specific sources
    bus.subscribe(
        on_high_priority,
        topics=["alert.*"],
        sources=["security"],
        min_priority=EventPriority.HIGH,
    )

    # This should pass the filter
    await bus.publish(Event(topic="alert.secret_detected", source="security",
                            priority=EventPriority.HIGH))
    # This should not pass (wrong source)
    await bus.publish(Event(topic="alert.warning", source="engine",
                            priority=EventPriority.HIGH))
    # This should not pass (low priority)
    await bus.publish(Event(topic="alert.info", source="security",
                            priority=EventPriority.LOW))

    console.print(f"   Filtered events (should be 1): {len(filtered_events)}")
    for e in filtered_events:
        console.print(f"   - {e}")

    # Test EventFilter directly
    ef = EventFilter(topics=["agent.*"], min_priority=EventPriority.NORMAL)
    test_events = [
        Event(topic="agent.started", priority=EventPriority.NORMAL),
        Event(topic="agent.started", priority=EventPriority.LOW),
        Event(topic="spec.created", priority=EventPriority.HIGH),
    ]
    for ev in test_events:
        match = ef.matches(ev)
        console.print(f"   Filter '{ev.topic}' (prio={ev.priority.name}): {'match' if match else 'no match'}")

    # -------------------------------------------------------------------
    # 4. One-shot subscription
    # -------------------------------------------------------------------
    console.print("\n[bold]4. One-shot subscription:[/bold]")
    oneshot_count = 0

    async def on_once(event: Event) -> None:
        nonlocal oneshot_count
        oneshot_count += 1

    bus.subscribe(on_once, topics=["oneshot.test"], once=True)
    await bus.publish(Event(topic="oneshot.test"))
    await bus.publish(Event(topic="oneshot.test"))
    await bus.publish(Event(topic="oneshot.test"))
    console.print(f"   Published 3 times, handler called {oneshot_count} time(s) (expected 1)")

    # -------------------------------------------------------------------
    # 5. Middleware
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Middleware pipeline:[/bold]")
    middleware_log: list[str] = []

    def logging_middleware(event: Event) -> Event | None:
        middleware_log.append(f"MW: {event.topic}")
        return event  # pass through

    def drop_debug_middleware(event: Event) -> Event | None:
        if event.topic.startswith("debug."):
            middleware_log.append(f"DROPPED: {event.topic}")
            return None  # drop debug events
        return event

    bus.add_middleware(logging_middleware)
    bus.add_middleware(drop_debug_middleware)

    await bus.publish(Event(topic="normal.event"))
    await bus.publish(Event(topic="debug.verbose"))

    console.print(f"   Middleware log:")
    for entry in middleware_log:
        console.print(f"   - {entry}")

    # -------------------------------------------------------------------
    # 6. Event history
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Event history:[/bold]")
    history = bus.get_history(limit=5)
    table = Table(title="Recent Events (last 5)")
    table.add_column("Topic", style="cyan")
    table.add_column("Source", style="yellow")
    table.add_column("Priority", style="dim")
    for ev in history:
        table.add_row(ev.topic, ev.source, ev.priority.name)
    console.print(table)

    # Filter by topic
    spec_events = bus.get_history(topic="spec.created")
    console.print(f"   spec.created events: {len(spec_events)}")

    # -------------------------------------------------------------------
    # 7. Replay
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Event replay:[/bold]")
    replay_log: list[str] = []

    async def replay_handler(event: Event) -> None:
        replay_log.append(event.topic)

    replayed = await bus.replay("spec.created", replay_handler)
    console.print(f"   Replayed {replayed} spec.created events")

    # -------------------------------------------------------------------
    # 8. Convenience helper and stats
    # -------------------------------------------------------------------
    console.print("\n[bold]8. Convenience publish and stats:[/bold]")
    await bus.publish_simple("metric.collected", source="observability",
                              metric="cpu", value=0.45)
    console.print(f"   Published with publish_simple()")

    stats = bus.get_stats()
    console.print(f"   Stats:")
    for key, val in stats.items():
        console.print(f"   - {key}: {val}")

    # Dead letters
    dead = bus.get_dead_letters()
    console.print(f"   Dead letters: {len(dead)}")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
