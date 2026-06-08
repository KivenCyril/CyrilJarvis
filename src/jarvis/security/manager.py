from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from jarvis.security.permissions import AuthContext, PermissionLevel
from jarvis.security.sandbox import SandboxConfig, SandboxValidator

logger = logging.getLogger(__name__)


class SecurityManager:
    """Central security manager.

    Responsibilities:
    - Authentication context management
    - Permission checking
    - Sandbox enforcement
    - Audit logging
    - Secret detection in outputs
    """

    def __init__(self, sandbox_config: SandboxConfig | None = None):
        self.sandbox = SandboxValidator(sandbox_config or SandboxConfig())
        self._audit_log: list[dict] = []
        self._secret_patterns: list[str] = [
            r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?[\w-]{20,}",
            r"(?i)(secret|token|password|passwd|pwd)\s*[:=]\s*['\"]?[\w-]{8,}",
            r"(?i)bearer\s+[\w\-.~+/]+=*",
            r"sk-[a-zA-Z0-9]{20,}",  # OpenAI keys
            r"ghp_[a-zA-Z0-9]{36}",  # GitHub tokens
            r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
        ]

    def check_permission(
        self, context: AuthContext, resource: str, level: PermissionLevel
    ) -> bool:
        """Check permission and log the access attempt."""
        allowed = context.has_permission(resource, level)
        self._audit_log.append(
            {
                "action": "permission_check",
                "user": context.user_id,
                "resource": resource,
                "level": level.value,
                "allowed": allowed,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return allowed

    def scan_for_secrets(self, text: str) -> list[str]:
        """Scan text for potential secrets/credentials."""
        findings = []
        for pattern in self._secret_patterns:
            matches = re.findall(pattern, text)
            if matches:
                findings.append(
                    f"Potential secret detected: pattern '{pattern[:30]}...'"
                )
        return findings

    def redact_secrets(self, text: str) -> str:
        """Replace detected secrets with [REDACTED]."""
        result = text
        for pattern in self._secret_patterns:
            result = re.sub(pattern, "[REDACTED]", result)
        return result

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """Return recent audit log entries."""
        return self._audit_log[-limit:]
