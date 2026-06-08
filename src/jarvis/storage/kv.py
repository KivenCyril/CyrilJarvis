"""High-level key-value store facade.

Provides a simple interface that delegates to the chosen storage backend.
"""

from __future__ import annotations

from jarvis.storage.base import StorageBackend
from jarvis.storage.json_store import JSONStore
from jarvis.storage.memory_store import MemoryStore
from jarvis.storage.sqlite_store import SQLiteStore


class KeyValueStore:
    """High-level key-value store with backend selection.

    Usage::

        kv = KeyValueStore(backend="json", base_path="~/.jarvis/data")
        await kv.set("user:prefs", {"theme": "dark"})
        prefs = await kv.get("user:prefs")
    """

    def __init__(self, backend: str = "json", **kwargs) -> None:
        backend_enum = StorageBackend(backend)
        if backend_enum == StorageBackend.JSON:
            self._store = JSONStore(**kwargs)
        elif backend_enum == StorageBackend.SQLITE:
            self._store = SQLiteStore(**kwargs)
        elif backend_enum == StorageBackend.MEMORY:
            self._store = MemoryStore()
        else:
            raise ValueError(f"Unknown backend: {backend}")
        self._backend = backend_enum

    @property
    def backend(self) -> StorageBackend:
        """Return the active backend type."""
        return self._backend

    async def get(self, key: str) -> dict | None:
        """Retrieve a value by key."""
        return await self._store.get(key)

    async def set(self, key: str, value: dict) -> None:
        """Store a value under the given key."""
        await self._store.put(key, value)

    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        return await self._store.delete(key)

    async def keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        return await self._store.list_keys(prefix)

    async def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        return await self._store.exists(key)

    async def count(self, prefix: str = "") -> int:
        """Return the number of keys matching the prefix."""
        return await self._store.count(prefix)

    async def get_many(self, keys: list[str]) -> dict[str, dict | None]:
        """Retrieve multiple values at once."""
        return await self._store.get_many(keys)

    async def set_many(self, items: dict[str, dict]) -> None:
        """Store multiple key-value pairs at once."""
        await self._store.put_many(items)
