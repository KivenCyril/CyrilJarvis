#!/usr/bin/env python3
"""knowledge_graph.py -- Knowledge graph demonstration.

Shows how JARVIS builds and queries an in-memory knowledge graph:
manual entity/relation management, naive text extraction, graph
traversal, persistence, and visualisation export.

Run:
    python examples/knowledge_graph.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.tree import Tree
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.knowledge.graph import GraphEdge, GraphNode, KnowledgeGraph
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Knowledge Graph Demo[/bold cyan]",
                        subtitle="Entity-Relation Graph with Extraction & Query"))

    graph = KnowledgeGraph()

    # -------------------------------------------------------------------
    # 1. Add entities manually
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Adding entities manually...[/bold]")
    entities = [
        GraphNode(id="python", label="Python", node_type="language",
                  properties={"version": "3.12", "paradigm": "multi"}),
        GraphNode(id="fastapi", label="FastAPI", node_type="framework",
                  properties={"language": "python", "async": True}),
        GraphNode(id="pydantic", label="Pydantic", node_type="library",
                  properties={"purpose": "data validation"}),
        GraphNode(id="jarvis", label="JARVIS", node_type="project",
                  properties={"type": "AI assistant"}),
        GraphNode(id="streaming_spec", label="Streaming Spec", node_type="concept",
                  properties={"type": "core innovation"}),
        GraphNode(id="hermes", label="Hermes Agent", node_type="project",
                  properties={"role": "inspiration"}),
        GraphNode(id="openclaw", label="OpenClaw", node_type="project",
                  properties={"role": "foundation"}),
    ]

    for node in entities:
        graph.add_node(node)
        console.print(f"   + [{node.node_type}] {node.label}")

    # -------------------------------------------------------------------
    # 2. Add relations manually
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Adding relations...[/bold]")
    relations = [
        GraphEdge(source="jarvis", target="python", relation="built_with", confidence=1.0),
        GraphEdge(source="jarvis", target="fastapi", relation="uses", confidence=1.0),
        GraphEdge(source="fastapi", target="pydantic", relation="depends_on", confidence=1.0),
        GraphEdge(source="fastapi", target="python", relation="written_in", confidence=1.0),
        GraphEdge(source="jarvis", target="streaming_spec", relation="introduces", confidence=1.0),
        GraphEdge(source="jarvis", target="hermes", relation="inspired_by", confidence=0.9),
        GraphEdge(source="jarvis", target="openclaw", relation="built_on", confidence=0.9),
    ]

    for edge in relations:
        graph.add_edge(edge)
        src = graph.get_node(edge.source)
        tgt = graph.get_node(edge.target)
        console.print(f"   {src.label if src else '?'} --[{edge.relation}]--> "
                      f"{tgt.label if tgt else '?'} (conf={edge.confidence})")

    # -------------------------------------------------------------------
    # 3. Extract entities from text (naive mode, no LLM)
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Extracting entities from text (naive mode)...[/bold]")
    text = """
    The JARVIS project was inspired by Hermes Agent and built on OpenClaw.
    It uses Python with FastAPI for the backend and Rich for terminal UI.
    The core innovation is the Streaming Spec, a real-time editable task
    control panel. Machine Learning models are used for intent routing.
    """
    extracted = await graph.extract_from_text(text)
    console.print(f"   Extracted {len(extracted)} new entities:")
    for node in extracted:
        console.print(f"   + [{node.node_type}] {node.label}")

    # -------------------------------------------------------------------
    # 4. Query the graph
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Querying the graph...[/bold]")
    queries = [
        "What frameworks does JARVIS use?",
        "What is the core innovation?",
        "Python libraries",
    ]

    for q in queries:
        results = await graph.query(q)
        names = [n.label for n in results[:5]]
        console.print(f"   Q: '{q}'")
        console.print(f"   A: {', '.join(names)}")

    # -------------------------------------------------------------------
    # 5. Traverse neighbours
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Neighbour traversal:[/bold]")
    for node_id in ["jarvis", "fastapi"]:
        node = graph.get_node(node_id)
        if not node:
            continue
        neighbours = graph.neighbors(node_id)
        tree = Tree(f"[bold]{node.label}[/bold] ({node.node_type})")
        for edge, neighbour in neighbours:
            tree.add(f"--[{edge.relation}]--> {neighbour.label} ({neighbour.node_type})")
        console.print(tree)

    # -------------------------------------------------------------------
    # 6. Graph statistics
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Graph statistics:[/bold]")
    stats = graph.stats
    console.print(f"   Nodes: {stats['nodes']}")
    console.print(f"   Edges: {stats['edges']}")
    console.print(f"   Node types: {stats['node_types']}")
    console.print(f"   Relation types: {stats['relation_types']}")

    # -------------------------------------------------------------------
    # 7. Save and reload
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Save/load persistence...[/bold]")
    tmpdir = tempfile.mkdtemp(prefix="jarvis_kg_")
    graph_path = f"{tmpdir}/knowledge_graph.json"

    graph.save(graph_path)
    console.print(f"   Saved to: {graph_path}")

    # Load into a new graph
    new_graph = KnowledgeGraph()
    new_graph.load(graph_path)
    new_stats = new_graph.stats
    console.print(f"   Loaded: {new_stats['nodes']} nodes, {new_stats['edges']} edges")

    # -------------------------------------------------------------------
    # 8. Visualisation export
    # -------------------------------------------------------------------
    console.print("\n[bold]8. Visualisation export:[/bold]")
    viz_data = graph.to_visualization()
    console.print(f"   Export has {len(viz_data['nodes'])} nodes, {len(viz_data['edges'])} edges")

    # Show first few nodes
    table = Table(title="Nodes (sample)")
    table.add_column("ID", style="dim")
    table.add_column("Label", style="cyan")
    table.add_column("Type", style="yellow")
    for node_data in viz_data["nodes"][:8]:
        table.add_row(node_data["id"], node_data["label"], node_data["type"])
    console.print(table)

    # -------------------------------------------------------------------
    # 9. Node merging
    # -------------------------------------------------------------------
    console.print("\n[bold]9. Node merging (deduplication):[/bold]")
    # Add a duplicate
    graph.add_node(GraphNode(id="py", label="py", node_type="language",
                             properties={"alias": True}))
    graph.add_edge(GraphEdge(source="py", target="fastapi", relation="used_by"))
    console.print(f"   Before merge: {graph.stats['nodes']} nodes")
    graph.merge_node("py", "python")
    console.print(f"   After merge:  {graph.stats['nodes']} nodes")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
