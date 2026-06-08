"""SQLite-based persistent storage backend.

Uses a single SQLite database with a key-value table.
Supports JSON serialization, indexed metadata queries,
JSON field extraction via json_extract, and automatic table creation.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.storage.base import Store


class SQLiteStore(Store[dict]):
    """SQLite-based persistent storage.

    Features:
        - CRUD with JSON serialization
        - Search via SQLite json_extract
        - Indexed key column
        - Automatic table creation on first use
        - Stats (row count, db file size)
    """

    def __init__(self, db_path: str = "~/.jarvis/data.db") -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _ensure_db(self) -> None:
        """Create tables and indexes if they don't exist yet."""
        if self._initialized:
            return
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kv_key ON kv_store(key)")
            conn.commit()
        finally:
            conn.close()
        self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        """Return a new connection (callers must close it)."""
        self._ensure_db()
        return sqlite3.connect(str(self._db_path))

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    async def get(self, key: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value FROM kv_store WHERE key = ?", (key,)
            ).fetchone()
            if row:
                return json.loads(row[0])
            return None
        finally:
            conn.close()

    async def put(self, key: str, value: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, ensure_ascii=False, default=str)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO kv_store (key, value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
                """,
                (key, value_json, now, now, value_json, now),
            )
            conn.commit()
        finally:
            conn.close()

    async def delete(self, key: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    async def list_keys(self, prefix: str = "") -> list[str]:
        conn = self._connect()
        try:
            if prefix:
                rows = conn.execute(
                    "SELECT key FROM kv_store WHERE key LIKE ? ORDER BY key",
                    (prefix + "%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key FROM kv_store ORDER BY key"
                ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    async def exists(self, key: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM kv_store WHERE key = ?", (key,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Extended operations
    # ------------------------------------------------------------------

    async def search_values(self, field: str, value: Any) -> list[dict]:
        """Search JSON values by field using SQLite json_extract."""
        conn = self._connect()
        try:
            search_val: Any
            if isinstance(value, (int, float, str)):
                search_val = value
            else:
                search_val = json.dumps(value)
            rows = conn.execute(
                "SELECT value FROM kv_store WHERE json_extract(value, ?) = ?",
                (f"$.{field}", search_val),
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()

    async def count(self, prefix: str = "") -> int:
        """Optimized count using SQL COUNT."""
        conn = self._connect()
        try:
            if prefix:
                row = conn.execute(
                    "SELECT COUNT(*) FROM kv_store WHERE key LIKE ?",
                    (prefix + "%",),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM kv_store").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def stats(self) -> dict:
        """Return database statistics."""
        conn = self._connect()
        try:
            count = conn.execute("SELECT COUNT(*) FROM kv_store").fetchone()[0]
        finally:
            conn.close()
        size = os.path.getsize(str(self._db_path))
        return {
            "count": count,
            "size_bytes": size,
            "path": str(self._db_path),
        }
