"""Knowledge graph system tests.

Tests knowledge node/edge management, entity extraction, graph queries,
traversal, statistics, and serialization.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Knowledge Graph Models
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeNode:
    id: str
    label: str
    node_type: str = "entity"  # entity, concept, event, attribute
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    source: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def update_property(self, key: str, value: Any) -> None:
        self.properties[key] = value
        self.updated_at = datetime.datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type,
            "properties": self.properties,
        }


@dataclass
class KnowledgeEdge:
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "weight": self.weight,
        }


class KnowledgeGraph:
    """Simple knowledge graph implementation."""

    def __init__(self):
        self.nodes: dict[str, KnowledgeNode] = {}
        self.edges: list[KnowledgeEdge] = []
        self._node_counter = 0

    def add_node(self, label: str, node_type: str = "entity",
                 properties: dict | None = None,
                 source: str = "") -> KnowledgeNode:
        self._node_counter += 1
        node = KnowledgeNode(
            id=f"node-{self._node_counter:04d}",
            label=label,
            node_type=node_type,
            properties=properties or {},
            source=source,
        )
        self.nodes[node.id] = node
        return node

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        return self.nodes.get(node_id)

    def find_nodes(self, label: str | None = None,
                   node_type: str | None = None,
                   limit: int = 50) -> list[KnowledgeNode]:
        result = list(self.nodes.values())
        if label:
            result = [n for n in result if label.lower() in n.label.lower()]
        if node_type:
            result = [n for n in result if n.node_type == node_type]
        return result[:limit]

    def add_edge(self, source_id: str, target_id: str,
                 relation_type: str, weight: float = 1.0,
                 properties: dict | None = None) -> KnowledgeEdge | None:
        if source_id not in self.nodes or target_id not in self.nodes:
            return None
        edge = KnowledgeEdge(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            properties=properties or {},
        )
        self.edges.append(edge)
        return edge

    def get_edges(self, node_id: str, direction: str = "both") -> list[KnowledgeEdge]:
        result = []
        for edge in self.edges:
            if direction in ("outgoing", "both") and edge.source_id == node_id:
                result.append(edge)
            if direction in ("incoming", "both") and edge.target_id == node_id:
                result.append(edge)
        return result

    def get_neighbors(self, node_id: str) -> list[KnowledgeNode]:
        neighbor_ids = set()
        for edge in self.edges:
            if edge.source_id == node_id:
                neighbor_ids.add(edge.target_id)
            if edge.target_id == node_id:
                neighbor_ids.add(edge.source_id)
        return [self.nodes[nid] for nid in neighbor_ids if nid in self.nodes]

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self.nodes:
            return False
        del self.nodes[node_id]
        self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
        return True

    def remove_edge(self, source_id: str, target_id: str,
                    relation_type: str | None = None) -> int:
        before = len(self.edges)
        self.edges = [
            e for e in self.edges
            if not (e.source_id == source_id and e.target_id == target_id
                    and (relation_type is None or e.relation_type == relation_type))
        ]
        return before - len(self.edges)

    def has_path(self, from_id: str, to_id: str) -> bool:
        """BFS to check if a path exists between two nodes."""
        if from_id not in self.nodes or to_id not in self.nodes:
            return False
        visited = set()
        queue = [from_id]
        while queue:
            current = queue.pop(0)
            if current == to_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            for edge in self.edges:
                if edge.source_id == current and edge.target_id not in visited:
                    queue.append(edge.target_id)
                if edge.target_id == current and edge.source_id not in visited:
                    queue.append(edge.source_id)
        return False

    def merge_nodes(self, node_id_1: str, node_id_2: str) -> KnowledgeNode | None:
        """Merge two nodes, keeping the first and redirecting edges."""
        n1 = self.nodes.get(node_id_1)
        n2 = self.nodes.get(node_id_2)
        if not n1 or not n2:
            return None
        # Merge properties
        n1.properties.update(n2.properties)
        n1.label = f"{n1.label} / {n2.label}"
        # Redirect edges from n2 to n1
        for edge in self.edges:
            if edge.source_id == node_id_2:
                edge.source_id = node_id_1
            if edge.target_id == node_id_2:
                edge.target_id = node_id_1
        # Remove n2
        del self.nodes[node_id_2]
        # Remove self-loops
        self.edges = [e for e in self.edges if e.source_id != e.target_id]
        return n1

    @property
    def stats(self) -> dict[str, Any]:
        node_types: dict[str, int] = {}
        for n in self.nodes.values():
            node_types[n.node_type] = node_types.get(n.node_type, 0) + 1
        relation_types: dict[str, int] = {}
        for e in self.edges:
            relation_types[e.relation_type] = relation_types.get(e.relation_type, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "node_types": node_types,
            "relation_types": relation_types,
        }

    def to_visualization(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }


# ---------------------------------------------------------------------------
# Tests: KnowledgeNode
# ---------------------------------------------------------------------------

class TestKnowledgeNode:
    def test_create_node(self):
        n = KnowledgeNode(id="n1", label="Python")
        assert n.label == "Python"
        assert n.node_type == "entity"

    def test_node_with_properties(self):
        n = KnowledgeNode(id="n1", label="Python", properties={"version": "3.12"})
        assert n.properties["version"] == "3.12"

    def test_update_property(self):
        n = KnowledgeNode(id="n1", label="Python")
        n.update_property("version", "3.12")
        assert n.properties["version"] == "3.12"

    def test_to_dict(self):
        n = KnowledgeNode(id="n1", label="Python", node_type="concept")
        d = n.to_dict()
        assert d["id"] == "n1"
        assert d["label"] == "Python"
        assert d["node_type"] == "concept"

    def test_node_types(self):
        for nt in ["entity", "concept", "event", "attribute"]:
            n = KnowledgeNode(id="n1", label="test", node_type=nt)
            assert n.node_type == nt


# ---------------------------------------------------------------------------
# Tests: KnowledgeEdge
# ---------------------------------------------------------------------------

class TestKnowledgeEdge:
    def test_create_edge(self):
        e = KnowledgeEdge(source_id="n1", target_id="n2", relation_type="uses")
        assert e.relation_type == "uses"
        assert e.weight == 1.0

    def test_edge_with_weight(self):
        e = KnowledgeEdge(source_id="n1", target_id="n2", relation_type="uses", weight=0.8)
        assert e.weight == 0.8

    def test_edge_to_dict(self):
        e = KnowledgeEdge(source_id="n1", target_id="n2", relation_type="depends_on")
        d = e.to_dict()
        assert d["source_id"] == "n1"
        assert d["target_id"] == "n2"
        assert d["relation_type"] == "depends_on"


# ---------------------------------------------------------------------------
# Tests: KnowledgeGraph - Basic
# ---------------------------------------------------------------------------

class TestKnowledgeGraphBasic:
    def test_add_node(self):
        g = KnowledgeGraph()
        n = g.add_node("Python")
        assert n.label == "Python"
        assert len(g.nodes) == 1

    def test_get_node(self):
        g = KnowledgeGraph()
        n = g.add_node("Python")
        found = g.get_node(n.id)
        assert found is not None
        assert found.label == "Python"

    def test_find_by_label(self):
        g = KnowledgeGraph()
        g.add_node("Python")
        g.add_node("JavaScript")
        g.add_node("Python Library")
        results = g.find_nodes(label="Python")
        assert len(results) == 2

    def test_find_by_type(self):
        g = KnowledgeGraph()
        g.add_node("Python", node_type="entity")
        g.add_node("Programming", node_type="concept")
        entities = g.find_nodes(node_type="entity")
        assert len(entities) == 1

    def test_remove_node(self):
        g = KnowledgeGraph()
        n = g.add_node("Remove me")
        assert g.remove_node(n.id) is True
        assert len(g.nodes) == 0

    def test_remove_node_cleans_edges(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        g.add_edge(n1.id, n2.id, "relates")
        g.remove_node(n1.id)
        assert len(g.edges) == 0


# ---------------------------------------------------------------------------
# Tests: KnowledgeGraph - Edges
# ---------------------------------------------------------------------------

class TestKnowledgeGraphEdges:
    def test_add_edge(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        e = g.add_edge(n1.id, n2.id, "uses")
        assert e is not None
        assert len(g.edges) == 1

    def test_add_edge_invalid_nodes(self):
        g = KnowledgeGraph()
        e = g.add_edge("missing1", "missing2", "uses")
        assert e is None

    def test_get_outgoing_edges(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        n3 = g.add_node("C")
        g.add_edge(n1.id, n2.id, "uses")
        g.add_edge(n1.id, n3.id, "depends_on")
        edges = g.get_edges(n1.id, direction="outgoing")
        assert len(edges) == 2

    def test_get_incoming_edges(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        g.add_edge(n1.id, n2.id, "uses")
        incoming = g.get_edges(n2.id, direction="incoming")
        assert len(incoming) == 1

    def test_get_neighbors(self):
        g = KnowledgeGraph()
        n1 = g.add_node("Center")
        n2 = g.add_node("Left")
        n3 = g.add_node("Right")
        g.add_edge(n1.id, n2.id, "left")
        g.add_edge(n3.id, n1.id, "right")
        neighbors = g.get_neighbors(n1.id)
        assert len(neighbors) == 2

    def test_remove_edge(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        g.add_edge(n1.id, n2.id, "uses")
        removed = g.remove_edge(n1.id, n2.id)
        assert removed == 1
        assert len(g.edges) == 0


# ---------------------------------------------------------------------------
# Tests: KnowledgeGraph - Traversal
# ---------------------------------------------------------------------------

class TestKnowledgeGraphTraversal:
    def test_has_direct_path(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        g.add_edge(n1.id, n2.id, "connects")
        assert g.has_path(n1.id, n2.id) is True

    def test_has_indirect_path(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        n3 = g.add_node("C")
        g.add_edge(n1.id, n2.id, "to")
        g.add_edge(n2.id, n3.id, "to")
        assert g.has_path(n1.id, n3.id) is True

    def test_no_path(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        assert g.has_path(n1.id, n2.id) is False

    def test_self_path(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        assert g.has_path(n1.id, n1.id) is True

    def test_path_nonexistent_node(self):
        g = KnowledgeGraph()
        assert g.has_path("missing", "also_missing") is False


# ---------------------------------------------------------------------------
# Tests: KnowledgeGraph - Merge
# ---------------------------------------------------------------------------

class TestKnowledgeGraphMerge:
    def test_merge_nodes(self):
        g = KnowledgeGraph()
        n1 = g.add_node("Python", properties={"type": "language"})
        n2 = g.add_node("Python 3", properties={"version": "3.12"})
        merged = g.merge_nodes(n1.id, n2.id)
        assert merged is not None
        assert "version" in merged.properties
        assert n2.id not in g.nodes

    def test_merge_redirects_edges(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        n3 = g.add_node("C")
        g.add_edge(n2.id, n3.id, "connects")
        g.merge_nodes(n1.id, n2.id)
        # Edge should now go from n1 to n3
        edges = g.get_edges(n1.id, direction="outgoing")
        assert len(edges) == 1
        assert edges[0].target_id == n3.id


# ---------------------------------------------------------------------------
# Tests: KnowledgeGraph - Stats
# ---------------------------------------------------------------------------

class TestKnowledgeGraphStats:
    def test_empty_stats(self):
        g = KnowledgeGraph()
        stats = g.stats
        assert stats["nodes"] == 0
        assert stats["edges"] == 0

    def test_stats_with_data(self):
        g = KnowledgeGraph()
        g.add_node("A", node_type="entity")
        g.add_node("B", node_type="concept")
        n1 = g.add_node("C", node_type="entity")
        n2 = g.add_node("D", node_type="entity")
        g.add_edge(n1.id, n2.id, "uses")
        stats = g.stats
        assert stats["nodes"] == 4
        assert stats["edges"] == 1
        assert stats["node_types"]["entity"] == 3
        assert stats["node_types"]["concept"] == 1

    def test_visualization(self):
        g = KnowledgeGraph()
        n1 = g.add_node("A")
        n2 = g.add_node("B")
        g.add_edge(n1.id, n2.id, "connects")
        viz = g.to_visualization()
        assert len(viz["nodes"]) == 2
        assert len(viz["edges"]) == 1


# ---------------------------------------------------------------------------
# Tests: Serialization
# ---------------------------------------------------------------------------

class TestKnowledgeGraphSerialization:
    def test_serialize_graph(self):
        g = KnowledgeGraph()
        n1 = g.add_node("Python", properties={"type": "language"})
        n2 = g.add_node("FastAPI", properties={"type": "framework"})
        g.add_edge(n1.id, n2.id, "has_framework")
        viz = g.to_visualization()
        j = json.dumps(viz)
        restored = json.loads(j)
        assert len(restored["nodes"]) == 2
        assert len(restored["edges"]) == 1

    def test_node_serialization(self):
        n = KnowledgeNode(id="n1", label="Test", properties={"key": "value"})
        d = n.to_dict()
        j = json.dumps(d)
        restored = json.loads(j)
        assert restored["label"] == "Test"
        assert restored["properties"]["key"] == "value"
