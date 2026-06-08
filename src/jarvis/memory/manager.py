from __future__ import annotations

import json
import logging
import math
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    CONVERSATION = "conversation"
    FACT = "fact"
    PREFERENCE = "preference"
    SKILL_LEARNED = "skill_learned"
    SPEC_HISTORY = "spec_history"


@dataclass
class MemoryEntry:
    id: str
    memory_type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    importance: float = 0.5
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["memory_type"] = self.memory_type.value
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryEntry:
        return cls(
            id=d["id"],
            memory_type=MemoryType(d["memory_type"]),
            content=d["content"],
            metadata=d.get("metadata", {}),
            embedding=d.get("embedding"),
            created_at=datetime.fromisoformat(d["created_at"]),
            updated_at=datetime.fromisoformat(d["updated_at"]),
            importance=d.get("importance", 0.5),
            keywords=d.get("keywords", []),
        )


# ---------------------------------------------------------------------------
# Prompt templates for LLM-powered memory operations
# ---------------------------------------------------------------------------

_IMPORTANCE_PROMPT = """\
Rate the importance of the following memory on a scale of 0.0 to 1.0, where:
- 0.0-0.2: trivial/ephemeral (greetings, small talk)
- 0.3-0.5: moderately useful (general facts, context)
- 0.6-0.8: important (user preferences, key decisions, learned skills)
- 0.9-1.0: critical (core project goals, critical errors, security info)

Also extract 3-8 keywords from the content.

Return ONLY a JSON object:
{{"importance": 0.7, "keywords": ["keyword1", "keyword2"]}}

Memory type: {memory_type}
Content:
{content}
"""

_SUMMARIZE_PROMPT = """\
Summarize the following conversation into a concise memory entry. Focus on:
- Key decisions made
- Important facts learned
- Action items or next steps
- User preferences expressed

Return ONLY the summary text (1-3 sentences), no JSON.

Conversation:
{conversation}
"""


def _parse_json_response(text: str) -> dict:
    """Best-effort JSON extraction from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenization, stripping punctuation and short words."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1]


def _extract_keywords_naive(content: str) -> list[str]:
    """Fallback keyword extraction: frequent meaningful tokens."""
    # Simple stop-word list
    stop = {
        "the", "is", "at", "of", "on", "and", "or", "to", "in", "it",
        "an", "as", "be", "by", "do", "if", "no", "so", "up", "we",
        "for", "are", "but", "not", "you", "all", "can", "had", "her",
        "was", "one", "our", "out", "has", "his", "how", "its", "may",
        "new", "now", "old", "see", "way", "who", "did", "got", "let",
        "say", "she", "too", "use", "this", "that", "with", "have",
        "from", "they", "been", "will", "more", "when", "what", "some",
        "than", "them", "into", "each", "make", "like", "just", "also",
        "then", "very", "about", "would", "could", "should", "there",
        "which", "their", "these", "other", "after", "before",
    }
    tokens = _tokenize(content)
    freq: dict[str, int] = {}
    for t in tokens:
        if t not in stop:
            freq[t] = freq.get(t, 0) + 1
    # Sort by frequency, take top 8
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _c in ranked[:8]]


class MemoryManager:
    """Persistent memory manager with keyword-based retrieval.

    Stores each memory as a JSON file under ``storage_path/``.
    Works without LLM (graceful fallback for importance scoring and keywords).
    """

    def __init__(self, storage_path: str = "~/.jarvis/memory") -> None:
        self._storage_path = Path(storage_path).expanduser()
        self._memories: dict[str, MemoryEntry] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ------------------------------------------------------------------
    # Add memory
    # ------------------------------------------------------------------

    async def add(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: dict[str, Any] | None = None,
        llm_registry: Any | None = None,
    ) -> MemoryEntry:
        """Create and persist a new memory entry.

        If *llm_registry* is provided, uses the LLM to assess importance and
        extract keywords. Otherwise falls back to heuristic scoring.
        """
        self._ensure_loaded()

        importance = 0.5
        keywords: list[str] = []

        if llm_registry is not None:
            importance, keywords = await self._llm_assess(content, memory_type, llm_registry)
        else:
            importance = self._heuristic_importance(content, memory_type)
            keywords = _extract_keywords_naive(content)

        now = datetime.now(timezone.utc)
        entry = MemoryEntry(
            id=uuid.uuid4().hex,
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
            importance=importance,
            keywords=keywords,
            created_at=now,
            updated_at=now,
        )
        self._memories[entry.id] = entry
        self._save_entry(entry)
        logger.info("Added memory %s (type=%s, importance=%.2f)", entry.id[:8], memory_type.value, importance)
        return entry

    async def _llm_assess(
        self,
        content: str,
        memory_type: MemoryType,
        llm_registry: Any,
    ) -> tuple[float, list[str]]:
        """Use LLM to rate importance and extract keywords."""
        from jarvis.llm.provider import Message, Role

        try:
            provider = llm_registry.get()
            prompt = _IMPORTANCE_PROMPT.format(
                memory_type=memory_type.value,
                content=content[:2000],
            )
            response = await provider.chat(
                messages=[Message(role=Role.USER, content=prompt)],
                temperature=0.0,
                max_tokens=256,
            )
            data = _parse_json_response(response.content)
            importance = float(data.get("importance", 0.5))
            importance = max(0.0, min(1.0, importance))
            keywords = data.get("keywords", [])
            if not keywords:
                keywords = _extract_keywords_naive(content)
            return importance, keywords
        except Exception:
            logger.warning("LLM importance assessment failed, using heuristic", exc_info=True)
            return self._heuristic_importance(content, memory_type), _extract_keywords_naive(content)

    @staticmethod
    def _heuristic_importance(content: str, memory_type: MemoryType) -> float:
        """Rule-based importance when no LLM is available."""
        base = {
            MemoryType.CONVERSATION: 0.3,
            MemoryType.FACT: 0.5,
            MemoryType.PREFERENCE: 0.6,
            MemoryType.SKILL_LEARNED: 0.7,
            MemoryType.SPEC_HISTORY: 0.6,
        }.get(memory_type, 0.5)

        # Boost for longer, more substantive content
        length_bonus = min(0.15, len(content) / 2000 * 0.15)
        return min(1.0, base + length_bonus)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """Keyword-based search sorted by relevance * importance * recency."""
        self._ensure_loaded()
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

        now = datetime.now(timezone.utc)
        scored: list[tuple[float, MemoryEntry]] = []

        for entry in self._memories.values():
            if memory_type is not None and entry.memory_type != memory_type:
                continue

            # Term frequency scoring across content + keywords
            content_tokens = _tokenize(entry.content)
            keyword_set = set(t.lower() for t in entry.keywords)
            token_freq: dict[str, int] = {}
            for t in content_tokens:
                token_freq[t] = token_freq.get(t, 0) + 1

            # Relevance: sum of (TF for matching query tokens) + keyword bonus
            relevance = 0.0
            for qt in query_tokens:
                tf = token_freq.get(qt, 0)
                if tf > 0:
                    relevance += 1.0 + math.log1p(tf)
                if qt in keyword_set:
                    relevance += 2.0  # keyword match bonus

            if relevance == 0:
                continue

            # Recency decay: half-life of 30 days
            age_days = max(0, (now - entry.created_at).total_seconds() / 86400)
            recency = math.exp(-0.023 * age_days)  # ~0.5 at 30 days

            final_score = relevance * entry.importance * recency
            scored.append((final_score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _score, entry in scored[:limit]]

    # ------------------------------------------------------------------
    # Conversation summarization
    # ------------------------------------------------------------------

    async def summarize_conversation(
        self,
        messages: list[dict[str, Any]],
        llm_registry: Any | None = None,
    ) -> MemoryEntry:
        """Summarize a conversation and store as CONVERSATION memory."""
        conversation_text = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages
        )

        if llm_registry is not None:
            summary = await self._llm_summarize(conversation_text, llm_registry)
        else:
            # Fallback: take the last few messages as summary
            recent = messages[-3:] if len(messages) > 3 else messages
            summary = "Conversation summary: " + "; ".join(
                m.get("content", "")[:100] for m in recent
            )

        return await self.add(
            content=summary,
            memory_type=MemoryType.CONVERSATION,
            metadata={
                "message_count": len(messages),
                "summarized_at": datetime.now(timezone.utc).isoformat(),
            },
            llm_registry=llm_registry,
        )

    async def _llm_summarize(self, conversation_text: str, llm_registry: Any) -> str:
        from jarvis.llm.provider import Message, Role

        try:
            provider = llm_registry.get()
            prompt = _SUMMARIZE_PROMPT.format(conversation=conversation_text[:4000])
            response = await provider.chat(
                messages=[Message(role=Role.USER, content=prompt)],
                temperature=0.3,
                max_tokens=512,
            )
            return response.content.strip()
        except Exception:
            logger.warning("LLM conversation summarization failed", exc_info=True)
            return f"Conversation ({len(conversation_text)} chars, summarization failed)"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load all memories from disk."""
        self._memories.clear()
        if not self._storage_path.exists():
            self._loaded = True
            return

        count = 0
        for fp in self._storage_path.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                entry = MemoryEntry.from_dict(data)
                self._memories[entry.id] = entry
                count += 1
            except Exception:
                logger.warning("Failed to load memory file: %s", fp, exc_info=True)

        self._loaded = True
        logger.info("Loaded %d memories from %s", count, self._storage_path)

    def save(self) -> None:
        """Persist all memories to disk."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        for entry in self._memories.values():
            self._save_entry(entry)
        logger.info("Saved %d memories to %s", len(self._memories), self._storage_path)

    def _save_entry(self, entry: MemoryEntry) -> None:
        """Write a single memory entry to disk."""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        fp = self._storage_path / f"{entry.id}.json"
        fp.write_text(
            json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Context for LLM prompts
    # ------------------------------------------------------------------

    def get_context(self, limit: int = 10) -> str:
        """Format recent/important memories as context string for LLM prompts."""
        self._ensure_loaded()
        if not self._memories:
            return ""

        # Sort by importance * recency
        now = datetime.now(timezone.utc)
        ranked = sorted(
            self._memories.values(),
            key=lambda e: e.importance * math.exp(
                -0.023 * max(0, (now - e.created_at).total_seconds() / 86400)
            ),
            reverse=True,
        )

        lines: list[str] = ["# Relevant Memories"]
        for entry in ranked[:limit]:
            age = (now - entry.created_at).total_seconds() / 86400
            age_str = f"{int(age)}d ago" if age >= 1 else "today"
            lines.append(
                f"- [{entry.memory_type.value}] ({age_str}, importance={entry.importance:.1f}) "
                f"{entry.content[:200]}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune(self, max_age_days: int = 90) -> int:
        """Remove old low-importance memories. Returns count of pruned entries."""
        self._ensure_loaded()
        now = datetime.now(timezone.utc)
        to_remove: list[str] = []

        for mid, entry in self._memories.items():
            age_days = (now - entry.created_at).total_seconds() / 86400
            if age_days > max_age_days and entry.importance < 0.5:
                to_remove.append(mid)

        for mid in to_remove:
            # Remove file
            fp = self._storage_path / f"{mid}.json"
            if fp.exists():
                fp.unlink()
            del self._memories[mid]

        if to_remove:
            logger.info("Pruned %d old low-importance memories", len(to_remove))
        return len(to_remove)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_memories(self, memory_type: MemoryType | None = None) -> list[MemoryEntry]:
        """List all memories, optionally filtered by type."""
        self._ensure_loaded()
        if memory_type is None:
            return list(self._memories.values())
        return [e for e in self._memories.values() if e.memory_type == memory_type]
