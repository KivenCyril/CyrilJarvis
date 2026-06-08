from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PermissionLevel(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class Permission(BaseModel):
    """A permission grant for a specific resource."""

    resource: str  # e.g., "filesystem", "shell", "network", "llm"
    level: PermissionLevel = PermissionLevel.READ
    scope: str = "*"  # e.g., "/tmp/*", "localhost:*"
    granted_by: str = "system"
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None


class AuthContext(BaseModel):
    """Authentication and authorization context for a request."""

    user_id: str = "default"
    session_id: str = ""
    permissions: list[Permission] = Field(default_factory=list)
    is_admin: bool = False
    channel: str = "cli"

    def has_permission(self, resource: str, level: PermissionLevel) -> bool:
        """Check if this context has a specific permission."""
        level_hierarchy = {
            PermissionLevel.NONE: 0,
            PermissionLevel.READ: 1,
            PermissionLevel.WRITE: 2,
            PermissionLevel.EXECUTE: 3,
            PermissionLevel.ADMIN: 4,
        }

        if self.is_admin:
            return True

        required = level_hierarchy[level]
        for perm in self.permissions:
            if perm.resource == resource or perm.resource == "*":
                if level_hierarchy[perm.level] >= required:
                    if perm.expires_at and perm.expires_at < datetime.now(timezone.utc):
                        continue
                    return True
        return False

    @classmethod
    def default(cls) -> AuthContext:
        """Create a default context with basic permissions."""
        return cls(
            permissions=[
                Permission(resource="filesystem", level=PermissionLevel.READ),
                Permission(
                    resource="filesystem",
                    level=PermissionLevel.WRITE,
                    scope="/tmp/*",
                ),
                Permission(resource="shell", level=PermissionLevel.EXECUTE),
                Permission(resource="llm", level=PermissionLevel.EXECUTE),
                Permission(resource="network", level=PermissionLevel.READ),
            ]
        )
