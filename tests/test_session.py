"""Tests for session management."""
import pytest
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from jarvis.session import SessionManager, Session, SessionState
from jarvis.session.manager import SessionMessage


# ── Session lifecycle ──

class TestSession:
    def test_create_session_defaults(self):
        s = Session()
        assert s.state == SessionState.ACTIVE
        assert s.user_id == "default"
        assert s.channel == "cli"
        assert s.message_count == 0
        assert len(s.id) == 16

    def test_add_message(self):
        s = Session()
        msg = s.add_message("user", "Hello!")
        assert msg.role == "user"
        assert msg.content == "Hello!"
        assert s.message_count == 1

    def test_add_message_with_agent(self):
        s = Session()
        s.add_message("agent", "I can help", agent_name="planner")
        assert "planner" in s.agents_used
        # Adding same agent again should not duplicate
        s.add_message("agent", "Sure thing", agent_name="planner")
        assert s.agents_used.count("planner") == 1

    def test_add_message_updates_timestamp(self):
        s = Session()
        old_updated = s.updated_at
        time.sleep(0.01)
        s.add_message("user", "test")
        assert s.updated_at >= old_updated

    def test_add_spec(self):
        s = Session()
        s.add_spec("spec-001")
        s.add_spec("spec-002")
        s.add_spec("spec-001")  # duplicate
        assert s.spec_ids == ["spec-001", "spec-002"]

    def test_duration_seconds(self):
        s = Session()
        time.sleep(0.05)
        assert s.duration_seconds >= 0.04

    def test_to_context_string(self):
        s = Session()
        s.add_message("user", "Hello")
        s.add_message("agent", "Hi there", agent_name="planner")
        ctx = s.to_context_string()
        assert "[User] Hello" in ctx
        assert "[planner] Hi there" in ctx

    def test_to_context_string_max_messages(self):
        s = Session()
        for i in range(30):
            s.add_message("user", f"msg-{i}")
        ctx = s.to_context_string(max_messages=5)
        lines = ctx.strip().split("\n")
        assert len(lines) == 5
        assert "msg-25" in ctx
        assert "msg-0" not in ctx

    def test_message_metadata(self):
        s = Session()
        msg = s.add_message("user", "test", priority="high", source="api")
        assert msg.metadata["priority"] == "high"
        assert msg.metadata["source"] == "api"

    def test_serialization_roundtrip(self):
        s = Session(user_id="alice", channel="web")
        s.add_message("user", "Hello")
        s.add_spec("spec-1")
        dumped = s.model_dump_json()
        restored = Session.model_validate_json(dumped)
        assert restored.id == s.id
        assert restored.user_id == "alice"
        assert restored.channel == "web"
        assert restored.message_count == 1
        assert restored.spec_ids == ["spec-1"]


# ── SessionManager CRUD ──

class TestSessionManager:
    def test_create_and_get(self):
        mgr = SessionManager(storage_path="/tmp/jarvis_test_sessions_crud")
        s = mgr.create(user_id="bob", channel="api")
        assert mgr.get(s.id) is s
        assert mgr.active_session is s

    def test_get_nonexistent(self):
        mgr = SessionManager()
        assert mgr.get("does-not-exist") is None

    def test_active_session_none_initially(self):
        mgr = SessionManager()
        assert mgr.active_session is None

    def test_list_sessions(self):
        mgr = SessionManager()
        s1 = mgr.create(user_id="a")
        s2 = mgr.create(user_id="b")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_filter_by_state(self):
        mgr = SessionManager()
        s1 = mgr.create()
        s2 = mgr.create()
        mgr.complete(s1.id)
        active = mgr.list_sessions(state=SessionState.ACTIVE)
        completed = mgr.list_sessions(state=SessionState.COMPLETED)
        assert len(active) == 1
        assert len(completed) == 1

    def test_list_sessions_limit(self):
        mgr = SessionManager()
        for _ in range(10):
            mgr.create()
        assert len(mgr.list_sessions(limit=3)) == 3

    def test_complete_session(self):
        mgr = SessionManager(storage_path="/tmp/jarvis_test_sessions_complete")
        s = mgr.create()
        mgr.complete(s.id)
        assert s.state == SessionState.COMPLETED
        assert mgr.active_session is None

    def test_complete_nonexistent_is_noop(self):
        mgr = SessionManager()
        mgr.complete("nonexistent")  # should not raise


    # ── Expiry ──

    def test_expire_old(self):
        mgr = SessionManager(storage_path="/tmp/jarvis_test_sessions_expire")
        s = mgr.create()
        # Artificially set updated_at to 48 hours ago
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
        expired_count = mgr.expire_old(max_idle_hours=24)
        assert expired_count == 1
        assert s.state == SessionState.EXPIRED

    def test_expire_does_not_touch_recent(self):
        mgr = SessionManager()
        s = mgr.create()
        expired_count = mgr.expire_old(max_idle_hours=24)
        assert expired_count == 0
        assert s.state == SessionState.ACTIVE

    def test_expire_skips_non_active(self):
        mgr = SessionManager()
        s = mgr.create()
        s.state = SessionState.COMPLETED
        s.updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
        expired_count = mgr.expire_old(max_idle_hours=1)
        assert expired_count == 0


    # ── Persistence ──

    def test_save_and_load(self, tmp_path):
        storage = str(tmp_path / "sessions")
        mgr = SessionManager(storage_path=storage)
        s = mgr.create(user_id="test_user", channel="web")
        s.add_message("user", "hello")
        s.add_message("agent", "hi", agent_name="planner")
        mgr.save_all()

        # Load into new manager
        mgr2 = SessionManager(storage_path=storage)
        count = mgr2.load_all()
        assert count == 1
        loaded = mgr2.get(s.id)
        assert loaded is not None
        assert loaded.user_id == "test_user"
        assert loaded.message_count == 2
        assert "planner" in loaded.agents_used

    def test_load_empty_dir(self, tmp_path):
        storage = str(tmp_path / "empty_sessions")
        mgr = SessionManager(storage_path=storage)
        assert mgr.load_all() == 0

    def test_load_nonexistent_dir(self):
        mgr = SessionManager(storage_path="/tmp/jarvis_nonexistent_dir_12345")
        assert mgr.load_all() == 0


    # ── Metrics ──

    def test_get_metrics(self):
        mgr = SessionManager()
        s1 = mgr.create()
        s1.add_message("user", "hi", agent_name="planner")
        s1.total_tokens = 100
        s2 = mgr.create()
        s2.add_message("user", "hello", agent_name="executor")
        s2.total_tokens = 200
        mgr.complete(s2.id)

        metrics = mgr.get_metrics()
        assert metrics["total_sessions"] == 2
        assert metrics["active_sessions"] == 1
        assert metrics["total_messages"] == 2
        assert metrics["total_tokens"] == 300
        assert metrics["agents_usage"]["planner"] == 1
        assert metrics["agents_usage"]["executor"] == 1
