"""In-memory storage backend.

Useful for testing and for temporary data that does not need to survive
process restarts.
"""

from __future__ import annotations

import copy
from typing import Any

from jarvis.storage.base import Store


class MemoryStore(Store[dict]):
    """In-memory storage for testing and temporary data.

    All data lives in a plain Python dict and is lost when the
    process exits.  Values are deep-copied on read/write to avoid
    accidental mutation of stored data.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    async def get(self, key: str) -> dict | None:
        value = self._data.get(key)
        if value is not None:
            return copy.deepcopy(value)
        return None

    async def put(self, key: str, value: dict) -> None:
        self._data[key] = copy.deepcopy(value)

    async def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        keys = [k for k in self._data if not prefix or k.startswith(prefix)]
        return sorted(keys)

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def get_many(self, keys: list[str]) -> dict[str, dict | None]:
        return {k: copy.deepcopy(self._data.get(k)) for k in keys}

    async def put_many(self, items: dict[str, dict]) -> None:
        for k, v in items.items():
            self._data[k] = copy.deepcopy(v)

    async def count(self, prefix: str = "") -> int:
        if not prefix:
            return len(self._data)
        return sum(1 for k in self._data if k.startswith(prefix))

    def clear(self) -> None:
        """Remove all stored data."""
        self._data.clear()

    def search(self, query: dict[str, Any]) -> list[dict]:
        """Synchronous field-level search across stored values."""
        results: list[dict] = []
        for value in self._data.values():
            if not isinstance(value, dict):
                continue
            if all(value.get(f) == v for f, v in query.items()):
                results.append(copy.deepcopy(value))
        return results
