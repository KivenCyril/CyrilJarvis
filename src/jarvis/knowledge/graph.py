from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    id: str
    label: str
    node_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Prompt templates for LLM-powered extraction and query
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """\
You are an entity/relation extractor. Given the following text, extract all \
meaningful entities and relationships between them.

Return a JSON object with exactly this structure (no extra keys):
{
  "entities": [
    {"label": "EntityName", "type": "person|concept|tool|event|place|org|other", "properties": {}}
  ],
  "relations": [
    {"source": "EntityA", "target": "EntityB", "relation": "verb_phrase", "confidence": 0.9}
  ]
}

Rules:
- Use short, canonical labels (prefer singular form).
- Merge entities that refer to the same thing.
- confidence is 0-1.
- If no entities found, return {"entities": [], "relations": []}.
- Return ONLY valid JSON, no markdown fences, no commentary.

Text:
{text}
"""

_QUERY_PROMPT = """\
You are a knowledge-graph query planner. Given a user question and a list of \
known entity labels, return the labels most relevant to answering the question.

Return a JSON object:
{{"relevant_entities": ["label1", "label2", ...]}}

If none are relevant, return {{"relevant_entities": []}}.
Return ONLY valid JSON, no markdown fences.

Known entities:
{entities}

Question:
{question}
"""


def _sanitize_id(label: str) -> str:
    """Turn a label into a URL-safe node id."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or uuid.uuid4().hex[:8]


def _parse_json_response(text: str) -> dict:
    """Best-effort JSON extraction from LLM output."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    logger.warning("Failed to parse LLM JSON response: %s", text[:200])
    return {}


class KnowledgeGraph:
    """In-memory knowledge graph with LLM-powered extraction and retrieval.

    Supports:
    - Manual node/edge management
    - LLM-powered entity/relation extraction from text
    - Graph-based semantic query
    - JSON persistence (save/load)
    - Visualization data export
    - Node merging for deduplication
    """

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []

    # ------------------------------------------------------------------
    # Core graph operations
    # ------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges.append(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def neighbors(self, node_id: str) -> list[tuple[GraphEdge, GraphNode]]:
        result: list[tuple[GraphEdge, GraphNode]] = []
        for edge in self._edges:
            if edge.source == node_id:
                target = self._nodes.get(edge.target)
                if target:
                    result.append((edge, target))
            elif edge.target == node_id:
                source = self._nodes.get(edge.source)
                if source:
                    result.append((edge, source))
        return result

    # ------------------------------------------------------------------
    # LLM-powered extraction
    # ------------------------------------------------------------------

    async def extract_from_text(
        self,
        text: str,
        llm_registry: Any | None = None,
    ) -> list[GraphNode]:
        """Extract entities and relations from *text* using an LLM.

        If *llm_registry* is ``None``, falls back to naive regex extraction
        (proper nouns / capitalised phrases).
        """
        if llm_registry is not None:
            return await self._llm_extract(text, llm_registry)
        return self._naive_extract(text)

    async def _llm_extract(self, text: str, llm_registry: Any) -> list[GraphNode]:
        from jarvis.llm.provider import Message, Role

        provider = llm_registry.get()
        prompt = _EXTRACT_PROMPT.format(text=text[:4000])
        response = await provider.chat(
            messages=[Message(role=Role.USER, content=prompt)],
            temperature=0.0,
            max_tokens=2048,
        )
        data = _parse_json_response(response.content)
        return self._ingest_extraction(data)

    def _naive_extract(self, text: str) -> list[GraphNode]:
        """Fallback: extract capitalised multi-word phrases as entities."""
        pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
        labels = sorted(set(re.findall(pattern, text)))
        added: list[GraphNode] = []
        for label in labels:
            node_id = _sanitize_id(label)
            if node_id not in self._nodes:
                node = GraphNode(id=node_id, label=label, node_type="concept")
                self.add_node(node)
                added.append(node)
        return added

    def _ingest_extraction(self, data: dict) -> list[GraphNode]:
        """Add extracted entities and relations to the graph."""
        added: list[GraphNode] = []
        label_to_id: dict[str, str] = {}

        for entity in data.get("entities", []):
            label = entity.get("label", "").strip()
            if not label:
                continue
            node_id = _sanitize_id(label)
            label_to_id[label] = node_id
            if node_id not in self._nodes:
                node = GraphNode(
                    id=node_id,
                    label=label,
                    node_type=entity.get("type", "concept"),
                    properties=entity.get("properties", {}),
                )
                self.add_node(node)
                added.append(node)

        for rel in data.get("relations", []):
            src_label = rel.get("source", "")
            tgt_label = rel.get("target", "")
            src_id = label_to_id.get(src_label, _sanitize_id(src_label))
            tgt_id = label_to_id.get(tgt_label, _sanitize_id(tgt_label))
            if src_id in self._nodes and tgt_id in self._nodes:
                edge = GraphEdge(
                    source=src_id,
                    target=tgt_id,
                    relation=rel.get("relation", "related_to"),
                    confidence=float(rel.get("confidence", 0.8)),
                )
                self.add_edge(edge)

        return added

    # ------------------------------------------------------------------
    # LLM-powered query
    # ------------------------------------------------------------------

    async def query(
        self,
        question: str,
        llm_registry: Any | None = None,
    ) -> list[GraphNode]:
        """Semantic search: identify relevant entities then traverse graph.

        Without an LLM, falls back to simple substring matching on labels.
        """
        if llm_registry is not None and self._nodes:
            return await self._llm_query(question, llm_registry)
        return self._keyword_query(question)

    async def _llm_query(self, question: str, llm_registry: Any) -> list[GraphNode]:
        from jarvis.llm.provider import Message, Role

        labels = [n.label for n in self._nodes.values()]
        provider = llm_registry.get()
        prompt = _QUERY_PROMPT.format(
            entities=json.dumps(labels[:200]),
            question=question,
        )
        response = await provider.chat(
            messages=[Message(role=Role.USER, content=prompt)],
            temperature=0.0,
            max_tokens=512,
        )
        data = _parse_json_response(response.content)
        relevant_labels = set(data.get("relevant_entities", []))

        # Build label -> node lookup
        label_map = {n.label: n for n in self._nodes.values()}
        seed_nodes = [label_map[lb] for lb in relevant_labels if lb in label_map]

        # Expand one hop
        result_ids: set[str] = set()
        result: list[GraphNode] = []
        for node in seed_nodes:
            if node.id not in result_ids:
                result_ids.add(node.id)
                result.append(node)
            for _edge, neighbor in self.neighbors(node.id):
                if neighbor.id not in result_ids:
                    result_ids.add(neighbor.id)
                    result.append(neighbor)

        return result if result else list(self._nodes.values())[:5]

    def _keyword_query(self, question: str) -> list[GraphNode]:
        """Fallback keyword search across node labels and properties."""
        tokens = set(question.lower().split())
        scored: list[tuple[int, GraphNode]] = []
        for node in self._nodes.values():
            haystack = f"{node.label} {node.node_type} {json.dumps(node.properties)}".lower()
            score = sum(1 for t in tokens if t in haystack)
            if score > 0:
                scored.append((score, node))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return [node for _score, node in scored[:10]]
        return list(self._nodes.values())[:5]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist graph to a JSON file."""
        data = {
            "nodes": [asdict(n) for n in self._nodes.values()],
            "edges": [asdict(e) for e in self._edges],
        }
        filepath = Path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Knowledge graph saved to %s (%d nodes, %d edges)", path, len(self._nodes), len(self._edges))

    def load(self, path: str) -> None:
        """Load graph from a JSON file (merges into current graph)."""
        filepath = Path(path)
        if not filepath.exists():
            logger.warning("Graph file not found: %s", path)
            return
        data = json.loads(filepath.read_text(encoding="utf-8"))
        for nd in data.get("nodes", []):
            node = GraphNode(
                id=nd["id"],
                label=nd["label"],
                node_type=nd["node_type"],
                properties=nd.get("properties", {}),
            )
            self._nodes[node.id] = node
        for ed in data.get("edges", []):
            edge = GraphEdge(
                source=ed["source"],
                target=ed["target"],
                relation=ed["relation"],
                confidence=ed.get("confidence", 1.0),
            )
            self._edges.append(edge)
        logger.info("Knowledge graph loaded from %s (%d nodes, %d edges)", path, len(self._nodes), len(self._edges))

    # ------------------------------------------------------------------
    # Visualization export
    # ------------------------------------------------------------------

    def to_visualization(self) -> dict[str, list[dict]]:
        """Export graph as ``{nodes: [...], edges: [...]}`` for frontend rendering."""
        nodes = [
            {
                "id": n.id,
                "label": n.label,
                "type": n.node_type,
                **n.properties,
            }
            for n in self._nodes.values()
        ]
        edges = [
            {
                "source": e.source,
                "target": e.target,
                "relation": e.relation,
                "confidence": e.confidence,
            }
            for e in self._edges
        ]
        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Node merging
    # ------------------------------------------------------------------

    def merge_node(self, node_id: str, into_id: str) -> None:
        """Merge *node_id* into *into_id*, retaining properties and edges."""
        source_node = self._nodes.get(node_id)
        target_node = self._nodes.get(into_id)
        if source_node is None or target_node is None:
            logger.warning("merge_node: one or both nodes not found (%s, %s)", node_id, into_id)
            return

        # Merge properties (target wins on conflict)
        merged_props = {**source_node.properties, **target_node.properties}
        target_node.properties = merged_props

        # Re-point edges
        for edge in self._edges:
            if edge.source == node_id:
                edge.source = into_id
            if edge.target == node_id:
                edge.target = into_id

        # Remove self-loops created by merge
        self._edges = [e for e in self._edges if e.source != e.target]

        # Remove duplicate edges (same source-target-relation)
        seen: set[tuple[str, str, str]] = set()
        deduped: list[GraphEdge] = []
        for edge in self._edges:
            key = (edge.source, edge.target, edge.relation)
            if key not in seen:
                seen.add(key)
                deduped.append(edge)
        self._edges = deduped

        # Remove merged node
        del self._nodes[node_id]
        logger.info("Merged node '%s' into '%s'", node_id, into_id)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        for node in self._nodes.values():
            type_counts[node.node_type] = type_counts.get(node.node_type, 0) + 1

        relation_counts: dict[str, int] = {}
        for edge in self._edges:
            relation_counts[edge.relation] = relation_counts.get(edge.relation, 0) + 1

        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "node_types": type_counts,
            "relation_types": relation_counts,
        }
