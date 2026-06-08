"""Tests for the benchmarks package."""

from __future__ import annotations

import pytest

from jarvis.benchmarks.suite import BenchmarkResult, BenchmarkSuite


# ── BenchmarkResult model ─────────────────────────────────────────────


class TestBenchmarkResult:
    def test_creation(self):
        result = BenchmarkResult(
            name="test",
            iterations=10,
            total_ms=100.0,
            avg_ms=10.0,
            min_ms=5.0,
            max_ms=15.0,
            p50_ms=9.0,
            p95_ms=14.0,
            p99_ms=15.0,
            ops_per_sec=100.0,
        )
        assert result.name == "test"
        assert result.iterations == 10
        assert result.ops_per_sec == pytest.approx(100.0)

    def test_serialization_roundtrip(self):
        result = BenchmarkResult(
            name="ser",
            iterations=5,
            total_ms=50.0,
            avg_ms=10.0,
            min_ms=8.0,
            max_ms=12.0,
            p50_ms=10.0,
            p95_ms=11.5,
            p99_ms=12.0,
            ops_per_sec=100.0,
            metadata={"note": "test"},
        )
        data = result.model_dump(mode="json")
        result2 = BenchmarkResult.model_validate(data)
        assert result2.name == "ser"
        assert result2.metadata["note"] == "test"


# ── BenchmarkSuite ─────────────────────────────────────────────────────


class TestBenchmarkSuite:
    @pytest.fixture
    def suite(self):
        return BenchmarkSuite()

    @pytest.mark.asyncio
    async def test_run_benchmark_collects_timing(self, suite):
        counter = {"n": 0}

        async def dummy():
            counter["n"] += 1

        result = await suite._run_benchmark("dummy", dummy, 20)
        assert result.name == "dummy"
        assert result.iterations == 20
        assert counter["n"] == 20
        assert result.avg_ms > 0 or result.avg_ms == pytest.approx(0, abs=1)
        assert result.min_ms <= result.avg_ms <= result.max_ms
        assert result.p50_ms <= result.p95_ms <= result.p99_ms

    @pytest.mark.asyncio
    async def test_run_benchmark_ops_per_sec(self, suite):
        import asyncio

        async def slow():
            await asyncio.sleep(0.001)  # 1ms

        result = await suite._run_benchmark("slow", slow, 5)
        # Should be around 1000 ops/s give or take
        assert result.ops_per_sec > 0
        assert result.avg_ms >= 0.5  # at least half a ms

    @pytest.mark.asyncio
    async def test_results_accumulate(self, suite):
        async def noop():
            pass

        await suite._run_benchmark("a", noop, 3)
        await suite._run_benchmark("b", noop, 3)
        assert len(suite.results) == 2
        assert suite.results[0].name == "a"
        assert suite.results[1].name == "b"

    @pytest.mark.asyncio
    async def test_bench_spec_creation(self, suite):
        await suite._bench_spec_creation(5)
        assert len(suite.results) == 1
        assert suite.results[0].name == "spec_creation"
        assert suite.results[0].iterations == 5

    @pytest.mark.asyncio
    async def test_bench_context_building(self, suite):
        await suite._bench_context_building(5)
        assert len(suite.results) == 1
        assert suite.results[0].name == "context_building"

    @pytest.mark.asyncio
    async def test_bench_prompt_building(self, suite):
        await suite._bench_prompt_building(5)
        assert len(suite.results) == 1
        assert suite.results[0].name == "prompt_building"

    @pytest.mark.asyncio
    async def test_bench_dag_validation(self, suite):
        await suite._bench_dag_validation(5)
        assert len(suite.results) == 1
        assert "dag_validation" in suite.results[0].name

    @pytest.mark.asyncio
    async def test_bench_serialization(self, suite):
        await suite._bench_serialization(5)
        assert len(suite.results) == 1
        assert suite.results[0].name == "spec_serialization"

    @pytest.mark.asyncio
    async def test_bench_knowledge_query(self, suite):
        await suite._bench_knowledge_query(5)
        assert len(suite.results) == 1
        assert suite.results[0].name == "knowledge_query"

    @pytest.mark.asyncio
    async def test_run_one(self, suite):
        result = await suite.run_one("serialization", iterations=3)
        assert result is not None
        assert result.name == "spec_serialization"
        assert result.iterations == 3

    @pytest.mark.asyncio
    async def test_run_one_unknown(self, suite):
        result = await suite.run_one("nonexistent", iterations=3)
        assert result is None

    def test_percentile_helper(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        assert BenchmarkSuite._percentile(data, 0.50) == 6.0
        assert BenchmarkSuite._percentile(data, 0.95) == 10.0
        assert BenchmarkSuite._percentile([], 0.50) == 0.0

    def test_print_report_plain(self, suite, capsys):
        suite._results = [
            BenchmarkResult(
                name="test_bench",
                iterations=10,
                total_ms=100.0,
                avg_ms=10.0,
                min_ms=5.0,
                max_ms=15.0,
                p50_ms=9.0,
                p95_ms=14.0,
                p99_ms=15.0,
                ops_per_sec=100.0,
            )
        ]
        suite._print_report_plain()
        captured = capsys.readouterr()
        assert "test_bench" in captured.out
        assert "100" in captured.out
