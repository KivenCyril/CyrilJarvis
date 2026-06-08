"""Tests for jarvis.logging — StructuredFormatter, HumanFormatter, JarvisLogger, AuditLogger."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jarvis.logging.structured import (
    HumanFormatter,
    JarvisLogger,
    LogConfig,
    StructuredFormatter,
    setup_logging,
)
from jarvis.logging.audit import AuditEntry, AuditLogger


# ── StructuredFormatter ──────────────────────────────────────────────────────


class TestStructuredFormatter:
    def _make_record(self, msg="hello", level=logging.INFO, **extras):
        logger = logging.getLogger("test.structured")
        record = logger.makeRecord(
            name="test.structured",
            level=level,
            fn="test_file.py",
            lno=42,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extras.items():
            setattr(record, k, v)
        return record

    def test_json_output(self):
        fmt = StructuredFormatter()
        record = self._make_record("hello world")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"
        assert data["logger"] == "test.structured"
        assert "timestamp" in data

    def test_includes_extras(self):
        fmt = StructuredFormatter(include_extras=True)
        record = self._make_record("test", agent="code-agent", spec_id="s123")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["agent"] == "code-agent"
        assert data["spec_id"] == "s123"

    def test_excludes_extras_when_disabled(self):
        fmt = StructuredFormatter(include_extras=False)
        record = self._make_record("test", agent="code-agent")
        output = fmt.format(record)
        data = json.loads(output)
        assert "agent" not in data

    def test_exception_info(self):
        fmt = StructuredFormatter()
        logger = logging.getLogger("test.exc")
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = self._make_record("error occurred")
        record.exc_info = exc_info
        output = fmt.format(record)
        data = json.loads(output)
        assert data["exception"]["type"] == "ValueError"
        assert data["exception"]["message"] == "test error"

    def test_non_ascii_message(self):
        fmt = StructuredFormatter()
        record = self._make_record("Chinese: 你好, Japanese: こんにちは")
        output = fmt.format(record)
        data = json.loads(output)
        assert "你好" in data["message"]


# ── HumanFormatter ───────────────────────────────────────────────────────────


class TestHumanFormatter:
    def test_basic_format(self):
        fmt = HumanFormatter()
        logger = logging.getLogger("test.human")
        record = logger.makeRecord(
            name="test.human",
            level=logging.INFO,
            fn="f.py",
            lno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)
        assert "test.human" in output
        assert "hello" in output
        assert "[I]" in output

    def test_includes_tags(self):
        fmt = HumanFormatter()
        logger = logging.getLogger("test.human")
        record = logger.makeRecord(
            name="test.human",
            level=logging.WARNING,
            fn="f.py",
            lno=1,
            msg="warning msg",
            args=(),
            exc_info=None,
        )
        record.agent = "planner"
        record.tool = "bash"
        output = fmt.format(record)
        assert "agent=planner" in output
        assert "tool=bash" in output

    def test_color_codes_present(self):
        fmt = HumanFormatter()
        logger = logging.getLogger("test.human")
        record = logger.makeRecord(
            name="test.human",
            level=logging.ERROR,
            fn="f.py",
            lno=1,
            msg="err",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)
        assert "\033[31m" in output  # red


# ── JarvisLogger ─────────────────────────────────────────────────────────────


class TestJarvisLogger:
    def test_info_log(self, capfd):
        setup_logging(LogConfig(level="DEBUG", format="json", output="console"))
        log = JarvisLogger("jarvis.test.jlogger")
        log.info("test message", agent="a1")
        # The message should have been emitted via the root jarvis logger
        # We verify by checking the underlying logger
        assert log._logger.name == "jarvis.test.jlogger"

    def test_all_levels(self):
        log = JarvisLogger("jarvis.test.levels")
        # Should not raise
        log.debug("d")
        log.info("i")
        log.warning("w")
        log.error("e")
        log.critical("c")

    def test_context_injection(self):
        """Verify extra fields actually reach the LogRecord."""
        captured: list[logging.LogRecord] = []

        class _H(logging.Handler):
            def emit(self, record):
                captured.append(record)

        logger = logging.getLogger("jarvis.test.ctx")
        logger.handlers.clear()
        logger.addHandler(_H())
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        jl = JarvisLogger("jarvis.test.ctx")
        jl.info("hello", agent="coder", spec_id="s1")

        assert len(captured) == 1
        assert captured[0].agent == "coder"  # type: ignore[attr-defined]
        assert captured[0].spec_id == "s1"  # type: ignore[attr-defined]


# ── LogConfig & setup_logging ────────────────────────────────────────────────


class TestLogConfig:
    def test_defaults(self):
        cfg = LogConfig()
        assert cfg.level == "INFO"
        assert cfg.format == "human"
        assert cfg.output == "console"

    def test_setup_json(self):
        setup_logging(LogConfig(level="DEBUG", format="json", output="console"))
        root = logging.getLogger("jarvis")
        assert root.level == logging.DEBUG
        assert len(root.handlers) >= 1

    def test_setup_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logging(LogConfig(
            level="INFO",
            format="json",
            output="file",
            file_path=str(log_file),
        ))
        root = logging.getLogger("jarvis")
        assert any(
            isinstance(h, logging.handlers.RotatingFileHandler)
            for h in root.handlers
        )

    def test_setup_both(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logging(LogConfig(
            level="INFO",
            format="human",
            output="both",
            file_path=str(log_file),
        ))
        root = logging.getLogger("jarvis")
        assert len(root.handlers) >= 2

    def test_module_level_override(self):
        setup_logging(LogConfig(
            level="WARNING",
            include_module_levels={"jarvis.noisy": "ERROR"},
        ))
        assert logging.getLogger("jarvis.noisy").level == logging.ERROR

    def test_setup_clears_old_handlers(self):
        setup_logging(LogConfig(level="INFO", format="json", output="console"))
        n1 = len(logging.getLogger("jarvis").handlers)
        setup_logging(LogConfig(level="INFO", format="json", output="console"))
        n2 = len(logging.getLogger("jarvis").handlers)
        assert n1 == n2  # not accumulating


# ── AuditLogger ──────────────────────────────────────────────────────────────


class TestAuditLogger:
    def test_log_entry(self, tmp_path):
        audit = AuditLogger(storage_path=str(tmp_path))
        entry = audit.log("login", user_id="u1", resource="/api", ip="127.0.0.1")
        assert entry.action == "login"
        assert entry.user_id == "u1"
        assert entry.result == "success"
        assert entry.details["ip"] == "127.0.0.1"

    def test_entry_count(self, tmp_path):
        audit = AuditLogger(storage_path=str(tmp_path))
        assert audit.entry_count == 0
        audit.log("a")
        audit.log("b")
        assert audit.entry_count == 2

    def test_query_by_action(self, tmp_path):
        audit = AuditLogger(storage_path=str(tmp_path))
        audit.log("login", user_id="u1")
        audit.log("logout", user_id="u1")
        audit.log("login", user_id="u2")
        results = audit.query(action="login")
        assert len(results) == 2

    def test_query_by_user(self, tmp_path):
        audit = AuditLogger(storage_path=str(tmp_path))
        audit.log("login", user_id="u1")
        audit.log("login", user_id="u2")
        results = audit.query(user_id="u1")
        assert len(results) == 1

    def test_save_and_load(self, tmp_path):
        audit = AuditLogger(storage_path=str(tmp_path))
        audit.log("action1", user_id="u1", resource="r1")
        audit.log("action2", user_id="u2", resource="r2")
        audit.save()

        # Load into a fresh instance
        audit2 = AuditLogger(storage_path=str(tmp_path))
        loaded = audit2.load()
        assert loaded == 2
        assert audit2.entry_count == 2

    def test_failure_result(self, tmp_path):
        audit = AuditLogger(storage_path=str(tmp_path))
        entry = audit.log("login", user_id="u1", result="failure", reason="bad password")
        assert entry.result == "failure"
        assert entry.details["reason"] == "bad password"
