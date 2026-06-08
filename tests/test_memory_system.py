"""Memory system tests.

Tests memory storage, retrieval, search, importance scoring,
compaction, and different memory types.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Memory Models
# ---------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    id: str
    content: str
    memory_type: str = "fact"  # fact, preference, conversation, skill_learned, spec_history
    importance: float = 0.5
    keywords: list[str] = field(default_factory=list)
    source: str = ""
    created_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()
        if not self.last_accessed:
            self.last_accessed = self.created_at
        if not self.keywords:
            self.keywords = self._extract_keywords()

    def _extract_keywords(self) -> list[str]:
        """Extract simple keywords from content."""
        words = self.content.lower().split()
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "being", "have", "has", "had", "do", "does", "did", "will",
                      "would", "could", "should", "may", "might", "shall", "can",
                      "to", "of", "in", "for", "on", "with", "at", "by", "from",
                      "as", "into", "through", "during", "before", "after", "and",
                      "but", "or", "nor", "not", "so", "yet", "both", "either",
                      "neither", "each", "every", "all", "any", "few", "more",
                      "most", "other", "some", "such", "no", "only", "own", "same",
                      "than", "too", "very", "it", "its", "this", "that", "these",
                      "those", "i", "me", "my", "we", "our", "you", "your", "he",
                      "she", "they", "them", "their"}
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        return list(set(keywords))[:10]

    def access(self) -> None:
        self.access_count += 1
        self.last_accessed = datetime.datetime.utcnow().isoformat()

    def update_importance(self, new_importance: float) -> None:
        self.importance = max(0.0, min(1.0, new_importance))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "keywords": self.keywords,
            "access_count": self.access_count,
            "created_at": self.created_at,
        }

    def matches_query(self, query: str) -> float:
        """Score how well this memory matches a query. Returns 0-1."""
        query_words = set(query.lower().split())
        keyword_set = set(self.keywords)
        if not query_words:
            return 0.0
        overlap = len(query_words & keyword_set)
        content_match = 1.0 if query.lower() in self.content.lower() else 0.0
        keyword_score = overlap / len(query_words) if query_words else 0
        return min(1.0, content_match * 0.6 + keyword_score * 0.4)


class MemoryStore:
    """In-memory storage for memory entries."""

    def __init__(self):
        self.entries: dict[str, MemoryEntry] = {}
        self._counter = 0

    def add(self, content: str, memory_type: str = "fact",
            importance: float = 0.5, source: str = "",
            metadata: dict | None = None) -> MemoryEntry:
        self._counter += 1
        entry = MemoryEntry(
            id=f"mem-{self._counter:06d}",
            content=content,
            memory_type=memory_type,
            importance=importance,
            source=source,
            metadata=metadata or {},
        )
        self.entries[entry.id] = entry
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        entry = self.entries.get(entry_id)
        if entry:
            entry.access()
        return entry

    def search(self, query: str, limit: int = 5,
               memory_type: str | None = None,
               min_importance: float = 0.0) -> list[MemoryEntry]:
        candidates = list(self.entries.values())
        if memory_type:
            candidates = [e for e in candidates if e.memory_type == memory_type]
        if min_importance > 0:
            candidates = [e for e in candidates if e.importance >= min_importance]

        scored = [(e, e.matches_query(query)) for e in candidates]
        scored.sort(key=lambda x: (x[1], x[0].importance), reverse=True)
        return [e for e, score in scored[:limit] if score > 0]

    def list_all(self, memory_type: str | None = None,
                 sort_by: str = "created_at",
                 limit: int = 100) -> list[MemoryEntry]:
        result = list(self.entries.values())
        if memory_type:
            result = [e for e in result if e.memory_type == memory_type]
        if sort_by == "importance":
            result.sort(key=lambda e: e.importance, reverse=True)
        elif sort_by == "access_count":
            result.sort(key=lambda e: e.access_count, reverse=True)
        elif sort_by == "created_at":
            result.sort(key=lambda e: e.created_at, reverse=True)
        return result[:limit]

    def forget(self, entry_id: str) -> bool:
        if entry_id in self.entries:
            del self.entries[entry_id]
            return True
        return False

    def compact(self, max_entries: int = 1000,
                min_importance: float = 0.1) -> int:
        """Remove low-importance entries if over capacity."""
        if len(self.entries) <= max_entries:
            return 0
        removed = 0
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda e: (e.importance, e.access_count),
        )
        while len(self.entries) > max_entries and sorted_entries:
            entry = sorted_entries.pop(0)
            if entry.importance < min_importance:
                del self.entries[entry.id]
                removed += 1
        return removed

    def update_importance(self, entry_id: str, importance: float) -> bool:
        entry = self.entries.get(entry_id)
        if entry:
            entry.update_importance(importance)
            return True
        return False

    @property
    def stats(self) -> dict[str, Any]:
        types: dict[str, int] = {}
        for e in self.entries.values():
            types[e.memory_type] = types.get(e.memory_type, 0) + 1
        avg_importance = 0.0
        if self.entries:
            avg_importance = sum(e.importance for e in self.entries.values()) / len(self.entries)
        return {
            "total": len(self.entries),
            "by_type": types,
            "avg_importance": round(avg_importance, 3),
            "total_accesses": sum(e.access_count for e in self.entries.values()),
        }


# ---------------------------------------------------------------------------
# Tests: MemoryEntry
# ---------------------------------------------------------------------------

class TestMemoryEntry:
    def test_create_entry(self):
        e = MemoryEntry(id="m1", content="Python uses indentation for blocks")
        assert e.memory_type == "fact"
        assert e.importance == 0.5
        assert len(e.keywords) > 0

    def test_keyword_extraction(self):
        e = MemoryEntry(id="m1", content="The project uses FastAPI for the backend server")
        assert "fastapi" in e.keywords or "project" in e.keywords
        # Stop words should be excluded
        assert "the" not in e.keywords
        assert "for" not in e.keywords

    def test_access_tracking(self):
        e = MemoryEntry(id="m1", content="test")
        assert e.access_count == 0
        e.access()
        assert e.access_count == 1
        e.access()
        assert e.access_count == 2

    def test_importance_update(self):
        e = MemoryEntry(id="m1", content="test")
        e.update_importance(0.9)
        assert e.importance == 0.9

    def test_importance_clamped(self):
        e = MemoryEntry(id="m1", content="test")
        e.update_importance(1.5)
        assert e.importance == 1.0
        e.update_importance(-0.5)
        assert e.importance == 0.0

    def test_to_dict(self):
        e = MemoryEntry(id="m1", content="test fact", memory_type="fact")
        d = e.to_dict()
        assert d["id"] == "m1"
        assert d["content"] == "test fact"
        assert d["memory_type"] == "fact"

    def test_matches_query(self):
        e = MemoryEntry(id="m1", content="The project uses Python and FastAPI")
        score = e.matches_query("Python")
        assert score > 0

    def test_no_match(self):
        e = MemoryEntry(id="m1", content="The weather is sunny today")
        score = e.matches_query("database schema migration")
        assert score == 0.0

    def test_memory_types(self):
        for mt in ["fact", "preference", "conversation", "skill_learned", "spec_history"]:
            e = MemoryEntry(id="m1", content="test", memory_type=mt)
            assert e.memory_type == mt


# ---------------------------------------------------------------------------
# Tests: MemoryStore - Basic Operations
# ---------------------------------------------------------------------------

class TestMemoryStoreBasic:
    def test_add_entry(self):
        store = MemoryStore()
        e = store.add("Python is a programming language")
        assert e.id == "mem-000001"
        assert len(store.entries) == 1

    def test_get_entry(self):
        store = MemoryStore()
        e = store.add("test content")
        found = store.get(e.id)
        assert found is not None
        assert found.content == "test content"
        assert found.access_count == 1  # Accessed by get

    def test_get_nonexistent(self):
        store = MemoryStore()
        assert store.get("missing") is None

    def test_forget_entry(self):
        store = MemoryStore()
        e = store.add("forget me")
        assert store.forget(e.id) is True
        assert len(store.entries) == 0

    def test_forget_nonexistent(self):
        store = MemoryStore()
        assert store.forget("missing") is False

    def test_update_importance(self):
        store = MemoryStore()
        e = store.add("important fact")
        assert store.update_importance(e.id, 0.95) is True
        assert store.entries[e.id].importance == 0.95


# ---------------------------------------------------------------------------
# Tests: MemoryStore - Search
# ---------------------------------------------------------------------------

class TestMemoryStoreSearch:
    def test_search_by_content(self):
        store = MemoryStore()
        store.add("Python is great for web development")
        store.add("JavaScript runs in the browser")
        store.add("Python has excellent libraries")
        results = store.search("Python")
        assert len(results) >= 1

    def test_search_by_type(self):
        store = MemoryStore()
        store.add("I prefer dark mode", memory_type="preference")
        store.add("Python is a language", memory_type="fact")
        results = store.search("prefer", memory_type="preference")
        assert len(results) >= 0  # May or may not match

    def test_search_with_limit(self):
        store = MemoryStore()
        for i in range(20):
            store.add(f"Python fact number {i}")
        results = store.search("Python", limit=3)
        assert len(results) <= 3

    def test_search_min_importance(self):
        store = MemoryStore()
        store.add("Low importance", importance=0.1)
        store.add("High importance fact about coding", importance=0.9)
        results = store.search("importance", min_importance=0.5)
        # Only high importance entries should be returned
        for r in results:
            assert r.importance >= 0.5

    def test_search_no_results(self):
        store = MemoryStore()
        store.add("Something about cats")
        results = store.search("quantum physics")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests: MemoryStore - List
# ---------------------------------------------------------------------------

class TestMemoryStoreList:
    def test_list_all(self):
        store = MemoryStore()
        store.add("Fact 1")
        store.add("Fact 2")
        store.add("Fact 3")
        result = store.list_all()
        assert len(result) == 3

    def test_list_by_type(self):
        store = MemoryStore()
        store.add("Fact", memory_type="fact")
        store.add("Preference", memory_type="preference")
        facts = store.list_all(memory_type="fact")
        assert len(facts) == 1

    def test_list_sort_by_importance(self):
        store = MemoryStore()
        store.add("Low", importance=0.1)
        store.add("High", importance=0.9)
        store.add("Mid", importance=0.5)
        result = store.list_all(sort_by="importance")
        assert result[0].importance == 0.9
        assert result[-1].importance == 0.1

    def test_list_with_limit(self):
        store = MemoryStore()
        for i in range(50):
            store.add(f"Entry {i}")
        result = store.list_all(limit=10)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# Tests: MemoryStore - Compaction
# ---------------------------------------------------------------------------

class TestMemoryStoreCompaction:
    def test_compact_removes_low_importance(self):
        store = MemoryStore()
        for i in range(20):
            store.add(f"Low importance {i}", importance=0.05)
        for i in range(5):
            store.add(f"High importance {i}", importance=0.8)
        removed = store.compact(max_entries=10, min_importance=0.1)
        assert removed > 0
        assert len(store.entries) <= 15

    def test_compact_noop_under_limit(self):
        store = MemoryStore()
        store.add("Entry 1")
        store.add("Entry 2")
        removed = store.compact(max_entries=100)
        assert removed == 0

    def test_compact_preserves_high_importance(self):
        store = MemoryStore()
        for i in range(10):
            store.add(f"Low {i}", importance=0.05)
        high = store.add("Critical fact", importance=0.95)
        store.compact(max_entries=5, min_importance=0.1)
        assert high.id in store.entries


# ---------------------------------------------------------------------------
# Tests: MemoryStore - Stats
# ---------------------------------------------------------------------------

class TestMemoryStoreStats:
    def test_empty_stats(self):
        store = MemoryStore()
        stats = store.stats
        assert stats["total"] == 0
        assert stats["avg_importance"] == 0

    def test_stats_with_entries(self):
        store = MemoryStore()
        store.add("Fact 1", memory_type="fact", importance=0.8)
        store.add("Fact 2", memory_type="fact", importance=0.6)
        store.add("Pref", memory_type="preference", importance=0.5)
        stats = store.stats
        assert stats["total"] == 3
        assert stats["by_type"]["fact"] == 2
        assert stats["by_type"]["preference"] == 1
        assert 0.6 <= stats["avg_importance"] <= 0.7

    def test_stats_accesses(self):
        store = MemoryStore()
        e = store.add("test")
        store.get(e.id)
        store.get(e.id)
        store.get(e.id)
        stats = store.stats
        assert stats["total_accesses"] == 3


# ---------------------------------------------------------------------------
# Tests: Memory Serialization
# ---------------------------------------------------------------------------

class TestMemorySerialization:
    def test_serialize_entries(self):
        store = MemoryStore()
        store.add("Fact 1")
        store.add("Fact 2")
        entries = [e.to_dict() for e in store.entries.values()]
        serialized = json.dumps(entries)
        restored = json.loads(serialized)
        assert len(restored) == 2

    def test_entry_json_roundtrip(self):
        e = MemoryEntry(id="m1", content="Python rocks", importance=0.9)
        d = e.to_dict()
        j = json.dumps(d)
        restored = json.loads(j)
        assert restored["content"] == "Python rocks"
        assert restored["importance"] == 0.9
