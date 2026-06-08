"""Storage abstraction layer for JARVIS.

Defines the abstract Store interface that all storage backends implement,
along with the StorageBackend enum for backend selection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class StorageBackend(str, Enum):
    """Supported storage backends."""

    JSON = "json"
    SQLITE = "sqlite"
    MEMORY = "memory"


class Store(ABC, Generic[T]):
    """Abstract storage interface for persistent data.

    All storage backends must implement the core CRUD operations:
    get, put, delete, list_keys, exists.

    Batch operations (get_many, put_many) and count have default
    implementations that subclasses may override for efficiency.
    """

    @abstractmethod
    async def get(self, key: str) -> T | None:
        """Retrieve a value by key. Returns None if not found."""
        ...

    @abstractmethod
    async def put(self, key: str, value: T) -> None:
        """Store a value under the given key."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if the key existed."""
        ...

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        ...

    # --- default batch helpers ---

    async def get_many(self, keys: list[str]) -> dict[str, T | None]:
        """Retrieve multiple values at once."""
        return {k: await self.get(k) for k in keys}

    async def put_many(self, items: dict[str, T]) -> None:
        """Store multiple key-value pairs at once."""
        for k, v in items.items():
            await self.put(k, v)

    async def count(self, prefix: str = "") -> int:
        """Return the number of keys matching the prefix."""
        return len(await self.list_keys(prefix))
