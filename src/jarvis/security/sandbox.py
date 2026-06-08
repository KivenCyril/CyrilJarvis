from __future__ import annotations

import logging
import os
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SandboxMode(str, Enum):
    NONE = "none"
    BASIC = "basic"  # blocklist dangerous commands
    STRICT = "strict"  # allowlist only safe commands
    DOCKER = "docker"  # run in Docker container


class SandboxConfig(BaseModel):
    """Sandbox configuration for agent execution."""

    mode: SandboxMode = SandboxMode.BASIC
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(
        default_factory=lambda: [
            "rm -rf /",
            "rm -rf /*",
            "rm -rf ~",
            "mkfs",
            "dd if=/dev/zero",
            ":(){ :|:& };:",
            "chmod -R 777 /",
            "> /dev/sda",
            "shutdown",
            "reboot",
            "init 0",
            "init 6",
        ]
    )
    allowed_paths: list[str] = Field(default_factory=lambda: ["/tmp", "."])
    blocked_paths: list[str] = Field(
        default_factory=lambda: [
            "/etc/passwd",
            "/etc/shadow",
            "~/.ssh",
        ]
    )
    max_file_size_mb: int = 100
    max_execution_time_seconds: int = 300
    network_allowed: bool = True
    docker_image: str = "python:3.12-slim"


class SandboxValidator:
    """Validates operations against sandbox rules."""

    def __init__(self, config: SandboxConfig):
        self.config = config

    def validate_command(self, command: str) -> tuple[bool, str]:
        """Check if a shell command is allowed."""
        cmd_lower = command.lower().strip()

        if self.config.mode == SandboxMode.NONE:
            return True, ""

        # Check blocklist
        for blocked in self.config.blocked_commands:
            if blocked.lower() in cmd_lower:
                return False, f"Command blocked: matches pattern '{blocked}'"

        # In strict mode, check allowlist
        if self.config.mode == SandboxMode.STRICT:
            cmd_base = cmd_lower.split()[0] if cmd_lower else ""
            if self.config.allowed_commands and cmd_base not in self.config.allowed_commands:
                return False, f"Command not in allowlist: {cmd_base}"

        return True, ""

    def validate_file_path(self, path: str, write: bool = False) -> tuple[bool, str]:
        """Check if a file path access is allowed."""
        abs_path = os.path.abspath(os.path.expanduser(path))

        # Check blocked paths
        for blocked in self.config.blocked_paths:
            blocked_abs = os.path.abspath(os.path.expanduser(blocked))
            if abs_path.startswith(blocked_abs):
                return False, f"Path blocked: {path}"

        return True, ""

    def validate_network(self, url: str) -> tuple[bool, str]:
        """Check if network access is allowed."""
        if not self.config.network_allowed:
            return False, "Network access disabled in sandbox"
        return True, ""
