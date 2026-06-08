"""Structured logging for the JARVIS system.

Provides:
- ``StructuredFormatter`` — JSON-lines output for machine consumption.
- ``HumanFormatter`` — coloured, compact terminal output.
- ``JarvisLogger`` — thin wrapper that injects contextual ``extra`` fields.
- ``LogConfig`` / ``setup_logging`` — one-call configuration of the whole
  ``jarvis.*`` logger hierarchy.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

# Extra keys that JarvisLogger may attach to log records.
_CONTEXT_KEYS = (
    "agent",
    "tool",
    "spec_id",
    "step_id",
    "trace_id",
    "session_id",
    "user_id",
    "duration_ms",
    "error",
)


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter.

    Outputs logs as JSON lines for machine parsing while maintaining
    human readability when pretty-printed.
    """

    def __init__(self, include_extras: bool = True) -> None:
        super().__init__()
        self.include_extras = include_extras

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if self.include_extras:
            for key in _CONTEXT_KEYS:
                val = getattr(record, key, None)
                if val is not None:
                    log_entry[key] = val

        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    """Human-friendly coloured log formatter for terminal output."""

    COLORS: dict[str, str] = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        prefix = f"{color}{timestamp} [{record.levelname[0]}]{self.RESET}"
        msg = record.getMessage()

        # Collect context tags
        tags: list[str] = []
        for key in ("agent", "tool", "spec_id", "trace_id"):
            val = getattr(record, key, None)
            if val is not None:
                tags.append(f"{key}={val}")
        tag_str = f" {color}[{', '.join(tags)}]{self.RESET}" if tags else ""

        return f"{prefix} {record.name}: {msg}{tag_str}"


# ---------------------------------------------------------------------------
# JarvisLogger
# ---------------------------------------------------------------------------


class _ContextFilter(logging.Filter):
    """Ensure all context keys exist on the record to avoid KeyError."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in _CONTEXT_KEYS:
            if not hasattr(record, key):
                setattr(record, key, None)
        return True


class JarvisLogger:
    """Enhanced logger with context injection.

    Usage::

        log = JarvisLogger("jarvis.agents.code")
        log.info("Processing task", agent="code-agent", spec_id="abc123")
    """

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)
        # Add the context filter once
        if not any(isinstance(f, _ContextFilter) for f in self._logger.filters):
            self._logger.addFilter(_ContextFilter())

    def _log(self, level: int, msg: str, **context: Any) -> None:
        extra = {k: v for k, v in context.items() if v is not None}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **ctx: Any) -> None:
        self._log(logging.DEBUG, msg, **ctx)

    def info(self, msg: str, **ctx: Any) -> None:
        self._log(logging.INFO, msg, **ctx)

    def warning(self, msg: str, **ctx: Any) -> None:
        self._log(logging.WARNING, msg, **ctx)

    def error(self, msg: str, **ctx: Any) -> None:
        self._log(logging.ERROR, msg, **ctx)

    def critical(self, msg: str, **ctx: Any) -> None:
        self._log(logging.CRITICAL, msg, **ctx)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class LogConfig(BaseModel):
    """Logging configuration for ``setup_logging``."""

    level: str = "INFO"
    format: str = "human"  # "human", "json", "simple"
    output: str = "console"  # "console", "file", "both"
    file_path: str = "~/.jarvis/logs/jarvis.log"
    max_file_size_mb: int = 50
    backup_count: int = 5
    include_module_levels: dict[str, str] = Field(default_factory=dict)


def setup_logging(config: LogConfig | None = None) -> None:
    """Configure logging for the entire JARVIS application.

    Calling this function sets up the ``jarvis`` root logger with the
    chosen formatter(s) and handler(s).  It is safe to call more than
    once — existing handlers are removed first.
    """
    if config is None:
        config = LogConfig()

    root = logging.getLogger("jarvis")
    root.setLevel(getattr(logging, config.level.upper()))
    root.handlers.clear()

    # Attach context filter to root so all children inherit it.
    if not any(isinstance(f, _ContextFilter) for f in root.filters):
        root.addFilter(_ContextFilter())

    # Build formatter
    if config.format == "json":
        formatter: logging.Formatter = StructuredFormatter()
    elif config.format == "human":
        formatter = HumanFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    # Console handler
    if config.output in ("console", "both"):
        handler: logging.Handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)

    # File handler (always uses StructuredFormatter for grep-ability)
    if config.output in ("file", "both"):
        log_path = Path(config.file_path).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=config.max_file_size_mb * 1024 * 1024,
            backupCount=config.backup_count,
        )
        file_handler.setFormatter(StructuredFormatter())
        root.addHandler(file_handler)

    # Per-module overrides
    for module, level in config.include_module_levels.items():
        logging.getLogger(module).setLevel(getattr(logging, level.upper()))
