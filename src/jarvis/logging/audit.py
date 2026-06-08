"""Immutable audit trail for security-sensitive operations.

Records authentication attempts, permission changes, tool executions
with dangerous operations, configuration changes, and data-access
patterns.  The on-disk format is append-only JSON-lines so that entries
cannot be silently modified after the fact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """A single audit record."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: str = ""
    user_id: str = ""
    resource: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    result: str = "success"  # success | failure | denied
    ip_address: str = ""


class AuditLogger:
    """Append-only audit logger backed by JSON-lines files.

    Each calendar day gets its own log file under *storage_path* to keep
    individual files manageable and to make retention policies trivial.
    """

    def __init__(self, storage_path: str = "~/.jarvis/audit") -> None:
        self._storage_path = Path(storage_path).expanduser()
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._entries: list[AuditEntry] = []

    # -- helpers -------------------------------------------------------------

    def _file_for_date(self, dt: datetime) -> Path:
        return self._storage_path / f"audit-{dt.strftime('%Y-%m-%d')}.jsonl"

    # -- public API ----------------------------------------------------------

    def log(
        self,
        action: str,
        user_id: str = "",
        resource: str = "",
        result: str = "success",
        **details: Any,
    ) -> AuditEntry:
        """Create and store an audit entry.

        Extra keyword arguments are stored in *details*.
        """
        entry = AuditEntry(
            action=action,
            user_id=user_id,
            resource=resource,
            result=result,
            details=details,
        )
        self._entries.append(entry)
        return entry

    def query(
        self,
        action: str = "",
        user_id: str = "",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query in-memory entries with optional filters."""
        results: list[AuditEntry] = []
        for entry in self._entries:
            if action and entry.action != action:
                continue
            if user_id and entry.user_id != user_id:
                continue
            if start and entry.timestamp < start:
                continue
            if end and entry.timestamp > end:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def save(self) -> None:
        """Flush all in-memory entries to the append-only audit log files."""
        by_date: dict[str, list[AuditEntry]] = {}
        for entry in self._entries:
            key = entry.timestamp.strftime("%Y-%m-%d")
            by_date.setdefault(key, []).append(entry)

        for _date_key, entries in by_date.items():
            if not entries:
                continue
            path = self._file_for_date(entries[0].timestamp)
            with open(path, "a", encoding="utf-8") as fh:
                for entry in entries:
                    fh.write(entry.model_dump_json() + "\n")

    def load(self) -> int:
        """Load entries from disk into memory. Returns count of loaded entries."""
        loaded = 0
        for fp in sorted(self._storage_path.glob("audit-*.jsonl")):
            with open(fp, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = AuditEntry.model_validate_json(line)
                        self._entries.append(entry)
                        loaded += 1
                    except Exception:  # noqa: BLE001
                        continue
        return loaded

    @property
    def entry_count(self) -> int:
        """Number of entries currently held in memory."""
        return len(self._entries)
