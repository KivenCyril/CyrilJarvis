"""Tests for the diagnostics package."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

from jarvis.diagnostics.health import (
    DiagnosticReport,
    HealthCheck,
    HealthStatus,
    SystemDiagnostics,
)


# ── HealthStatus enum ──────────────────────────────────────────────────


class TestHealthStatus:
    def test_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"

    def test_is_str_enum(self):
        assert isinstance(HealthStatus.HEALTHY, str)
        assert HealthStatus.HEALTHY == "healthy"


# ── HealthCheck model ──────────────────────────────────────────────────


class TestHealthCheck:
    def test_defaults(self):
        hc = HealthCheck(name="test")
        assert hc.name == "test"
        assert hc.status == HealthStatus.UNKNOWN
        assert hc.message == ""
        assert hc.duration_ms == 0
        assert hc.details == {}
        assert hc.checked_at is not None

    def test_with_values(self):
        hc = HealthCheck(
            name="cpu",
            status=HealthStatus.HEALTHY,
            message="OK",
            duration_ms=1.23,
            details={"cores": 8},
        )
        assert hc.status == HealthStatus.HEALTHY
        assert hc.details["cores"] == 8
        assert hc.duration_ms == pytest.approx(1.23)

    def test_serialization_roundtrip(self):
        hc = HealthCheck(
            name="roundtrip",
            status=HealthStatus.DEGRADED,
            message="partial",
        )
        data = hc.model_dump(mode="json")
        hc2 = HealthCheck.model_validate(data)
        assert hc2.name == "roundtrip"
        assert hc2.status == HealthStatus.DEGRADED


# ── DiagnosticReport model ─────────────────────────────────────────────


class TestDiagnosticReport:
    def _make_report(self, statuses: list[HealthStatus]) -> DiagnosticReport:
        from datetime import datetime, timezone

        checks = [
            HealthCheck(name=f"check_{i}", status=s, message=s.value)
            for i, s in enumerate(statuses)
        ]
        return DiagnosticReport(
            checks=checks,
            overall_status=HealthStatus.HEALTHY,
            timestamp=datetime.now(timezone.utc),
        )

    def test_counts(self):
        report = self._make_report(
            [HealthStatus.HEALTHY, HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        )
        assert report.healthy_count == 2
        assert report.degraded_count == 1
        assert report.unhealthy_count == 0

    def test_get_check(self):
        report = self._make_report([HealthStatus.HEALTHY])
        assert report.get_check("check_0") is not None
        assert report.get_check("nonexistent") is None

    def test_to_table(self):
        report = self._make_report([HealthStatus.HEALTHY, HealthStatus.UNHEALTHY])
        table = report.to_table()
        assert "System Diagnostics" in table
        assert "check_0" in table
        assert "check_1" in table
        assert "HEALTHY" in table

    def test_empty_report(self):
        from datetime import datetime, timezone

        report = DiagnosticReport(
            checks=[],
            overall_status=HealthStatus.UNKNOWN,
            timestamp=datetime.now(timezone.utc),
        )
        assert report.healthy_count == 0
        assert report.to_table() is not None


# ── SystemDiagnostics ──────────────────────────────────────────────────


class TestSystemDiagnostics:
    @pytest.fixture
    def diag(self):
        return SystemDiagnostics()

    @pytest.mark.asyncio
    async def test_check_python_env(self, diag):
        await diag._check_python_env()
        assert len(diag._checks) == 1
        check = diag._checks[0]
        assert check.name == "python_environment"
        assert check.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
        assert "python_version" in check.details
        assert "installed_packages" in check.details

    @pytest.mark.asyncio
    async def test_check_system_resources(self, diag):
        await diag._check_system_resources()
        assert len(diag._checks) == 1
        check = diag._checks[0]
        assert check.name == "system_resources"
        assert "cpu_count" in check.details
        assert "disk_total_gb" in check.details

    @pytest.mark.asyncio
    async def test_check_modules(self, diag):
        await diag._check_modules()
        assert len(diag._checks) == 1
        check = diag._checks[0]
        assert check.name == "modules"
        assert "available" in check.details
        assert "unavailable" in check.details
        assert isinstance(check.details["available"], list)

    @pytest.mark.asyncio
    async def test_check_llm_providers_no_keys(self, diag):
        # With no API keys set, providers should be degraded
        env = {k: "" for k in SystemDiagnostics.LLM_PROVIDER_KEYS.values()}
        with patch.dict(os.environ, env, clear=False):
            # Remove any existing keys
            for key in SystemDiagnostics.LLM_PROVIDER_KEYS.values():
                os.environ.pop(key, None)
            await diag._check_llm_providers()
        check = diag._checks[0]
        assert check.name == "llm_providers"
        assert check.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_check_llm_providers_with_key(self, diag):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test1234567890"}):
            await diag._check_llm_providers()
        check = diag._checks[0]
        assert check.name == "llm_providers"
        assert check.status == HealthStatus.HEALTHY
        assert "openai" in check.details["configured"]

    @pytest.mark.asyncio
    async def test_check_storage(self, diag):
        await diag._check_storage()
        assert len(diag._checks) == 1
        check = diag._checks[0]
        assert check.name == "storage"
        assert check.details.get("memory_store") == "ok"

    @pytest.mark.asyncio
    async def test_run_all(self, diag):
        report = await diag.run_all()
        assert isinstance(report, DiagnosticReport)
        assert len(report.checks) >= 6  # at least all the main checks
        assert report.overall_status in HealthStatus

    @pytest.mark.asyncio
    async def test_run_check_by_name(self, diag):
        result = await diag.run_check("python_environment")
        assert result is not None
        assert result.name == "python_environment"

    @pytest.mark.asyncio
    async def test_run_check_unknown(self, diag):
        result = await diag.run_check("nonexistent_check")
        assert result is None

    def test_compute_overall_healthy(self, diag):
        diag._checks = [
            HealthCheck(name="a", status=HealthStatus.HEALTHY),
            HealthCheck(name="b", status=HealthStatus.HEALTHY),
        ]
        assert diag._compute_overall() == HealthStatus.HEALTHY

    def test_compute_overall_degraded(self, diag):
        diag._checks = [
            HealthCheck(name="a", status=HealthStatus.HEALTHY),
            HealthCheck(name="b", status=HealthStatus.DEGRADED),
        ]
        assert diag._compute_overall() == HealthStatus.DEGRADED

    def test_compute_overall_unhealthy(self, diag):
        diag._checks = [
            HealthCheck(name="a", status=HealthStatus.HEALTHY),
            HealthCheck(name="b", status=HealthStatus.UNHEALTHY),
        ]
        assert diag._compute_overall() == HealthStatus.UNHEALTHY

    def test_compute_overall_unknown_fallback(self, diag):
        diag._checks = [
            HealthCheck(name="a", status=HealthStatus.UNKNOWN),
        ]
        assert diag._compute_overall() == HealthStatus.UNKNOWN
