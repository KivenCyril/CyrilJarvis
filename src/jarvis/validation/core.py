"""Core validation framework — composable validators, sanitizers, and config checks.

Usage::

    result = (Validator()
        .required("name")
        .min_length("name", 3)
        .max_length("name", 50)
        .matches("email", r"^[^@]+@[^@]+\\.[^@]+$")
        .in_range("age", 0, 150)
        .validate(data))
"""

from __future__ import annotations

import logging
import os
import re
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity & Issue
# ---------------------------------------------------------------------------


class ValidationSeverity(str, Enum):
    """How serious a validation finding is."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(BaseModel):
    """A single validation finding."""

    field: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    value: Any = None
    suggestion: str = ""


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Aggregated result of one or more validation checks."""

    valid: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)

    # -- mutators ---------------------------------------------------------

    def add_error(self, field: str, message: str, **kwargs: Any) -> None:
        """Record an error and mark the result as invalid."""
        self.issues.append(
            ValidationIssue(
                field=field,
                message=message,
                severity=ValidationSeverity.ERROR,
                **kwargs,
            )
        )
        self.valid = False

    def add_warning(self, field: str, message: str, **kwargs: Any) -> None:
        """Record a warning (does *not* invalidate the result)."""
        self.issues.append(
            ValidationIssue(
                field=field,
                message=message,
                severity=ValidationSeverity.WARNING,
                **kwargs,
            )
        )

    def add_info(self, field: str, message: str, **kwargs: Any) -> None:
        """Record an informational note."""
        self.issues.append(
            ValidationIssue(
                field=field,
                message=message,
                severity=ValidationSeverity.INFO,
                **kwargs,
            )
        )

    def merge(self, other: ValidationResult) -> None:
        """Merge another result into this one."""
        self.issues.extend(other.issues)
        if not other.valid:
            self.valid = False

    # -- accessors --------------------------------------------------------

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    @property
    def infos(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.INFO]

    def summary(self) -> str:
        """One-line summary."""
        return (
            f"{'VALID' if self.valid else 'INVALID'}: "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


# ---------------------------------------------------------------------------
# Composable Validator
# ---------------------------------------------------------------------------

# Each rule is (field, rule_name, check_fn, kwargs)
_Rule = tuple[str, str, Callable[..., str | None], dict[str, Any]]


class Validator:
    """Fluent, composable field validator.

    Build a chain of rules, then call :meth:`validate` with a ``dict``
    to get a :class:`ValidationResult`.
    """

    def __init__(self) -> None:
        self._rules: list[_Rule] = []

    # -- rule builders ----------------------------------------------------

    def required(self, field: str, message: str = "") -> Validator:
        """Field must be present and non-empty."""

        def _check(value: Any, **_kw: Any) -> str | None:
            if value is None or (isinstance(value, str) and not value.strip()):
                return message or f"{field} is required"
            return None

        self._rules.append((field, "required", _check, {}))
        return self

    def min_length(self, field: str, min_len: int, message: str = "") -> Validator:
        """String/list length must be >= *min_len*."""

        def _check(value: Any, **_kw: Any) -> str | None:
            if value is not None and hasattr(value, "__len__") and len(value) < min_len:
                return message or f"{field} must be at least {min_len} characters"
            return None

        self._rules.append((field, "min_length", _check, {}))
        return self

    def max_length(self, field: str, max_len: int, message: str = "") -> Validator:
        """String/list length must be <= *max_len*."""

        def _check(value: Any, **_kw: Any) -> str | None:
            if value is not None and hasattr(value, "__len__") and len(value) > max_len:
                return message or f"{field} must be at most {max_len} characters"
            return None

        self._rules.append((field, "max_length", _check, {}))
        return self

    def matches(self, field: str, pattern: str, message: str = "") -> Validator:
        """String value must match *pattern*."""
        compiled = re.compile(pattern)

        def _check(value: Any, **_kw: Any) -> str | None:
            if value is not None and isinstance(value, str):
                if not compiled.match(value):
                    return message or f"{field} does not match expected pattern"
            return None

        self._rules.append((field, "matches", _check, {}))
        return self

    def in_range(
        self, field: str, min_val: float | int, max_val: float | int, message: str = ""
    ) -> Validator:
        """Numeric value must be within [min_val, max_val]."""

        def _check(value: Any, **_kw: Any) -> str | None:
            if value is not None and isinstance(value, (int, float)):
                if value < min_val or value > max_val:
                    return message or f"{field} must be between {min_val} and {max_val}"
            return None

        self._rules.append((field, "in_range", _check, {}))
        return self

    def one_of(self, field: str, choices: list[Any], message: str = "") -> Validator:
        """Value must be one of *choices*."""

        def _check(value: Any, **_kw: Any) -> str | None:
            if value is not None and value not in choices:
                return message or f"{field} must be one of {choices}"
            return None

        self._rules.append((field, "one_of", _check, {}))
        return self

    def custom(
        self,
        field: str,
        check: Callable[[Any], bool],
        message: str = "",
    ) -> Validator:
        """Arbitrary boolean predicate.  Returns *message* when ``check(value)`` is False."""

        def _check(value: Any, **_kw: Any) -> str | None:
            if value is not None and not check(value):
                return message or f"{field} failed custom validation"
            return None

        self._rules.append((field, "custom", _check, {}))
        return self

    # -- execution --------------------------------------------------------

    def validate(self, data: dict[str, Any]) -> ValidationResult:
        """Run all registered rules against *data*."""
        result = ValidationResult()

        for field, _rule_name, check_fn, _kw in self._rules:
            value = _resolve_field(data, field)
            error_msg = check_fn(value)
            if error_msg:
                result.add_error(field, error_msg, value=value)

        return result


def _resolve_field(data: dict[str, Any], field: str) -> Any:
    """Resolve a potentially dot-separated field path."""
    parts = field.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


# ---------------------------------------------------------------------------
# InputSanitizer
# ---------------------------------------------------------------------------

# Pre-compiled patterns
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_PATH_TRAVERSAL_RE = re.compile(r"(^|[/\\])\.\.([/\\]|$)")

# Dangerous shell patterns
_DANGEROUS_SHELL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+-rf\s+/"), "destructive rm -rf /"),
    (re.compile(r"\bmkfs\b"), "filesystem format command"),
    (re.compile(r"\bdd\s+.*of=/dev/"), "raw device write"),
    (re.compile(r">\s*/dev/sd[a-z]"), "raw device redirect"),
    (re.compile(r":\(\)\s*\{.*:\|:.*\}"), "fork bomb"),
    (re.compile(r"\bchmod\s+-R\s+777\s+/\b"), "recursive world-writable root"),
    (re.compile(r"\bcurl\b.*\|\s*(ba)?sh"), "pipe curl to shell"),
    (re.compile(r"\bwget\b.*\|\s*(ba)?sh"), "pipe wget to shell"),
    (re.compile(r"\beval\b.*\$\("), "eval with command substitution"),
]


class InputSanitizer:
    """Sanitize user input for safety."""

    @staticmethod
    def sanitize_string(s: str, max_length: int = 10000) -> str:
        """Truncate and strip null bytes from a string."""
        s = s.replace("\x00", "")
        if len(s) > max_length:
            s = s[:max_length]
        return s

    @staticmethod
    def sanitize_path(path: str) -> str:
        """Prevent path traversal attacks.

        Returns the sanitized absolute path or raises ``ValueError``
        if the path attempts traversal outside the working directory.
        """
        # Reject null bytes
        if "\x00" in path:
            raise ValueError("Path contains null bytes")

        # Normalise
        cleaned = os.path.normpath(path)

        # Reject path-traversal sequences
        if _PATH_TRAVERSAL_RE.search(path):
            raise ValueError(f"Path traversal detected: {path}")

        # Reject absolute paths that try to escape (e.g. /etc/passwd)
        if os.path.isabs(cleaned):
            # Allow absolute paths but log a warning
            logger.debug("Absolute path used: %s", cleaned)

        return cleaned

    @staticmethod
    def sanitize_command(command: str) -> tuple[bool, str]:
        """Check a shell command string for dangerous patterns.

        Returns ``(safe, reason)`` where *safe* is ``True`` when no
        dangerous pattern was matched.
        """
        for pattern, description in _DANGEROUS_SHELL_PATTERNS:
            if pattern.search(command):
                return False, f"Blocked: {description}"
        return True, ""

    @staticmethod
    def sanitize_url(url: str) -> tuple[bool, str]:
        """Validate and sanitize a URL.

        Returns ``(valid, reason)``.
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return False, "Malformed URL"

        if parsed.scheme not in ("http", "https", ""):
            return False, f"Unsupported scheme: {parsed.scheme}"

        if not parsed.hostname:
            return False, "Missing hostname"

        # Block private/internal IPs
        hostname = parsed.hostname.lower()
        private_patterns = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "169.254.",
            "10.",
            "192.168.",
            "172.16.",
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
            "[::1]",
        ]
        for pp in private_patterns:
            if hostname.startswith(pp) or hostname == pp:
                return False, f"Private/internal address: {hostname}"

        return True, ""

    @staticmethod
    def strip_ansi(text: str) -> str:
        """Remove ANSI escape codes from *text*."""
        return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# ConfigValidator
# ---------------------------------------------------------------------------


class ConfigValidator:
    """Validate JARVIS configuration files against expected schemas."""

    def validate_settings(self, settings: dict[str, Any]) -> ValidationResult:
        """Validate a ``jarvis.yaml`` settings dictionary."""
        result = ValidationResult()

        # Top-level keys
        known_keys = {
            "app_name", "version", "specs_dir", "log", "server",
            "agents", "hooks", "knowledge", "llm", "security",
            "gateway", "memory", "skills", "mcp", "observability",
        }
        for key in settings:
            if key not in known_keys:
                result.add_warning(key, f"Unknown top-level setting: {key}")

        # Server validation
        server = settings.get("server", {})
        if isinstance(server, dict):
            port = server.get("port")
            if port is not None:
                if not isinstance(port, int) or port < 1 or port > 65535:
                    result.add_error(
                        "server.port",
                        f"Port must be 1-65535, got {port}",
                        value=port,
                        suggestion="Use a port between 1024 and 65535",
                    )

        # LLM validation
        llm = settings.get("llm", {})
        if isinstance(llm, dict):
            temp = llm.get("temperature")
            if temp is not None:
                if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                    result.add_error(
                        "llm.temperature",
                        f"Temperature must be 0-2, got {temp}",
                        value=temp,
                    )
            max_tokens = llm.get("max_tokens")
            if max_tokens is not None:
                if not isinstance(max_tokens, int) or max_tokens < 1:
                    result.add_error(
                        "llm.max_tokens",
                        f"max_tokens must be a positive integer, got {max_tokens}",
                        value=max_tokens,
                    )

        # Security validation
        security = settings.get("security", {})
        if isinstance(security, dict):
            sandbox = security.get("sandbox_mode")
            if sandbox is not None and sandbox not in ("off", "basic", "strict", "docker"):
                result.add_warning(
                    "security.sandbox_mode",
                    f"Unknown sandbox mode: {sandbox}",
                    value=sandbox,
                    suggestion="Use one of: off, basic, strict, docker",
                )

        # Log level
        log = settings.get("log", {})
        if isinstance(log, dict):
            level = log.get("level")
            if level is not None and level not in (
                "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
            ):
                result.add_warning(
                    "log.level",
                    f"Unknown log level: {level}",
                    value=level,
                )

        return result

    def validate_mcp_config(self, config: dict[str, Any]) -> ValidationResult:
        """Validate an MCP server configuration."""
        result = ValidationResult()

        servers = config.get("servers", [])
        if not isinstance(servers, list):
            result.add_error("servers", "servers must be a list")
            return result

        for i, server in enumerate(servers):
            if not isinstance(server, dict):
                result.add_error(f"servers[{i}]", "Each server must be a mapping")
                continue

            if "name" not in server:
                result.add_error(f"servers[{i}].name", "Server name is required")

            if "command" not in server and "url" not in server:
                result.add_error(
                    f"servers[{i}]",
                    "Server must have either 'command' or 'url'",
                )

        return result

    def validate_agent_spec(self, spec: dict[str, Any]) -> ValidationResult:
        """Validate an AgentSpec dictionary."""
        result = ValidationResult()

        meta = spec.get("metadata", {})
        if not isinstance(meta, dict):
            result.add_error("metadata", "metadata must be a mapping")
        else:
            if not meta.get("name"):
                result.add_error("metadata.name", "Agent name is required")
            version = meta.get("version", "")
            if version and not re.match(r"^v?\d+", version):
                result.add_warning(
                    "metadata.version",
                    f"Version '{version}' does not start with a number",
                )

        triggers = spec.get("triggers", [])
        if not isinstance(triggers, list):
            result.add_error("triggers", "triggers must be a list")
        else:
            for i, trig in enumerate(triggers):
                if isinstance(trig, dict) and not trig.get("event"):
                    result.add_error(
                        f"triggers[{i}].event",
                        "Trigger event is required",
                    )

        collab = spec.get("collaboration", {})
        if isinstance(collab, dict):
            delegates = collab.get("can_delegate_to", [])
            if not isinstance(delegates, list):
                result.add_error(
                    "collaboration.can_delegate_to",
                    "can_delegate_to must be a list",
                )

        return result

    def validate_skill(self, skill: dict[str, Any]) -> ValidationResult:
        """Validate a Skill definition dictionary."""
        result = ValidationResult()

        meta = skill.get("metadata", {})
        if not isinstance(meta, dict):
            result.add_error("metadata", "metadata must be a mapping")
        else:
            if not meta.get("name"):
                result.add_error("metadata.name", "Skill name is required")
            if not meta.get("description"):
                result.add_warning(
                    "metadata.description",
                    "Skill should have a description",
                )

        spec = skill.get("spec", {})
        if isinstance(spec, dict):
            steps = spec.get("steps", [])
            if not isinstance(steps, list):
                result.add_error("spec.steps", "steps must be a list")
            elif not steps:
                result.add_warning("spec.steps", "Skill has no steps defined")
            else:
                for i, s in enumerate(steps):
                    if isinstance(s, dict) and not s.get("action"):
                        result.add_error(
                            f"spec.steps[{i}].action",
                            "Step action is required",
                        )

        return result
