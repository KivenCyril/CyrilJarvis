"""Performance benchmark suite for JARVIS modules.

Benchmarks core operations and reports percentile timing data.
"""

from __future__ import annotations

import statistics
import time
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, Field


class BenchmarkResult(BaseModel):
    """Timing results for a single benchmark."""

    name: str
    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    ops_per_sec: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkSuite:
    """Performance benchmark suite for JARVIS modules.

    Benchmarks:
    - Spec creation and serialization
    - Agent routing
    - Tool execution
    - Memory search
    - Knowledge graph queries
    - JSON storage operations
    - Context building
    - Prompt generation
    - DAG validation
    """

    def __init__(self) -> None:
        self._results: list[BenchmarkResult] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_all(self, iterations: int = 100) -> list[BenchmarkResult]:
        """Run all benchmarks."""
        self._results = []

        await self._bench_spec_creation(iterations)
        await self._bench_agent_routing(iterations)
        await self._bench_tool_execution(iterations)
        await self._bench_memory_search(iterations)
        await self._bench_knowledge_query(iterations)
        await self._bench_json_store(iterations)
        await self._bench_context_building(iterations)
        await self._bench_prompt_building(iterations)
        await self._bench_dag_validation(iterations)
        await self._bench_serialization(iterations)

        return self._results

    async def run_one(self, name: str, iterations: int = 100) -> BenchmarkResult | None:
        """Run a single named benchmark."""
        bench_map: dict[str, Callable] = {
            "spec_creation": self._bench_spec_creation,
            "agent_routing": self._bench_agent_routing,
            "tool_execution": self._bench_tool_execution,
            "memory_search": self._bench_memory_search,
            "knowledge_query": self._bench_knowledge_query,
            "json_store": self._bench_json_store,
            "context_building": self._bench_context_building,
            "prompt_building": self._bench_prompt_building,
            "dag_validation": self._bench_dag_validation,
            "serialization": self._bench_serialization,
        }
        method = bench_map.get(name)
        if method is None:
            return None
        before = len(self._results)
        await method(iterations)
        if len(self._results) > before:
            return self._results[-1]
        return None

    def print_report(self) -> None:
        """Print benchmark results as a formatted table."""
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            table = Table(title="JARVIS Benchmark Results", show_lines=True)
            table.add_column("Benchmark", style="cyan")
            table.add_column("Ops/s", justify="right", style="green")
            table.add_column("Avg (ms)", justify="right")
            table.add_column("P50 (ms)", justify="right")
            table.add_column("P95 (ms)", justify="right")
            table.add_column("P99 (ms)", justify="right")
            table.add_column("Iterations", justify="right", style="dim")

            for r in self._results:
                table.add_row(
                    r.name,
                    f"{r.ops_per_sec:.0f}",
                    f"{r.avg_ms:.2f}",
                    f"{r.p50_ms:.2f}",
                    f"{r.p95_ms:.2f}",
                    f"{r.p99_ms:.2f}",
                    str(r.iterations),
                )
            console.print(table)
        except ImportError:
            # Fallback without rich
            self._print_report_plain()

    def _print_report_plain(self) -> None:
        """Print benchmark results as plain text."""
        header = f"{'Benchmark':<30} {'Ops/s':>10} {'Avg(ms)':>10} {'P50(ms)':>10} {'P95(ms)':>10} {'P99(ms)':>10} {'N':>6}"
        print("\nJARVIS Benchmark Results")
        print("=" * len(header))
        print(header)
        print("-" * len(header))
        for r in self._results:
            print(
                f"{r.name:<30} {r.ops_per_sec:>10.0f} {r.avg_ms:>10.2f} "
                f"{r.p50_ms:>10.2f} {r.p95_ms:>10.2f} {r.p99_ms:>10.2f} {r.iterations:>6}"
            )

    @property
    def results(self) -> list[BenchmarkResult]:
        return list(self._results)

    # ------------------------------------------------------------------
    # Internal benchmark runner
    # ------------------------------------------------------------------

    async def _run_benchmark(
        self,
        name: str,
        func: Callable[[], Coroutine[Any, Any, Any]],
        iterations: int,
        **metadata: Any,
    ) -> BenchmarkResult:
        """Run a single benchmark and collect timing data."""
        times: list[float] = []
        for _ in range(iterations):
            start = time.perf_counter()
            await func()
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        times.sort()
        total = sum(times)
        avg = total / len(times) if times else 0
        result = BenchmarkResult(
            name=name,
            iterations=iterations,
            total_ms=total,
            avg_ms=avg,
            min_ms=times[0] if times else 0,
            max_ms=times[-1] if times else 0,
            p50_ms=self._percentile(times, 0.50),
            p95_ms=self._percentile(times, 0.95),
            p99_ms=self._percentile(times, 0.99),
            ops_per_sec=(1000 / avg) if avg > 0 else 0,
            metadata=metadata,
        )
        self._results.append(result)
        return result

    @staticmethod
    def _percentile(sorted_data: list[float], pct: float) -> float:
        """Return the *pct*-th percentile from already-sorted data."""
        if not sorted_data:
            return 0.0
        idx = int(len(sorted_data) * pct)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    # ------------------------------------------------------------------
    # Individual benchmarks
    # ------------------------------------------------------------------

    async def _bench_spec_creation(self, n: int) -> None:
        """Benchmark StreamingSpec creation with steps."""
        from jarvis.models.streaming_spec import ChangeSource, StreamingSpec

        async def create_spec() -> None:
            spec = StreamingSpec(name="bench", intent="benchmark test")
            for i in range(5):
                spec.add_step(f"Step {i}", source=ChangeSource.AGENT)

        await self._run_benchmark("spec_creation", create_spec, n)

    async def _bench_agent_routing(self, n: int) -> None:
        """Benchmark agent routing (score computation)."""
        from jarvis.agents.registry import AgentRegistry

        registry = AgentRegistry()

        # Register mock agents if possible
        try:
            from jarvis.agents.base import AgentCard, BaseAgent

            class _MockAgent(BaseAgent):
                def __init__(self, name: str, skills: list[str], domain: str = "general"):
                    card = AgentCard(
                        name=name,
                        description=f"Mock {name}",
                        skills=skills,
                        domain=domain,
                    )
                    super().__init__(name=name, card=card)

                async def execute(self, message, context=None):
                    pass

            await registry.register(_MockAgent("code", ["review", "generate", "debug"], "code"))
            await registry.register(_MockAgent("knowledge", ["search", "qa", "summarize"], "knowledge"))
            await registry.register(_MockAgent("data", ["analyze", "visualize", "transform"], "data"))
        except Exception:
            pass

        async def route() -> None:
            registry.route("review this code for bugs")

        await self._run_benchmark("agent_routing", route, n)

    async def _bench_tool_execution(self, n: int) -> None:
        """Benchmark a lightweight tool execution (echo)."""
        try:
            from jarvis.tools.builtin.shell import ShellTool

            tool = ShellTool()

            async def execute() -> None:
                await tool.execute({"command": "echo test"})

            await self._run_benchmark("tool_shell_echo", execute, min(n, 50))
        except ImportError:
            # Tool module not available -- use a no-op fallback
            async def noop() -> None:
                pass

            await self._run_benchmark("tool_shell_echo", noop, min(n, 50), note="ShellTool not importable")

    async def _bench_memory_search(self, n: int) -> None:
        """Benchmark memory search."""
        import tempfile

        from jarvis.memory import MemoryManager, MemoryType

        tmpdir = tempfile.mkdtemp(prefix="jarvis_bench_mem_")
        mm = MemoryManager(tmpdir)
        for i in range(20):
            await mm.add(
                f"Memory entry {i} about Python programming and data science",
                MemoryType.FACT,
            )

        async def search() -> None:
            await mm.search("Python")

        await self._run_benchmark("memory_search", search, n)

    async def _bench_knowledge_query(self, n: int) -> None:
        """Benchmark knowledge graph traversal."""
        from jarvis.knowledge.graph import GraphEdge, GraphNode, KnowledgeGraph

        kg = KnowledgeGraph()
        for i in range(50):
            kg.add_node(
                GraphNode(id=f"n{i}", label=f"Entity {i}", node_type="concept")
            )
        for i in range(30):
            kg.add_edge(
                GraphEdge(source=f"n{i}", target=f"n{i + 1}", relation="related")
            )

        async def query() -> None:
            await kg.query("Entity")

        await self._run_benchmark("knowledge_query", query, n)

    async def _bench_json_store(self, n: int) -> None:
        """Benchmark JSON store write/read cycle."""
        import shutil
        import tempfile

        from jarvis.storage import JSONStore

        tmpdir = tempfile.mkdtemp(prefix="jarvis_bench_store_")
        store = JSONStore(tmpdir)

        async def write_read() -> None:
            await store.put("bench_key", {"data": "test", "value": 42})
            await store.get("bench_key")

        await self._run_benchmark("json_store_write_read", write_read, n)

        # Cleanup
        shutil.rmtree(tmpdir, ignore_errors=True)

    async def _bench_context_building(self, n: int) -> None:
        """Benchmark context assembly."""
        from jarvis.agents.context import ContextBuilder

        builder = ContextBuilder()

        async def build() -> None:
            builder.build(
                system_prompt="You are a helpful assistant " * 10,
                memory_context="User likes Python " * 5,
                knowledge_context="Graph context " * 5,
                constraints=["constraint 1", "constraint 2", "constraint 3"],
            )

        await self._run_benchmark("context_building", build, n)

    async def _bench_prompt_building(self, n: int) -> None:
        """Benchmark prompt builder assembly."""
        from jarvis.prompts import PromptBuilder

        async def build() -> None:
            pb = PromptBuilder()
            pb.add_system_identity("test-agent", "a test agent")
            pb.add_capabilities(["tool1", "tool2"], ["skill1", "skill2"])
            pb.add_constraints(["c1", "c2", "c3"])
            pb.add_context("some context data " * 20)
            pb.build()

        await self._run_benchmark("prompt_building", build, n)

    async def _bench_dag_validation(self, n: int) -> None:
        """Benchmark DAG validation and topological sort on a 20-step chain."""
        from jarvis.models.streaming_spec import ChangeSource, StreamingSpec

        spec = StreamingSpec(name="bench", intent="benchmark")
        steps = [
            spec.add_step(f"Step {i}", source=ChangeSource.AGENT)
            for i in range(20)
        ]
        for i in range(1, len(steps)):
            steps[i].depends_on = [steps[i - 1].id]

        async def validate() -> None:
            spec.validate_dag()
            spec.topological_sort()

        await self._run_benchmark("dag_validation_20_steps", validate, n)

    async def _bench_serialization(self, n: int) -> None:
        """Benchmark Pydantic serialization/deserialization of a StreamingSpec."""
        from jarvis.models.streaming_spec import ChangeSource, StreamingSpec

        spec = StreamingSpec(name="bench", intent="serialization benchmark")
        for i in range(10):
            spec.add_step(f"Step {i}", source=ChangeSource.AGENT)
            spec.add_constraint(f"Constraint {i}")

        async def serialize() -> None:
            data = spec.model_dump(mode="json")
            StreamingSpec.model_validate(data)

        await self._run_benchmark("spec_serialization", serialize, n)


# ------------------------------------------------------------------
# Convenience entry point
# ------------------------------------------------------------------


async def run_benchmarks(iterations: int = 100) -> list[BenchmarkResult]:
    """Run all benchmarks and print the report."""
    suite = BenchmarkSuite()
    results = await suite.run_all(iterations)
    suite.print_report()
    return results
