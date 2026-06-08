"""File-based JSON storage backend.

Each key maps to a JSON file in the storage directory.
Supports atomic writes, TTL-based expiry, field search, and basic indexing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.storage.base import Store


class JSONStore(Store[dict]):
    """File-based JSON storage.

    Each key maps to a JSON file in the storage directory.

    Features:
        - CRUD operations on JSON files
        - Key prefix listing (directory-based)
        - Atomic writes (write to temp file, then rename)
        - Optional in-memory index for metadata
        - TTL-based expiry
        - Field-level search across stored values
    """

    def __init__(self, base_path: str, ttl_seconds: int | None = None) -> None:
        self._base = Path(base_path).expanduser()
        self._base.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds
        self._index: dict[str, dict[str, Any]] = {}  # key -> metadata

    # ------------------------------------------------------------------
    # Key / path mapping
    # ------------------------------------------------------------------

    def _key_to_path(self, key: str) -> Path:
        """Convert a logical key to its filesystem path."""
        safe_key = key.replace("/", "__")
        return self._base / f"{safe_key}.json"

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    async def get(self, key: str) -> dict | None:
        path = self._key_to_path(key)
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))

        # Check TTL
        if self._ttl and "_stored_at" in data:
            stored = datetime.fromisoformat(data["_stored_at"])
            if stored.tzinfo is None:
                stored = stored.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - stored).total_seconds() > self._ttl:
                path.unlink()
                self._index.pop(key, None)
                return None

        return data.get("_value", data)

    async def put(self, key: str, value: dict) -> None:
        path = self._key_to_path(key)
        wrapper = {
            "_key": key,
            "_stored_at": datetime.now(timezone.utc).isoformat(),
            "_value": value,
        }
        # Atomic write: write to .tmp then rename
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(wrapper, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        tmp_path.rename(path)

        # Update in-memory index
        self._index[key] = {
            "stored_at": wrapper["_stored_at"],
            "size": path.stat().st_size,
        }

    async def delete(self, key: str) -> bool:
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()
            self._index.pop(key, None)
            return True
        return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        for fp in self._base.glob("*.json"):
            key = fp.stem.replace("__", "/")
            if not prefix or key.startswith(prefix):
                keys.append(key)
        return sorted(keys)

    async def exists(self, key: str) -> bool:
        return self._key_to_path(key).exists()

    # ------------------------------------------------------------------
    # Extended operations
    # ------------------------------------------------------------------

    async def search(self, query: dict[str, Any]) -> list[dict]:
        """Search stored values by matching fields.

        Args:
            query: dict of {field: expected_value} pairs. All must match.

        Returns:
            List of matching stored values.
        """
        results: list[dict] = []
        for fp in self._base.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            value = data.get("_value", data)
            if not isinstance(value, dict):
                continue
            match = all(value.get(field) == expected for field, expected in query.items())
            if match:
                results.append(value)
        return results

    async def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        if not self._ttl:
            return 0
        removed = 0
        now = datetime.now(timezone.utc)
        for fp in self._base.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                stored_str = data.get("_stored_at", "")
                if not stored_str:
                    continue
                stored = datetime.fromisoformat(stored_str)
                if stored.tzinfo is None:
                    stored = stored.replace(tzinfo=timezone.utc)
                if (now - stored).total_seconds() > self._ttl:
                    fp.unlink()
                    # Also clean index
                    key = fp.stem.replace("__", "/")
                    self._index.pop(key, None)
                    removed += 1
            except Exception:
                pass
        return removed

    def stats(self) -> dict:
        """Return storage statistics."""
        files = list(self._base.glob("*.json"))
        count = len(files)
        total_size = sum(fp.stat().st_size for fp in files)
        return {
            "count": count,
            "total_size_bytes": total_size,
            "path": str(self._base),
        }
