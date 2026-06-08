"""Security system tests.

Tests authentication, authorization, API key management,
rate limiting, input sanitization, and security policies.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Security Models
# ---------------------------------------------------------------------------

@dataclass
class APIKey:
    key_id: str
    key_hash: str  # Store hash, not plaintext
    name: str
    owner: str
    scopes: list[str] = field(default_factory=list)
    created_at: str = ""
    expires_at: str | None = None
    last_used: str | None = None
    active: bool = True
    usage_count: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.datetime.fromisoformat(self.expires_at) < datetime.datetime.utcnow()

    @property
    def is_valid(self) -> bool:
        return self.active and not self.is_expired

    def has_scope(self, scope: str) -> bool:
        if "*" in self.scopes:
            return True
        if scope in self.scopes:
            return True
        # Check wildcard patterns
        parts = scope.split(":")
        for s in self.scopes:
            s_parts = s.split(":")
            if len(s_parts) >= len(parts) and s_parts[0] == parts[0]:
                if len(s_parts) > 1 and s_parts[1] == "*":
                    return True
        return False

    def record_usage(self) -> None:
        self.usage_count += 1
        self.last_used = datetime.datetime.utcnow().isoformat()

    def revoke(self) -> None:
        self.active = False


class APIKeyManager:
    """Manage API keys for authentication."""

    def __init__(self):
        self.keys: dict[str, APIKey] = {}
        self._counter = 0

    def create_key(self, name: str, owner: str,
                   scopes: list[str] | None = None,
                   expires_days: int | None = None) -> tuple[str, APIKey]:
        """Create a new API key. Returns (plaintext_key, api_key_object)."""
        self._counter += 1
        plaintext = secrets.token_hex(32)
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        key_id = f"key-{self._counter:04d}"

        expires_at = None
        if expires_days:
            expires_at = (
                datetime.datetime.utcnow() + datetime.timedelta(days=expires_days)
            ).isoformat()

        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            owner=owner,
            scopes=scopes or ["read:*"],
            expires_at=expires_at,
        )
        self.keys[key_id] = api_key
        return plaintext, api_key

    def validate_key(self, plaintext: str) -> APIKey | None:
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        for api_key in self.keys.values():
            if api_key.key_hash == key_hash and api_key.is_valid:
                api_key.record_usage()
                return api_key
        return None

    def revoke_key(self, key_id: str) -> bool:
        api_key = self.keys.get(key_id)
        if api_key:
            api_key.revoke()
            return True
        return False

    def list_keys(self, owner: str | None = None,
                  active_only: bool = False) -> list[APIKey]:
        result = list(self.keys.values())
        if owner:
            result = [k for k in result if k.owner == owner]
        if active_only:
            result = [k for k in result if k.is_valid]
        return result

    @property
    def stats(self) -> dict[str, int]:
        total = len(self.keys)
        active = sum(1 for k in self.keys.values() if k.is_valid)
        expired = sum(1 for k in self.keys.values() if k.is_expired)
        revoked = sum(1 for k in self.keys.values() if not k.active)
        return {"total": total, "active": active, "expired": expired, "revoked": revoked}


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

@dataclass
class RateLimitRule:
    name: str
    max_requests: int
    window_seconds: float
    scope: str = "global"  # global, per_key, per_ip

    @property
    def requests_per_second(self) -> float:
        return self.max_requests / self.window_seconds


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self):
        self.rules: list[RateLimitRule] = []
        self._buckets: dict[str, list[float]] = {}

    def add_rule(self, rule: RateLimitRule) -> None:
        self.rules.append(rule)

    def check(self, identifier: str, rule_name: str | None = None) -> tuple[bool, str]:
        """Check if a request should be allowed."""
        for rule in self.rules:
            if rule_name and rule.name != rule_name:
                continue
            bucket_key = f"{rule.name}:{identifier}"
            now = time.time()

            if bucket_key not in self._buckets:
                self._buckets[bucket_key] = []

            # Clean old entries
            self._buckets[bucket_key] = [
                t for t in self._buckets[bucket_key]
                if now - t < rule.window_seconds
            ]

            if len(self._buckets[bucket_key]) >= rule.max_requests:
                return False, f"Rate limit exceeded: {rule.name} ({rule.max_requests}/{rule.window_seconds}s)"

            self._buckets[bucket_key].append(now)

        return True, "OK"

    def get_remaining(self, identifier: str, rule_name: str) -> int:
        rule = next((r for r in self.rules if r.name == rule_name), None)
        if not rule:
            return 0
        bucket_key = f"{rule.name}:{identifier}"
        now = time.time()
        recent = [
            t for t in self._buckets.get(bucket_key, [])
            if now - t < rule.window_seconds
        ]
        return max(0, rule.max_requests - len(recent))


# ---------------------------------------------------------------------------
# Input Sanitizer
# ---------------------------------------------------------------------------

class InputSanitizer:
    """Sanitize user inputs for security."""

    DANGEROUS_PATTERNS = [
        "rm -rf",
        "DROP TABLE",
        "DELETE FROM",
        "<script>",
        "javascript:",
        "eval(",
        "exec(",
        "__import__",
        "os.system",
        "subprocess",
    ]

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Remove or escape dangerous patterns."""
        sanitized = text
        for pattern in cls.DANGEROUS_PATTERNS:
            sanitized = sanitized.replace(pattern, "[BLOCKED]")
        return sanitized

    @classmethod
    def is_safe(cls, text: str) -> bool:
        """Check if text contains dangerous patterns."""
        text_lower = text.lower()
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.lower() in text_lower:
                return False
        return True

    @classmethod
    def validate_path(cls, path: str) -> tuple[bool, str]:
        """Validate a file path for safety."""
        if ".." in path:
            return False, "Path traversal detected"
        if path.startswith("/etc") or path.startswith("/root"):
            return False, "Access to sensitive directory"
        if any(c in path for c in ["|", ";", "&", "$", "`"]):
            return False, "Shell metacharacters detected"
        return True, "OK"

    @classmethod
    def validate_email(cls, email: str) -> bool:
        """Basic email validation."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @classmethod
    def validate_url(cls, url: str) -> bool:
        """Basic URL validation."""
        return url.startswith("http://") or url.startswith("https://")


# ---------------------------------------------------------------------------
# Security Policy
# ---------------------------------------------------------------------------

@dataclass
class SecurityPolicy:
    name: str
    description: str = ""
    max_tool_timeout: int = 300  # seconds
    allowed_tools: list[str] | None = None  # None = all
    blocked_tools: list[str] = field(default_factory=list)
    allow_shell: bool = True
    allow_file_write: bool = True
    allow_network: bool = True
    max_file_size_mb: int = 100
    sandbox_mode: bool = False

    def is_tool_allowed(self, tool_name: str) -> bool:
        if tool_name in self.blocked_tools:
            return False
        if self.allowed_tools is not None:
            return tool_name in self.allowed_tools
        return True

    def validate_file_size(self, size_bytes: int) -> bool:
        return size_bytes <= self.max_file_size_mb * 1024 * 1024


# ---------------------------------------------------------------------------
# Tests: APIKey
# ---------------------------------------------------------------------------

class TestAPIKey:
    def test_create_key(self):
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user")
        assert key.is_valid is True
        assert key.usage_count == 0

    def test_expired_key(self):
        past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user", expires_at=past)
        assert key.is_expired is True
        assert key.is_valid is False

    def test_not_expired_key(self):
        future = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat()
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user", expires_at=future)
        assert key.is_expired is False
        assert key.is_valid is True

    def test_revoked_key(self):
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user")
        key.revoke()
        assert key.active is False
        assert key.is_valid is False

    def test_scope_exact_match(self):
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user",
                     scopes=["read:specs", "write:specs"])
        assert key.has_scope("read:specs") is True
        assert key.has_scope("delete:specs") is False

    def test_scope_wildcard(self):
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user",
                     scopes=["*"])
        assert key.has_scope("anything") is True

    def test_scope_prefix_wildcard(self):
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user",
                     scopes=["read:*"])
        assert key.has_scope("read:specs") is True
        assert key.has_scope("read:agents") is True

    def test_record_usage(self):
        key = APIKey(key_id="k1", key_hash="abc", name="test", owner="user")
        key.record_usage()
        assert key.usage_count == 1
        assert key.last_used is not None


# ---------------------------------------------------------------------------
# Tests: APIKeyManager
# ---------------------------------------------------------------------------

class TestAPIKeyManager:
    def test_create_key(self):
        mgr = APIKeyManager()
        plaintext, api_key = mgr.create_key("test", "user")
        assert len(plaintext) == 64
        assert api_key.name == "test"

    def test_validate_key(self):
        mgr = APIKeyManager()
        plaintext, _ = mgr.create_key("test", "user")
        result = mgr.validate_key(plaintext)
        assert result is not None
        assert result.name == "test"

    def test_validate_invalid_key(self):
        mgr = APIKeyManager()
        result = mgr.validate_key("invalid-key")
        assert result is None

    def test_revoke_key(self):
        mgr = APIKeyManager()
        _, api_key = mgr.create_key("test", "user")
        assert mgr.revoke_key(api_key.key_id) is True
        assert api_key.is_valid is False

    def test_list_keys(self):
        mgr = APIKeyManager()
        mgr.create_key("a", "alice")
        mgr.create_key("b", "bob")
        mgr.create_key("c", "alice")
        assert len(mgr.list_keys()) == 3
        assert len(mgr.list_keys(owner="alice")) == 2

    def test_list_active_only(self):
        mgr = APIKeyManager()
        _, k1 = mgr.create_key("active", "user")
        _, k2 = mgr.create_key("revoked", "user")
        k2.revoke()
        assert len(mgr.list_keys(active_only=True)) == 1

    def test_stats(self):
        mgr = APIKeyManager()
        mgr.create_key("a", "user")
        mgr.create_key("b", "user")
        _, k3 = mgr.create_key("c", "user")
        k3.revoke()
        stats = mgr.stats
        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["revoked"] == 1

    def test_scoped_key(self):
        mgr = APIKeyManager()
        plaintext, _ = mgr.create_key("readonly", "user", scopes=["read:*"])
        api_key = mgr.validate_key(plaintext)
        assert api_key.has_scope("read:specs") is True
        assert api_key.has_scope("write:specs") is False


# ---------------------------------------------------------------------------
# Tests: RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allow_within_limit(self):
        rl = RateLimiter()
        rl.add_rule(RateLimitRule(name="api", max_requests=10, window_seconds=60))
        allowed, msg = rl.check("user1")
        assert allowed is True

    def test_deny_over_limit(self):
        rl = RateLimiter()
        rl.add_rule(RateLimitRule(name="api", max_requests=3, window_seconds=60))
        for _ in range(3):
            rl.check("user1")
        allowed, msg = rl.check("user1")
        assert allowed is False
        assert "Rate limit" in msg

    def test_separate_identifiers(self):
        rl = RateLimiter()
        rl.add_rule(RateLimitRule(name="api", max_requests=2, window_seconds=60))
        rl.check("user1")
        rl.check("user1")
        # user1 is at limit
        allowed1, _ = rl.check("user1")
        assert allowed1 is False
        # user2 should still be allowed
        allowed2, _ = rl.check("user2")
        assert allowed2 is True

    def test_get_remaining(self):
        rl = RateLimiter()
        rl.add_rule(RateLimitRule(name="api", max_requests=5, window_seconds=60))
        rl.check("user1")
        rl.check("user1")
        remaining = rl.get_remaining("user1", "api")
        assert remaining == 3

    def test_rule_rate(self):
        rule = RateLimitRule(name="api", max_requests=100, window_seconds=60)
        assert abs(rule.requests_per_second - 100/60) < 0.01


# ---------------------------------------------------------------------------
# Tests: InputSanitizer
# ---------------------------------------------------------------------------

class TestInputSanitizer:
    def test_safe_text(self):
        assert InputSanitizer.is_safe("Hello world") is True

    def test_dangerous_text(self):
        assert InputSanitizer.is_safe("rm -rf /") is False
        assert InputSanitizer.is_safe("DROP TABLE users") is False
        assert InputSanitizer.is_safe("<script>alert(1)</script>") is False

    def test_sanitize(self):
        result = InputSanitizer.sanitize_text("rm -rf / && echo done")
        assert "rm -rf" not in result
        assert "[BLOCKED]" in result

    def test_validate_safe_path(self):
        valid, msg = InputSanitizer.validate_path("/home/user/file.txt")
        assert valid is True

    def test_validate_traversal(self):
        valid, msg = InputSanitizer.validate_path("../../etc/passwd")
        assert valid is False
        assert "traversal" in msg.lower()

    def test_validate_sensitive_dir(self):
        valid, msg = InputSanitizer.validate_path("/etc/shadow")
        assert valid is False

    def test_validate_shell_metachar(self):
        valid, msg = InputSanitizer.validate_path("file.txt; rm -rf /")
        assert valid is False

    def test_validate_email_valid(self):
        assert InputSanitizer.validate_email("test@example.com") is True
        assert InputSanitizer.validate_email("user.name@domain.org") is True

    def test_validate_email_invalid(self):
        assert InputSanitizer.validate_email("not-an-email") is False
        assert InputSanitizer.validate_email("@domain.com") is False

    def test_validate_url(self):
        assert InputSanitizer.validate_url("https://example.com") is True
        assert InputSanitizer.validate_url("http://localhost:8000") is True
        assert InputSanitizer.validate_url("ftp://files.example.com") is False


# ---------------------------------------------------------------------------
# Tests: SecurityPolicy
# ---------------------------------------------------------------------------

class TestSecurityPolicy:
    def test_default_policy(self):
        policy = SecurityPolicy(name="default")
        assert policy.allow_shell is True
        assert policy.sandbox_mode is False

    def test_tool_allowed(self):
        policy = SecurityPolicy(name="open")
        assert policy.is_tool_allowed("shell") is True

    def test_tool_blocked(self):
        policy = SecurityPolicy(name="restricted", blocked_tools=["shell", "python_exec"])
        assert policy.is_tool_allowed("shell") is False
        assert policy.is_tool_allowed("read_file") is True

    def test_allowlist(self):
        policy = SecurityPolicy(name="strict", allowed_tools=["read_file", "json_query"])
        assert policy.is_tool_allowed("read_file") is True
        assert policy.is_tool_allowed("shell") is False

    def test_file_size_validation(self):
        policy = SecurityPolicy(name="default", max_file_size_mb=10)
        assert policy.validate_file_size(5 * 1024 * 1024) is True
        assert policy.validate_file_size(20 * 1024 * 1024) is False

    def test_sandbox_mode(self):
        policy = SecurityPolicy(
            name="sandbox",
            sandbox_mode=True,
            allow_shell=False,
            allow_file_write=False,
            allow_network=False,
        )
        assert policy.sandbox_mode is True
        assert policy.allow_shell is False
        assert policy.allow_network is False
