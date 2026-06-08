#!/usr/bin/env python3
"""memory_system.py -- Memory system demonstration.

Shows JARVIS's persistent memory: adding different memory types,
keyword-based search with relevance scoring, context generation
for agents, memory pruning, and file persistence.

Run:
    python examples/memory_system.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.memory.manager import MemoryManager, MemoryType
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Memory System Demo[/bold cyan]",
                        subtitle="Persistent Memory with Keyword Search"))

    tmpdir = tempfile.mkdtemp(prefix="jarvis_memory_")
    memory = MemoryManager(storage_path=tmpdir)

    # -------------------------------------------------------------------
    # 1. Add different memory types
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Adding memories (heuristic mode, no LLM)...[/bold]")

    memories_to_add = [
        (MemoryType.FACT, "JARVIS uses FastAPI for its HTTP server and Pydantic for data validation."),
        (MemoryType.FACT, "The Streaming Spec is the core innovation -- a real-time editable task panel."),
        (MemoryType.PREFERENCE, "User prefers Python 3.12 with type hints and async/await patterns."),
        (MemoryType.PREFERENCE, "User likes concise responses in markdown format."),
        (MemoryType.SKILL_LEARNED, "Learned to deploy FastAPI services to Kubernetes with zero downtime."),
        (MemoryType.SKILL_LEARNED, "Learned to use Pydantic for strict input validation in APIs."),
        (MemoryType.CONVERSATION, "Discussed authentication strategies. User chose JWT over session cookies."),
        (MemoryType.SPEC_HISTORY, "Completed spec: Build REST API for user auth with bcrypt and JWT tokens."),
    ]

    for mem_type, content in memories_to_add:
        entry = await memory.add(content, mem_type)
        console.print(f"   [{mem_type.value}] importance={entry.importance:.2f} "
                      f"keywords={entry.keywords[:4]}")

    console.print(f"   Total memories: {len(memory.list_memories())}")

    # -------------------------------------------------------------------
    # 2. Search with relevance scoring
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Searching memories...[/bold]")
    queries = [
        "FastAPI deployment",
        "user preferences",
        "authentication JWT",
        "Streaming Spec",
    ]

    for query in queries:
        results = await memory.search(query, limit=3)
        console.print(f"\n   Query: '{query}' ({len(results)} results)")
        for r in results:
            console.print(f"   - [{r.memory_type.value}] {r.content[:70]}...")

    # -------------------------------------------------------------------
    # 3. Search filtered by type
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Type-filtered search:[/bold]")
    facts = await memory.search("API", memory_type=MemoryType.FACT)
    console.print(f"   Facts matching 'API': {len(facts)}")
    for f in facts:
        console.print(f"   - {f.content[:70]}...")

    skills = await memory.search("deploy", memory_type=MemoryType.SKILL_LEARNED)
    console.print(f"   Skills matching 'deploy': {len(skills)}")
    for s in skills:
        console.print(f"   - {s.content[:70]}...")

    # -------------------------------------------------------------------
    # 4. Get context for agents
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Context string for agent prompts:[/bold]")
    context = memory.get_context(limit=5)
    console.print(Panel(context, title="Agent Context"))

    # -------------------------------------------------------------------
    # 5. List memories by type
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Memory inventory:[/bold]")
    table = Table(title="Memories by Type")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right", style="yellow")

    for mem_type in MemoryType:
        entries = memory.list_memories(mem_type)
        table.add_row(mem_type.value, str(len(entries)))
    console.print(table)

    # -------------------------------------------------------------------
    # 6. Conversation summarisation (no LLM fallback)
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Conversation summarisation (fallback mode):[/bold]")
    messages = [
        {"role": "user", "content": "How do I add authentication to my FastAPI app?"},
        {"role": "agent", "content": "You can use FastAPI's OAuth2PasswordBearer with JWT tokens."},
        {"role": "user", "content": "Should I use bcrypt for password hashing?"},
        {"role": "agent", "content": "Yes, bcrypt is the recommended choice for password hashing."},
        {"role": "user", "content": "Great, let's implement that."},
    ]
    summary_entry = await memory.summarize_conversation(messages)
    console.print(f"   Summary: {summary_entry.content[:120]}")
    console.print(f"   Type: {summary_entry.memory_type.value}")

    # -------------------------------------------------------------------
    # 7. Pruning
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Memory pruning:[/bold]")
    count_before = len(memory.list_memories())
    pruned = memory.prune(max_age_days=90)
    console.print(f"   Before: {count_before} memories")
    console.print(f"   Pruned: {pruned} old low-importance memories")
    console.print(f"   After: {len(memory.list_memories())} memories")

    # -------------------------------------------------------------------
    # 8. Save and reload
    # -------------------------------------------------------------------
    console.print("\n[bold]8. Persistence (save/load):[/bold]")
    memory.save()
    console.print(f"   Saved to: {tmpdir}")

    # Load into a fresh manager
    new_memory = MemoryManager(storage_path=tmpdir)
    new_memory.load()
    console.print(f"   Loaded: {len(new_memory.list_memories())} memories")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
