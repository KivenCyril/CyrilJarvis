"""Tests for the jarvis.security package."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jarvis.security.permissions import AuthContext, Permission, PermissionLevel
from jarvis.security.sandbox import SandboxConfig, SandboxMode, SandboxValidator
from jarvis.security.manager import SecurityManager


# ---------------------------------------------------------------------------
# Permission creation and checking
# ---------------------------------------------------------------------------


class TestPermission:
    def test_create_permission(self):
        perm = Permission(resource="filesystem", level=PermissionLevel.READ)
        assert perm.resource == "filesystem"
        assert perm.level == PermissionLevel.READ
        assert perm.scope == "*"
        assert perm.granted_by == "system"
        assert perm.expires_at is None

    def test_permission_with_scope(self):
        perm = Permission(
            resource="filesystem",
            level=PermissionLevel.WRITE,
            scope="/tmp/*",
        )
        assert perm.scope == "/tmp/*"
        assert perm.level == PermissionLevel.WRITE


# ---------------------------------------------------------------------------
# AuthContext permission hierarchy
# ---------------------------------------------------------------------------


class TestAuthContext:
    def test_permission_hierarchy(self):
        """Higher-level permission should grant access to lower levels."""
        ctx = AuthContext(
            permissions=[
                Permission(resource="filesystem", level=PermissionLevel.EXECUTE),
            ]
        )
        # EXECUTE (3) >= READ (1) -> True
        assert ctx.has_permission("filesystem", PermissionLevel.READ) is True
        # EXECUTE (3) >= WRITE (2) -> True
        assert ctx.has_permission("filesystem", PermissionLevel.WRITE) is True
        # EXECUTE (3) >= EXECUTE (3) -> True
        assert ctx.has_permission("filesystem", PermissionLevel.EXECUTE) is True
        # EXECUTE (3) < ADMIN (4) -> False
        assert ctx.has_permission("filesystem", PermissionLevel.ADMIN) is False

    def test_admin_bypass(self):
        """Admin context should bypass all permission checks."""
        ctx = AuthContext(is_admin=True, permissions=[])
        assert ctx.has_permission("filesystem", PermissionLevel.ADMIN) is True
        assert ctx.has_permission("network", PermissionLevel.EXECUTE) is True
        assert ctx.has_permission("anything", PermissionLevel.ADMIN) is True

    def test_expired_permission(self):
        """Expired permissions should not grant access."""
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        ctx = AuthContext(
            permissions=[
                Permission(
                    resource="filesystem",
                    level=PermissionLevel.WRITE,
                    expires_at=expired,
                ),
            ]
        )
        assert ctx.has_permission("filesystem", PermissionLevel.WRITE) is False

    def test_non_expired_permission(self):
        """Non-expired permissions should grant access normally."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        ctx = AuthContext(
            permissions=[
                Permission(
                    resource="filesystem",
                    level=PermissionLevel.WRITE,
                    expires_at=future,
                ),
            ]
        )
        assert ctx.has_permission("filesystem", PermissionLevel.WRITE) is True

    def test_no_matching_resource(self):
        """Permission for a different resource should not grant access."""
        ctx = AuthContext(
            permissions=[
                Permission(resource="network", level=PermissionLevel.ADMIN),
            ]
        )
        assert ctx.has_permission("filesystem", PermissionLevel.READ) is False

    def test_wildcard_resource(self):
        """Wildcard resource '*' should match any resource."""
        ctx = AuthContext(
            permissions=[
                Permission(resource="*", level=PermissionLevel.EXECUTE),
            ]
        )
        assert ctx.has_permission("filesystem", PermissionLevel.READ) is True
        assert ctx.has_permission("network", PermissionLevel.EXECUTE) is True

    def test_default_context(self):
        """Default context should have basic permissions."""
        ctx = AuthContext.default()
        assert ctx.has_permission("filesystem", PermissionLevel.READ) is True
        assert ctx.has_permission("shell", PermissionLevel.EXECUTE) is True
        assert ctx.has_permission("llm", PermissionLevel.EXECUTE) is True
        assert ctx.has_permission("network", PermissionLevel.READ) is True


# ---------------------------------------------------------------------------
# SandboxValidator
# ---------------------------------------------------------------------------


class TestSandboxValidator:
    def test_blocked_command(self):
        validator = SandboxValidator(SandboxConfig())
        allowed, reason = validator.validate_command("rm -rf /")
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_allowed_command(self):
        validator = SandboxValidator(SandboxConfig())
        allowed, reason = validator.validate_command("ls -la")
        assert allowed is True
        assert reason == ""

    def test_none_mode_allows_everything(self):
        config = SandboxConfig(mode=SandboxMode.NONE)
        validator = SandboxValidator(config)
        allowed, reason = validator.validate_command("rm -rf /")
        assert allowed is True

    def test_strict_mode_allowlist(self):
        config = SandboxConfig(
            mode=SandboxMode.STRICT,
            allowed_commands=["ls", "cat", "echo"],
        )
        validator = SandboxValidator(config)

        allowed, _ = validator.validate_command("ls -la")
        assert allowed is True

        allowed, reason = validator.validate_command("wget http://evil.com")
        assert allowed is False
        assert "allowlist" in reason.lower()

    def test_blocked_path(self):
        validator = SandboxValidator(SandboxConfig())
        allowed, reason = validator.validate_file_path("/etc/shadow")
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_allowed_path(self):
        validator = SandboxValidator(SandboxConfig())
        allowed, reason = validator.validate_file_path("/tmp/test.txt")
        assert allowed is True
        assert reason == ""

    def test_network_disabled(self):
        config = SandboxConfig(network_allowed=False)
        validator = SandboxValidator(config)
        allowed, reason = validator.validate_network("https://example.com")
        assert allowed is False
        assert "disabled" in reason.lower()

    def test_network_enabled(self):
        validator = SandboxValidator(SandboxConfig())
        allowed, reason = validator.validate_network("https://example.com")
        assert allowed is True


# ---------------------------------------------------------------------------
# SecurityManager
# ---------------------------------------------------------------------------


class TestSecurityManager:
    def test_secret_scanning_api_key(self):
        mgr = SecurityManager()
        text = 'api_key = "abcdefghijklmnopqrstuvwxyz"'
        findings = mgr.scan_for_secrets(text)
        assert len(findings) > 0
        assert any("secret" in f.lower() or "pattern" in f.lower() for f in findings)

    def test_secret_scanning_openai_key(self):
        mgr = SecurityManager()
        text = "Here is my key: sk-abcdefghijklmnopqrstuvwxyz1234"
        findings = mgr.scan_for_secrets(text)
        assert len(findings) > 0

    def test_secret_scanning_private_key(self):
        mgr = SecurityManager()
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        findings = mgr.scan_for_secrets(text)
        assert len(findings) > 0

    def test_secret_scanning_clean_text(self):
        mgr = SecurityManager()
        findings = mgr.scan_for_secrets("Hello, this is a normal message.")
        assert len(findings) == 0

    def test_secret_redaction(self):
        mgr = SecurityManager()
        text = "My key is sk-abcdefghijklmnopqrstuvwxyz1234 and it works."
        redacted = mgr.redact_secrets(text)
        assert "sk-" not in redacted
        assert "[REDACTED]" in redacted

    def test_secret_redaction_preserves_safe_text(self):
        mgr = SecurityManager()
        text = "This is perfectly safe text."
        redacted = mgr.redact_secrets(text)
        assert redacted == text

    def test_audit_logging(self):
        mgr = SecurityManager()
        ctx = AuthContext.default()
        mgr.check_permission(ctx, "filesystem", PermissionLevel.READ)
        mgr.check_permission(ctx, "network", PermissionLevel.ADMIN)

        log = mgr.get_audit_log()
        assert len(log) == 2
        assert log[0]["resource"] == "filesystem"
        assert log[0]["allowed"] is True
        assert log[1]["resource"] == "network"
        assert log[1]["allowed"] is False

    def test_audit_log_limit(self):
        mgr = SecurityManager()
        ctx = AuthContext.default()
        for _ in range(10):
            mgr.check_permission(ctx, "filesystem", PermissionLevel.READ)

        log = mgr.get_audit_log(limit=3)
        assert len(log) == 3
