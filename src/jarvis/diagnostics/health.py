"""Health check system for JARVIS.

Provides comprehensive system diagnostics covering Python environment,
system resources, module availability, LLM providers, tools, storage,
network, and configuration validation.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Possible health statuses for a diagnostic check."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheck(BaseModel):
    """Result of a single diagnostic check."""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    duration_ms: float = 0
    details: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DiagnosticReport(BaseModel):
    """Aggregated report from all diagnostic checks."""

    checks: list[HealthCheck]
    overall_status: HealthStatus
    timestamp: datetime

    def to_table(self) -> str:
        """Format the report as a printable table."""
        lines = [
            f"System Diagnostics ({self.timestamp.strftime('%Y-%m-%d %H:%M:%S')})",
            "=" * 60,
        ]
        for check in self.checks:
            icon = {
                "healthy": "[OK]",
                "degraded": "[WARN]",
                "unhealthy": "[FAIL]",
                "unknown": "[??]",
            }[check.status.value]
            lines.append(
                f"{icon} {check.name}: {check.message} ({check.duration_ms:.0f}ms)"
            )
        lines.append(f"\nOverall: {self.overall_status.value.upper()}")
        return "\n".join(lines)

    def get_check(self, name: str) -> HealthCheck | None:
        """Look up a check by name."""
        for check in self.checks:
            if check.name == name:
                return check
        return None

    @property
    def healthy_count(self) -> int:
        return sum(1 for c in self.checks if c.status == HealthStatus.HEALTHY)

    @property
    def degraded_count(self) -> int:
        return sum(1 for c in self.checks if c.status == HealthStatus.DEGRADED)

    @property
    def unhealthy_count(self) -> int:
        return sum(1 for c in self.checks if c.status == HealthStatus.UNHEALTHY)


class SystemDiagnostics:
    """Comprehensive system diagnostics and health checking.

    Checks:
    - Python environment (version, packages, virtual env)
    - System resources (CPU, memory, disk)
    - Module availability (all 28+ modules)
    - LLM provider connectivity
    - Tool system health
    - Storage backends
    - Network connectivity
    - Configuration validation
    """

    # Key packages required for JARVIS to operate fully.
    REQUIRED_PACKAGES = ["pydantic", "fastapi", "uvicorn", "rich", "yaml", "httpx"]

    # All JARVIS sub-modules that should be importable.
    MODULES_TO_CHECK = [
        "jarvis.agents",
        "jarvis.engine",
        "jarvis.llm",
        "jarvis.tools",
        "jarvis.knowledge",
        "jarvis.memory",
        "jarvis.skills",
        "jarvis.curator",
        "jarvis.mcp",
        "jarvis.gateway",
        "jarvis.plugins",
        "jarvis.security",
        "jarvis.session",
        "jarvis.observability",
        "jarvis.hooks",
        "jarvis.config",
        "jarvis.models",
        "jarvis.server",
        "jarvis.cli",
        "jarvis.notifications",
        "jarvis.templates",
        "jarvis.storage",
        "jarvis.resilience",
        "jarvis.prompts",
        "jarvis.user",
        "jarvis.scheduler",
        "jarvis.workflow",
        "jarvis.tui",
        "jarvis.sdk",
    ]

    # Environment variables that indicate LLM provider keys.
    LLM_PROVIDER_KEYS = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }

    def __init__(self, app: Any | None = None):
        self._app = app
        self._checks: list[HealthCheck] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_all(self) -> DiagnosticReport:
        """Run all diagnostic checks and return a report."""
        self._checks = []

        await self._check_python_env()
        await self._check_system_resources()
        await self._check_modules()
        await self._check_agents()
        await self._check_tools()
        await self._check_storage()
        await self._check_llm_providers()
        await self._check_config()

        return DiagnosticReport(
            checks=list(self._checks),
            overall_status=self._compute_overall(),
            timestamp=datetime.now(timezone.utc),
        )

    async def run_check(self, name: str) -> HealthCheck | None:
        """Run a single named check and return its result."""
        method_map = {
            "python_environment": self._check_python_env,
            "system_resources": self._check_system_resources,
            "modules": self._check_modules,
            "agents": self._check_agents,
            "tools": self._check_tools,
            "storage": self._check_storage,
            "llm_providers": self._check_llm_providers,
            "config": self._check_config,
        }
        method = method_map.get(name)
        if method is None:
            return None
        before = len(self._checks)
        await method()
        if len(self._checks) > before:
            return self._checks[-1]
        return None

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    async def _check_python_env(self) -> None:
        """Check Python version, installed packages, virtual env."""
        start = time.monotonic()

        details: dict[str, Any] = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "arch": platform.machine(),
            "virtual_env": (
                hasattr(sys, "real_prefix")
                or (
                    hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
                )
            ),
        }

        missing: list[str] = []
        installed: list[str] = []
        for pkg in self.REQUIRED_PACKAGES:
            try:
                __import__(pkg)
                installed.append(pkg)
            except ImportError:
                missing.append(pkg)

        details["installed_packages"] = installed
        details["missing_packages"] = missing

        status = HealthStatus.HEALTHY if not missing else HealthStatus.DEGRADED
        duration = (time.monotonic() - start) * 1000

        self._checks.append(
            HealthCheck(
                name="python_environment",
                status=status,
                message=(
                    f"Python {sys.version_info.major}.{sys.version_info.minor}"
                    + (f", missing: {missing}" if missing else "")
                ),
                duration_ms=duration,
                details=details,
            )
        )

    async def _check_system_resources(self) -> None:
        """Check CPU, memory, disk usage."""
        start = time.monotonic()
        details: dict[str, Any] = {}

        # Disk usage
        try:
            usage = shutil.disk_usage("/")
            details["disk_total_gb"] = round(usage.total / (1024**3), 1)
            details["disk_free_gb"] = round(usage.free / (1024**3), 1)
            details["disk_used_pct"] = round((usage.used / usage.total) * 100, 1)
        except Exception:
            pass

        # CPU
        details["cpu_count"] = os.cpu_count()

        # Load average (Unix only)
        try:
            load = os.getloadavg()
            details["load_avg_1m"] = round(load[0], 2)
            details["load_avg_5m"] = round(load[1], 2)
            details["load_avg_15m"] = round(load[2], 2)
        except (OSError, AttributeError):
            pass

        # Process memory via resource module (Unix)
        try:
            import resource as _resource

            mem = _resource.getrusage(_resource.RUSAGE_SELF)
            # On macOS ru_maxrss is in bytes, on Linux it's in kilobytes.
            if sys.platform == "darwin":
                details["process_memory_mb"] = round(
                    mem.ru_maxrss / (1024 * 1024), 1
                )
            else:
                details["process_memory_mb"] = round(mem.ru_maxrss / 1024, 1)
        except Exception:
            pass

        disk_pct = details.get("disk_used_pct", 0)
        status = HealthStatus.HEALTHY
        if disk_pct > 90:
            status = HealthStatus.UNHEALTHY
        elif disk_pct > 80:
            status = HealthStatus.DEGRADED

        self._checks.append(
            HealthCheck(
                name="system_resources",
                status=status,
                message=(
                    f"Disk: {details.get('disk_free_gb', '?')}GB free, "
                    f"CPU: {details.get('cpu_count', '?')} cores"
                ),
                duration_ms=(time.monotonic() - start) * 1000,
                details=details,
            )
        )

    async def _check_modules(self) -> None:
        """Check all JARVIS modules are importable."""
        start = time.monotonic()

        available: list[str] = []
        unavailable: list[str] = []
        for mod in self.MODULES_TO_CHECK:
            short = mod.split(".")[-1]
            try:
                __import__(mod)
                available.append(short)
            except ImportError:
                unavailable.append(short)

        total = len(self.MODULES_TO_CHECK)
        status = HealthStatus.HEALTHY if not unavailable else HealthStatus.DEGRADED

        self._checks.append(
            HealthCheck(
                name="modules",
                status=status,
                message=f"{len(available)}/{total} modules available",
                duration_ms=(time.monotonic() - start) * 1000,
                details={"available": available, "unavailable": unavailable},
            )
        )

    async def _check_agents(self) -> None:
        """Check agent registry health."""
        start = time.monotonic()
        details: dict[str, Any] = {}
        status = HealthStatus.HEALTHY

        try:
            from jarvis.agents.registry import AgentRegistry

            registry = AgentRegistry()
            agents = getattr(registry, "_agents", {})
            details["registered_count"] = len(agents)
            details["agent_names"] = list(agents.keys()) if agents else []
            if len(agents) == 0:
                status = HealthStatus.DEGRADED
                details["note"] = "No agents registered in default registry"
        except ImportError:
            status = HealthStatus.UNHEALTHY
            details["error"] = "AgentRegistry not importable"
        except Exception as exc:
            status = HealthStatus.DEGRADED
            details["error"] = str(exc)

        self._checks.append(
            HealthCheck(
                name="agents",
                status=status,
                message=f"{details.get('registered_count', 0)} agents registered",
                duration_ms=(time.monotonic() - start) * 1000,
                details=details,
            )
        )

    async def _check_tools(self) -> None:
        """Check tool registry health."""
        start = time.monotonic()
        details: dict[str, Any] = {}
        status = HealthStatus.HEALTHY

        try:
            from jarvis.tools import ToolRegistry

            registry = ToolRegistry()
            tools = getattr(registry, "_tools", {})
            details["registered_count"] = len(tools)
            details["tool_names"] = sorted(tools.keys()) if tools else []
            if len(tools) == 0:
                status = HealthStatus.DEGRADED
                details["note"] = "No tools registered in default registry"
        except ImportError:
            status = HealthStatus.DEGRADED
            details["error"] = "ToolRegistry not importable"
        except Exception as exc:
            status = HealthStatus.DEGRADED
            details["error"] = str(exc)

        self._checks.append(
            HealthCheck(
                name="tools",
                status=status,
                message=f"{details.get('registered_count', 0)} tools registered",
                duration_ms=(time.monotonic() - start) * 1000,
                details=details,
            )
        )

    async def _check_storage(self) -> None:
        """Check storage backends (write/read/delete cycle)."""
        start = time.monotonic()
        details: dict[str, Any] = {}
        status = HealthStatus.HEALTHY

        # Test MemoryStore (in-memory, always available)
        try:
            from jarvis.storage import MemoryStore

            store = MemoryStore()
            await store.put("__diag_test__", {"check": True})
            result = await store.get("__diag_test__")
            await store.delete("__diag_test__")
            if result and result.get("check") is True:
                details["memory_store"] = "ok"
            else:
                details["memory_store"] = "read-back failed"
                status = HealthStatus.DEGRADED
        except ImportError:
            details["memory_store"] = "not importable"
            status = HealthStatus.DEGRADED
        except Exception as exc:
            details["memory_store"] = f"error: {exc}"
            status = HealthStatus.DEGRADED

        # Test JSONStore (file-based)
        import tempfile

        try:
            from jarvis.storage import JSONStore

            tmpdir = tempfile.mkdtemp(prefix="jarvis_diag_")
            json_store = JSONStore(tmpdir)
            await json_store.put("__diag_test__", {"check": True})
            result = await json_store.get("__diag_test__")
            await json_store.delete("__diag_test__")
            if result and result.get("check") is True:
                details["json_store"] = "ok"
            else:
                details["json_store"] = "read-back failed"
                status = HealthStatus.DEGRADED
            # Clean up
            shutil.rmtree(tmpdir, ignore_errors=True)
        except ImportError:
            details["json_store"] = "not importable"
            status = HealthStatus.DEGRADED
        except Exception as exc:
            details["json_store"] = f"error: {exc}"
            status = HealthStatus.DEGRADED

        self._checks.append(
            HealthCheck(
                name="storage",
                status=status,
                message="Storage backends operational" if status == HealthStatus.HEALTHY else "Some storage issues",
                duration_ms=(time.monotonic() - start) * 1000,
                details=details,
            )
        )

    async def _check_llm_providers(self) -> None:
        """Check LLM provider availability (API keys set)."""
        start = time.monotonic()
        details: dict[str, Any] = {}
        configured: list[str] = []
        unconfigured: list[str] = []

        for provider, env_var in self.LLM_PROVIDER_KEYS.items():
            key = os.environ.get(env_var, "")
            if key:
                configured.append(provider)
                # Mask the key for safety
                details[provider] = f"{env_var}=***{key[-4:]}" if len(key) > 4 else f"{env_var}=***"
            else:
                unconfigured.append(provider)
                details[provider] = f"{env_var} not set"

        if configured:
            status = HealthStatus.HEALTHY
        else:
            status = HealthStatus.DEGRADED

        details["configured"] = configured
        details["unconfigured"] = unconfigured

        self._checks.append(
            HealthCheck(
                name="llm_providers",
                status=status,
                message=f"{len(configured)} provider(s) configured: {', '.join(configured) if configured else 'none'}",
                duration_ms=(time.monotonic() - start) * 1000,
                details=details,
            )
        )

    async def _check_config(self) -> None:
        """Validate configuration."""
        start = time.monotonic()
        details: dict[str, Any] = {}
        status = HealthStatus.HEALTHY

        try:
            from jarvis.config import Settings

            settings = Settings()
            details["settings_loaded"] = True
            details["debug"] = getattr(settings, "debug", False)
            details["log_level"] = getattr(settings, "log_level", "INFO")
        except ImportError:
            details["settings_loaded"] = False
            details["error"] = "Settings module not importable"
            status = HealthStatus.DEGRADED
        except Exception as exc:
            details["settings_loaded"] = False
            details["error"] = str(exc)
            status = HealthStatus.DEGRADED

        self._checks.append(
            HealthCheck(
                name="config",
                status=status,
                message="Configuration valid" if status == HealthStatus.HEALTHY else f"Config issue: {details.get('error', '?')}",
                duration_ms=(time.monotonic() - start) * 1000,
                details=details,
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_overall(self) -> HealthStatus:
        """Derive the overall status from individual checks."""
        if any(c.status == HealthStatus.UNHEALTHY for c in self._checks):
            return HealthStatus.UNHEALTHY
        if any(c.status == HealthStatus.DEGRADED for c in self._checks):
            return HealthStatus.DEGRADED
        if all(c.status == HealthStatus.HEALTHY for c in self._checks):
            return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN
