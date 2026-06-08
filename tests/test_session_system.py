"""Session management system tests.

Tests session creation, state management, message tracking,
agent usage recording, metrics, and session lifecycle.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Session Models
# ---------------------------------------------------------------------------

@dataclass
class SessionMessage:
    role: str  # user, assistant, system
    content: str
    agent: str | None = None
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "agent": self.agent,
            "timestamp": self.timestamp,
        }


@dataclass
class Session:
    id: str
    state: str = "active"  # active, idle, closed
    user_id: str = "anonymous"
    channel: str = "api"  # api, cli, web, ws
    messages: list[SessionMessage] = field(default_factory=list)
    agents_used: list[str] = field(default_factory=list)
    specs_created: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    closed_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def user_message_count(self) -> int:
        return sum(1 for m in self.messages if m.role == "user")

    @property
    def assistant_message_count(self) -> int:
        return sum(1 for m in self.messages if m.role == "assistant")

    @property
    def unique_agents_count(self) -> int:
        return len(set(self.agents_used))

    @property
    def is_active(self) -> bool:
        return self.state == "active"

    def add_message(self, role: str, content: str, agent: str | None = None) -> SessionMessage:
        msg = SessionMessage(role=role, content=content, agent=agent)
        self.messages.append(msg)
        self.updated_at = datetime.datetime.utcnow().isoformat()
        if agent and agent not in self.agents_used:
            self.agents_used.append(agent)
        return msg

    def record_tool_use(self, tool_name: str) -> None:
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)

    def record_spec(self, spec_id: str) -> None:
        if spec_id not in self.specs_created:
            self.specs_created.append(spec_id)

    def close(self) -> None:
        self.state = "closed"
        self.closed_at = datetime.datetime.utcnow().isoformat()

    def idle(self) -> None:
        self.state = "idle"

    def reactivate(self) -> None:
        self.state = "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "user_id": self.user_id,
            "channel": self.channel,
            "message_count": self.message_count,
            "agents_used": self.agents_used,
            "specs_created": self.specs_created,
            "tools_used": self.tools_used,
            "created_at": self.created_at,
        }


class SessionManager:
    """Manage user sessions."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self._counter = 0

    def create(self, user_id: str = "anonymous",
               channel: str = "api") -> Session:
        self._counter += 1
        session = Session(
            id=f"session-{self._counter:04d}",
            user_id=user_id,
            channel=channel,
        )
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def list_sessions(self, state: str | None = None,
                      user_id: str | None = None,
                      limit: int = 50) -> list[Session]:
        result = list(self.sessions.values())
        if state:
            result = [s for s in result if s.state == state]
        if user_id:
            result = [s for s in result if s.user_id == user_id]
        return result[-limit:]

    def close_session(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if session:
            session.close()
            return True
        return False

    def close_idle(self) -> int:
        closed = 0
        for session in self.sessions.values():
            if session.state == "idle":
                session.close()
                closed += 1
        return closed

    def get_metrics(self) -> dict[str, Any]:
        total = len(self.sessions)
        active = sum(1 for s in self.sessions.values() if s.state == "active")
        idle = sum(1 for s in self.sessions.values() if s.state == "idle")
        closed = sum(1 for s in self.sessions.values() if s.state == "closed")
        total_messages = sum(s.message_count for s in self.sessions.values())
        channels: dict[str, int] = {}
        for s in self.sessions.values():
            channels[s.channel] = channels.get(s.channel, 0) + 1
        return {
            "total_sessions": total,
            "active": active,
            "idle": idle,
            "closed": closed,
            "total_messages": total_messages,
            "avg_messages": round(total_messages / total, 1) if total else 0,
            "channels": channels,
        }


# ---------------------------------------------------------------------------
# Tests: SessionMessage
# ---------------------------------------------------------------------------

class TestSessionMessage:
    def test_create_message(self):
        msg = SessionMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp != ""

    def test_message_with_agent(self):
        msg = SessionMessage(role="assistant", content="Hi", agent="code-agent")
        assert msg.agent == "code-agent"

    def test_to_dict(self):
        msg = SessionMessage(role="user", content="Test")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Test"


# ---------------------------------------------------------------------------
# Tests: Session
# ---------------------------------------------------------------------------

class TestSession:
    def test_create_session(self):
        s = Session(id="s1")
        assert s.state == "active"
        assert s.message_count == 0

    def test_add_messages(self):
        s = Session(id="s1")
        s.add_message("user", "Hello")
        s.add_message("assistant", "Hi there!")
        assert s.message_count == 2
        assert s.user_message_count == 1
        assert s.assistant_message_count == 1

    def test_agent_tracking(self):
        s = Session(id="s1")
        s.add_message("assistant", "Code review done", agent="code-agent")
        s.add_message("assistant", "Research complete", agent="research-agent")
        s.add_message("assistant", "More code", agent="code-agent")
        assert s.unique_agents_count == 2

    def test_tool_tracking(self):
        s = Session(id="s1")
        s.record_tool_use("shell")
        s.record_tool_use("git_status")
        s.record_tool_use("shell")  # duplicate
        assert len(s.tools_used) == 2

    def test_spec_tracking(self):
        s = Session(id="s1")
        s.record_spec("spec-001")
        s.record_spec("spec-002")
        assert len(s.specs_created) == 2

    def test_close_session(self):
        s = Session(id="s1")
        s.close()
        assert s.state == "closed"
        assert s.closed_at is not None

    def test_idle_and_reactivate(self):
        s = Session(id="s1")
        s.idle()
        assert s.state == "idle"
        assert s.is_active is False
        s.reactivate()
        assert s.state == "active"
        assert s.is_active is True

    def test_to_dict(self):
        s = Session(id="s1", user_id="alice")
        s.add_message("user", "Hello")
        d = s.to_dict()
        assert d["id"] == "s1"
        assert d["user_id"] == "alice"
        assert d["message_count"] == 1

    def test_channels(self):
        for ch in ["api", "cli", "web", "ws"]:
            s = Session(id="s1", channel=ch)
            assert s.channel == ch


# ---------------------------------------------------------------------------
# Tests: SessionManager
# ---------------------------------------------------------------------------

class TestSessionManager:
    def test_create_session(self):
        mgr = SessionManager()
        s = mgr.create(user_id="alice")
        assert s.id == "session-0001"
        assert s.user_id == "alice"

    def test_get_session(self):
        mgr = SessionManager()
        s = mgr.create()
        found = mgr.get(s.id)
        assert found is not None

    def test_get_nonexistent(self):
        mgr = SessionManager()
        assert mgr.get("missing") is None

    def test_list_sessions(self):
        mgr = SessionManager()
        mgr.create(user_id="alice")
        mgr.create(user_id="bob")
        assert len(mgr.list_sessions()) == 2

    def test_list_by_state(self):
        mgr = SessionManager()
        s1 = mgr.create()
        s2 = mgr.create()
        s2.close()
        active = mgr.list_sessions(state="active")
        assert len(active) == 1

    def test_list_by_user(self):
        mgr = SessionManager()
        mgr.create(user_id="alice")
        mgr.create(user_id="bob")
        mgr.create(user_id="alice")
        alice = mgr.list_sessions(user_id="alice")
        assert len(alice) == 2

    def test_close_session(self):
        mgr = SessionManager()
        s = mgr.create()
        assert mgr.close_session(s.id) is True
        assert s.state == "closed"

    def test_close_nonexistent(self):
        mgr = SessionManager()
        assert mgr.close_session("missing") is False

    def test_close_idle(self):
        mgr = SessionManager()
        s1 = mgr.create()
        s2 = mgr.create()
        s3 = mgr.create()
        s1.idle()
        s2.idle()
        closed = mgr.close_idle()
        assert closed == 2

    def test_metrics(self):
        mgr = SessionManager()
        s1 = mgr.create(channel="api")
        s2 = mgr.create(channel="web")
        s1.add_message("user", "Hello")
        s1.add_message("assistant", "Hi")
        s2.add_message("user", "Test")
        metrics = mgr.get_metrics()
        assert metrics["total_sessions"] == 2
        assert metrics["active"] == 2
        assert metrics["total_messages"] == 3
        assert metrics["avg_messages"] == 1.5
        assert "api" in metrics["channels"]
        assert "web" in metrics["channels"]

    def test_multiple_users(self):
        mgr = SessionManager()
        for user in ["alice", "bob", "charlie"]:
            s = mgr.create(user_id=user)
            s.add_message("user", f"Hello from {user}")
        assert len(mgr.list_sessions()) == 3
