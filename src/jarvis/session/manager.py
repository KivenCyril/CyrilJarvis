from __future__ import annotations
import json, logging, uuid, time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

class SessionState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXPIRED = "expired"

class SessionMessage(BaseModel):
    """A message within a session."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    role: str  # user, agent, system
    content: str
    agent_name: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

class Session(BaseModel):
    """A conversation session with full history tracking.

    Sessions track:
    - Full conversation history (messages)
    - Which agents were involved
    - Which specs were created/executed
    - Performance metrics
    - User context
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    state: SessionState = SessionState.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

    # Conversation
    messages: list[SessionMessage] = Field(default_factory=list)

    # Context
    user_id: str = "default"
    channel: str = "cli"  # cli, web, api, telegram, etc.
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Tracking
    spec_ids: list[str] = Field(default_factory=list)
    agents_used: list[str] = Field(default_factory=list)
    tool_calls: int = 0
    total_tokens: int = 0
    total_duration_ms: int = 0

    def add_message(self, role: str, content: str, agent_name: str = "", **meta) -> SessionMessage:
        msg = SessionMessage(role=role, content=content, agent_name=agent_name, metadata=meta)
        self.messages.append(msg)
        self.updated_at = datetime.now(timezone.utc)
        if agent_name and agent_name not in self.agents_used:
            self.agents_used.append(agent_name)
        return msg

    def add_spec(self, spec_id: str) -> None:
        if spec_id not in self.spec_ids:
            self.spec_ids.append(spec_id)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def duration_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    def to_context_string(self, max_messages: int = 20) -> str:
        """Format recent messages as context for agents."""
        recent = self.messages[-max_messages:]
        lines = []
        for msg in recent:
            prefix = msg.role.capitalize()
            if msg.agent_name:
                prefix = f"{msg.agent_name}"
            lines.append(f"[{prefix}] {msg.content[:500]}")
        return "\n".join(lines)

class SessionManager:
    """Manages conversation sessions with persistence.

    Features:
    - Session creation and lifecycle management
    - Session persistence (JSON files)
    - Session expiry
    - Session search and listing
    - Metrics aggregation across sessions
    """

    def __init__(self, storage_path: str = "~/.jarvis/sessions"):
        self._sessions: dict[str, Session] = {}
        self._storage_path = Path(storage_path).expanduser()
        self._active_session_id: str | None = None

    def create(self, user_id: str = "default", channel: str = "cli", **metadata) -> Session:
        session = Session(user_id=user_id, channel=channel, metadata=metadata)
        self._sessions[session.id] = session
        self._active_session_id = session.id
        logger.info("Session created: %s (user=%s, channel=%s)", session.id[:8], user_id, channel)
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    @property
    def active_session(self) -> Session | None:
        if self._active_session_id:
            return self._sessions.get(self._active_session_id)
        return None

    def list_sessions(self, state: SessionState | None = None, limit: int = 50) -> list[Session]:
        sessions = list(self._sessions.values())
        if state:
            sessions = [s for s in sessions if s.state == state]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions[:limit]

    def complete(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.state = SessionState.COMPLETED
            self._save_session(session)
            if self._active_session_id == session_id:
                self._active_session_id = None

    def expire_old(self, max_idle_hours: int = 24) -> int:
        """Expire sessions that have been idle too long."""
        now = datetime.now(timezone.utc)
        expired = 0
        for session in list(self._sessions.values()):
            if session.state == SessionState.ACTIVE:
                idle = (now - session.updated_at).total_seconds() / 3600
                if idle > max_idle_hours:
                    session.state = SessionState.EXPIRED
                    self._save_session(session)
                    expired += 1
        return expired

    def save_all(self) -> None:
        self._storage_path.mkdir(parents=True, exist_ok=True)
        for session in self._sessions.values():
            self._save_session(session)

    def _save_session(self, session: Session) -> None:
        self._storage_path.mkdir(parents=True, exist_ok=True)
        fp = self._storage_path / f"{session.id}.json"
        fp.write_text(
            session.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> int:
        if not self._storage_path.exists():
            return 0
        count = 0
        for fp in self._storage_path.glob("*.json"):
            try:
                session = Session.model_validate_json(fp.read_text(encoding="utf-8"))
                self._sessions[session.id] = session
                count += 1
            except Exception:
                logger.warning("Failed to load session: %s", fp)
        return count

    # Metrics
    def get_metrics(self) -> dict[str, Any]:
        total = len(self._sessions)
        active = sum(1 for s in self._sessions.values() if s.state == SessionState.ACTIVE)
        total_messages = sum(s.message_count for s in self._sessions.values())
        total_tokens = sum(s.total_tokens for s in self._sessions.values())
        agents_used: dict[str, int] = {}
        for s in self._sessions.values():
            for a in s.agents_used:
                agents_used[a] = agents_used.get(a, 0) + 1

        return {
            "total_sessions": total,
            "active_sessions": active,
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "agents_usage": agents_used,
        }
