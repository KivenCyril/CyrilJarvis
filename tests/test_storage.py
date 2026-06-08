"""Tests for the JARVIS data persistence layer (storage package).

Covers MemoryStore, JSONStore, SQLiteStore, and the KeyValueStore facade.
30+ test cases.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from jarvis.storage.base import Store, StorageBackend
from jarvis.storage.memory_store import MemoryStore
from jarvis.storage.json_store import JSONStore
from jarvis.storage.sqlite_store import SQLiteStore
from jarvis.storage.kv import KeyValueStore


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def memory_store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def json_store(tmp_path: Path) -> JSONStore:
    return JSONStore(base_path=str(tmp_path / "json_data"))


@pytest.fixture
def json_store_ttl(tmp_path: Path) -> JSONStore:
    return JSONStore(base_path=str(tmp_path / "json_ttl"), ttl_seconds=1)


@pytest.fixture
def sqlite_store(tmp_path: Path) -> SQLiteStore:
    return SQLiteStore(db_path=str(tmp_path / "test.db"))


# ======================================================================
# MemoryStore tests
# ======================================================================

@pytest.mark.asyncio
async def test_memory_put_get(memory_store: MemoryStore) -> None:
    await memory_store.put("k1", {"a": 1})
    result = await memory_store.get("k1")
    assert result == {"a": 1}


@pytest.mark.asyncio
async def test_memory_get_missing(memory_store: MemoryStore) -> None:
    assert await memory_store.get("nonexistent") is None


@pytest.mark.asyncio
async def test_memory_delete(memory_store: MemoryStore) -> None:
    await memory_store.put("k1", {"a": 1})
    assert await memory_store.delete("k1") is True
    assert await memory_store.get("k1") is None


@pytest.mark.asyncio
async def test_memory_delete_missing(memory_store: MemoryStore) -> None:
    assert await memory_store.delete("nope") is False


@pytest.mark.asyncio
async def test_memory_exists(memory_store: MemoryStore) -> None:
    assert await memory_store.exists("k1") is False
    await memory_store.put("k1", {"a": 1})
    assert await memory_store.exists("k1") is True


@pytest.mark.asyncio
async def test_memory_list_keys(memory_store: MemoryStore) -> None:
    await memory_store.put("user:1", {"name": "a"})
    await memory_store.put("user:2", {"name": "b"})
    await memory_store.put("task:1", {"name": "c"})
    assert await memory_store.list_keys("user:") == ["user:1", "user:2"]
    assert len(await memory_store.list_keys()) == 3


@pytest.mark.asyncio
async def test_memory_count(memory_store: MemoryStore) -> None:
    await memory_store.put("a", {})
    await memory_store.put("b", {})
    assert await memory_store.count() == 2
    assert await memory_store.count("a") == 1


@pytest.mark.asyncio
async def test_memory_put_many_get_many(memory_store: MemoryStore) -> None:
    await memory_store.put_many({"x": {"v": 1}, "y": {"v": 2}})
    result = await memory_store.get_many(["x", "y", "z"])
    assert result["x"] == {"v": 1}
    assert result["y"] == {"v": 2}
    assert result["z"] is None


@pytest.mark.asyncio
async def test_memory_deep_copy_isolation(memory_store: MemoryStore) -> None:
    """Mutating the returned dict must not affect stored data."""
    await memory_store.put("k", {"list": [1, 2, 3]})
    val = await memory_store.get("k")
    assert val is not None
    val["list"].append(4)
    val2 = await memory_store.get("k")
    assert val2 == {"list": [1, 2, 3]}


@pytest.mark.asyncio
async def test_memory_clear(memory_store: MemoryStore) -> None:
    await memory_store.put("a", {})
    memory_store.clear()
    assert await memory_store.count() == 0


@pytest.mark.asyncio
async def test_memory_search(memory_store: MemoryStore) -> None:
    await memory_store.put("u1", {"role": "admin", "name": "alice"})
    await memory_store.put("u2", {"role": "user", "name": "bob"})
    results = memory_store.search({"role": "admin"})
    assert len(results) == 1
    assert results[0]["name"] == "alice"


# ======================================================================
# JSONStore tests
# ======================================================================

@pytest.mark.asyncio
async def test_json_put_get(json_store: JSONStore) -> None:
    await json_store.put("doc1", {"title": "hello"})
    result = await json_store.get("doc1")
    assert result == {"title": "hello"}


@pytest.mark.asyncio
async def test_json_get_missing(json_store: JSONStore) -> None:
    assert await json_store.get("missing") is None


@pytest.mark.asyncio
async def test_json_delete(json_store: JSONStore) -> None:
    await json_store.put("d", {"x": 1})
    assert await json_store.delete("d") is True
    assert await json_store.get("d") is None
    assert await json_store.delete("d") is False


@pytest.mark.asyncio
async def test_json_exists(json_store: JSONStore) -> None:
    assert await json_store.exists("k") is False
    await json_store.put("k", {"a": 1})
    assert await json_store.exists("k") is True


@pytest.mark.asyncio
async def test_json_list_keys(json_store: JSONStore) -> None:
    await json_store.put("ns/a", {"v": 1})
    await json_store.put("ns/b", {"v": 2})
    await json_store.put("other", {"v": 3})
    keys = await json_store.list_keys("ns/")
    assert keys == ["ns/a", "ns/b"]


@pytest.mark.asyncio
async def test_json_overwrite(json_store: JSONStore) -> None:
    await json_store.put("k", {"v": 1})
    await json_store.put("k", {"v": 2})
    assert (await json_store.get("k")) == {"v": 2}


@pytest.mark.asyncio
async def test_json_search(json_store: JSONStore) -> None:
    await json_store.put("u1", {"role": "admin", "name": "alice"})
    await json_store.put("u2", {"role": "user", "name": "bob"})
    results = await json_store.search({"role": "admin"})
    assert len(results) == 1
    assert results[0]["name"] == "alice"


@pytest.mark.asyncio
async def test_json_stats(json_store: JSONStore) -> None:
    await json_store.put("a", {"x": 1})
    await json_store.put("b", {"x": 2})
    stats = json_store.stats()
    assert stats["count"] == 2
    assert stats["total_size_bytes"] > 0


@pytest.mark.asyncio
async def test_json_ttl_expiry(json_store_ttl: JSONStore) -> None:
    await json_store_ttl.put("temp", {"val": 42})
    assert (await json_store_ttl.get("temp")) == {"val": 42}
    # Wait for TTL to expire (1 second)
    import asyncio
    await asyncio.sleep(1.1)
    assert await json_store_ttl.get("temp") is None


@pytest.mark.asyncio
async def test_json_cleanup_expired(json_store_ttl: JSONStore) -> None:
    await json_store_ttl.put("e1", {"a": 1})
    await json_store_ttl.put("e2", {"a": 2})
    import asyncio
    await asyncio.sleep(1.1)
    removed = await json_store_ttl.cleanup_expired()
    assert removed == 2


@pytest.mark.asyncio
async def test_json_atomic_write(json_store: JSONStore) -> None:
    """After put, no .tmp files should remain."""
    await json_store.put("atomic", {"data": "test"})
    tmp_files = list(json_store._base.glob("*.tmp"))
    assert len(tmp_files) == 0


# ======================================================================
# SQLiteStore tests
# ======================================================================

@pytest.mark.asyncio
async def test_sqlite_put_get(sqlite_store: SQLiteStore) -> None:
    await sqlite_store.put("k1", {"val": 100})
    result = await sqlite_store.get("k1")
    assert result == {"val": 100}


@pytest.mark.asyncio
async def test_sqlite_get_missing(sqlite_store: SQLiteStore) -> None:
    assert await sqlite_store.get("nope") is None


@pytest.mark.asyncio
async def test_sqlite_delete(sqlite_store: SQLiteStore) -> None:
    await sqlite_store.put("d", {"x": 1})
    assert await sqlite_store.delete("d") is True
    assert await sqlite_store.delete("d") is False


@pytest.mark.asyncio
async def test_sqlite_exists(sqlite_store: SQLiteStore) -> None:
    assert await sqlite_store.exists("k") is False
    await sqlite_store.put("k", {})
    assert await sqlite_store.exists("k") is True


@pytest.mark.asyncio
async def test_sqlite_list_keys(sqlite_store: SQLiteStore) -> None:
    await sqlite_store.put("ns:a", {})
    await sqlite_store.put("ns:b", {})
    await sqlite_store.put("other", {})
    keys = await sqlite_store.list_keys("ns:")
    assert keys == ["ns:a", "ns:b"]
    assert len(await sqlite_store.list_keys()) == 3


@pytest.mark.asyncio
async def test_sqlite_overwrite(sqlite_store: SQLiteStore) -> None:
    await sqlite_store.put("k", {"v": 1})
    await sqlite_store.put("k", {"v": 2})
    assert (await sqlite_store.get("k")) == {"v": 2}


@pytest.mark.asyncio
async def test_sqlite_count(sqlite_store: SQLiteStore) -> None:
    await sqlite_store.put("a", {})
    await sqlite_store.put("b", {})
    assert await sqlite_store.count() == 2
    assert await sqlite_store.count("a") == 1


@pytest.mark.asyncio
async def test_sqlite_search_values(sqlite_store: SQLiteStore) -> None:
    await sqlite_store.put("u1", {"role": "admin", "name": "alice"})
    await sqlite_store.put("u2", {"role": "user", "name": "bob"})
    results = await sqlite_store.search_values("role", "admin")
    assert len(results) == 1
    assert results[0]["name"] == "alice"


@pytest.mark.asyncio
async def test_sqlite_stats(sqlite_store: SQLiteStore) -> None:
    await sqlite_store.put("x", {"v": 1})
    stats = sqlite_store.stats()
    assert stats["count"] == 1
    assert stats["size_bytes"] > 0


# ======================================================================
# KeyValueStore facade tests
# ======================================================================

@pytest.mark.asyncio
async def test_kv_memory_backend() -> None:
    kv = KeyValueStore(backend="memory")
    await kv.set("key", {"val": 1})
    assert await kv.get("key") == {"val": 1}
    assert kv.backend == StorageBackend.MEMORY


@pytest.mark.asyncio
async def test_kv_json_backend(tmp_path: Path) -> None:
    kv = KeyValueStore(backend="json", base_path=str(tmp_path / "kv_json"))
    await kv.set("hello", {"msg": "world"})
    assert await kv.get("hello") == {"msg": "world"}
    assert kv.backend == StorageBackend.JSON


@pytest.mark.asyncio
async def test_kv_sqlite_backend(tmp_path: Path) -> None:
    kv = KeyValueStore(backend="sqlite", db_path=str(tmp_path / "kv.db"))
    await kv.set("hello", {"msg": "world"})
    assert await kv.get("hello") == {"msg": "world"}
    assert kv.backend == StorageBackend.SQLITE


@pytest.mark.asyncio
async def test_kv_delete_and_exists(tmp_path: Path) -> None:
    kv = KeyValueStore(backend="memory")
    await kv.set("k", {"a": 1})
    assert await kv.exists("k") is True
    assert await kv.delete("k") is True
    assert await kv.exists("k") is False


@pytest.mark.asyncio
async def test_kv_keys_and_count() -> None:
    kv = KeyValueStore(backend="memory")
    await kv.set("user:1", {"n": "a"})
    await kv.set("user:2", {"n": "b"})
    await kv.set("task:1", {"n": "c"})
    assert await kv.keys("user:") == ["user:1", "user:2"]
    assert await kv.count() == 3


@pytest.mark.asyncio
async def test_kv_set_many_get_many() -> None:
    kv = KeyValueStore(backend="memory")
    await kv.set_many({"a": {"v": 1}, "b": {"v": 2}})
    result = await kv.get_many(["a", "b", "c"])
    assert result["a"] == {"v": 1}
    assert result["c"] is None


def test_kv_invalid_backend() -> None:
    with pytest.raises(ValueError):
        KeyValueStore(backend="redis")


# ======================================================================
# StorageBackend enum tests
# ======================================================================

def test_storage_backend_values() -> None:
    assert StorageBackend.JSON.value == "json"
    assert StorageBackend.SQLITE.value == "sqlite"
    assert StorageBackend.MEMORY.value == "memory"


def test_storage_backend_from_string() -> None:
    assert StorageBackend("json") == StorageBackend.JSON
