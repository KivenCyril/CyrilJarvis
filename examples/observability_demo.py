#!/usr/bin/env python3
"""observability_demo.py -- Observability system demonstration.

Shows JARVIS's observability stack: distributed tracing with spans,
metrics collection (counters, histograms), system diagnostics, and
benchmarks.

Run:
    python examples/observability_demo.py
"""

from __future__ import annotations

import asyncio
import random
import sys
import time

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.observability.tracer import Span, Tracer
    from jarvis.observability.metrics import Counter, Histogram, Metrics
    from jarvis.diagnostics.health import SystemDiagnostics
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Observability Demo[/bold cyan]",
                        subtitle="Tracing, Metrics, Diagnostics"))

    # -------------------------------------------------------------------
    # 1. Distributed tracing
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Distributed tracing:[/bold]")
    tracer = Tracer()

    # Start a trace
    trace_id = tracer.start_trace("user_request")
    console.print(f"   Trace ID: {trace_id}")

    # Root span: orchestrator
    root_span = tracer.start_span(trace_id, "orchestrator.handle", agent="orchestrator")
    root_span.set_attribute("message", "Fix the login bug")

    # Child span: routing
    route_span = tracer.start_span(trace_id, "orchestrator.route",
                                    parent_span_id=root_span.span_id)
    await asyncio.sleep(0.01)  # simulate work
    route_span.add_event("candidates_scored", count=3, best_agent="code")
    tracer.end_span(route_span.span_id)

    # Child span: agent execution
    agent_span = tracer.start_span(trace_id, "code_agent.execute",
                                    parent_span_id=root_span.span_id,
                                    agent="code")

    # Nested: tool call
    tool_span = tracer.start_span(trace_id, "tool.read_file",
                                   parent_span_id=agent_span.span_id,
                                   tool="read_file", path="/src/auth.py")
    await asyncio.sleep(0.01)
    tracer.end_span(tool_span.span_id)

    # Nested: LLM call
    llm_span = tracer.start_span(trace_id, "llm.chat",
                                  parent_span_id=agent_span.span_id,
                                  model="mock", tokens=150)
    await asyncio.sleep(0.02)
    tracer.end_span(llm_span.span_id)

    tracer.end_span(agent_span.span_id)
    tracer.end_span(root_span.span_id)

    # Show trace
    trace_data = tracer.get_trace(trace_id)
    table = Table(title=f"Trace: {trace_id}")
    table.add_column("Operation", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration (ms)", justify="right", style="yellow")
    table.add_column("Parent", style="dim")

    for span_dict in trace_data:
        table.add_row(
            span_dict["operation"],
            span_dict["status"],
            f"{span_dict['duration_ms']:.1f}",
            span_dict.get("parent_span_id", "-") or "(root)",
        )
    console.print(table)

    # Context manager tracing
    console.print("\n   Context manager tracing:")
    trace_id2 = tracer.start_trace("context_manager_demo")
    async with tracer.trace_operation(trace_id2, "outer_operation") as outer:
        outer.set_attribute("test", True)
        async with tracer.trace_operation(trace_id2, "inner_operation",
                                           parent_span_id=outer.span_id) as inner:
            await asyncio.sleep(0.01)
            inner.add_event("checkpoint", data="inner done")
    console.print(f"   Trace {trace_id2}: {len(tracer.get_trace(trace_id2))} spans")

    # List all traces
    console.print("\n   All traces:")
    for t in tracer.list_traces():
        console.print(f"   - {t['trace_id']}: {t['root_operation']} "
                      f"({t['span_count']} spans, {t['total_duration_ms']:.1f}ms)")

    # -------------------------------------------------------------------
    # 2. Metrics collection
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Metrics collection:[/bold]")
    metrics = Metrics()

    # Counters
    req_counter = metrics.counter("requests_total", agent="code")
    err_counter = metrics.counter("errors_total", agent="code")
    for _ in range(25):
        req_counter.inc()
    for _ in range(3):
        err_counter.inc()
    console.print(f"   requests_total: {req_counter.value}")
    console.print(f"   errors_total: {err_counter.value}")

    # Histograms
    latency_hist = metrics.histogram("request_latency_ms", operation="chat")
    for _ in range(50):
        latency_hist.observe(random.uniform(10, 200))
    console.print(f"   latency p50: {latency_hist.p50:.1f}ms")
    console.print(f"   latency p95: {latency_hist.p95:.1f}ms")
    console.print(f"   latency p99: {latency_hist.p99:.1f}ms")
    console.print(f"   latency avg: {latency_hist.avg:.1f}ms")

    token_hist = metrics.histogram("tokens_per_request")
    for _ in range(30):
        token_hist.observe(random.randint(50, 500))
    console.print(f"   tokens avg: {token_hist.avg:.0f}")

    # Gauges
    metrics.gauge("active_sessions", 5)
    metrics.gauge("memory_usage_mb", 128.5)
    console.print(f"   active_sessions: {metrics.get_gauge('active_sessions')}")
    console.print(f"   memory_usage_mb: {metrics.get_gauge('memory_usage_mb')}")

    # Snapshot
    console.print("\n   Metrics snapshot:")
    snapshot = metrics.snapshot()
    console.print(f"   Counters: {len(snapshot['counters'])}")
    console.print(f"   Histograms: {len(snapshot['histograms'])}")
    console.print(f"   Gauges: {len(snapshot['gauges'])}")

    # -------------------------------------------------------------------
    # 3. System diagnostics
    # -------------------------------------------------------------------
    console.print("\n[bold]3. System diagnostics:[/bold]")
    diagnostics = SystemDiagnostics()
    report = await diagnostics.run_all()

    console.print(report.to_table())

    console.print(f"\n   Healthy: {report.healthy_count}")
    console.print(f"   Degraded: {report.degraded_count}")
    console.print(f"   Unhealthy: {report.unhealthy_count}")

    # -------------------------------------------------------------------
    # 4. Simple benchmarks
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Quick benchmarks:[/bold]")

    # Benchmark spec creation
    from jarvis.models.streaming_spec import StreamingSpec
    start = time.monotonic()
    for i in range(1000):
        spec = StreamingSpec(name=f"test-{i}", intent="benchmark")
        spec.add_step(f"step-{i}")
    elapsed = (time.monotonic() - start) * 1000
    console.print(f"   Create 1000 specs: {elapsed:.1f}ms ({elapsed/1000:.3f}ms each)")

    # Benchmark DAG validation
    spec = StreamingSpec(name="dag-bench", intent="benchmark")
    prev_id = None
    for i in range(50):
        step = spec.add_step(f"step-{i}", depends_on=[prev_id] if prev_id else [])
        prev_id = step.id

    start = time.monotonic()
    for _ in range(100):
        spec.validate_dag()
    elapsed = (time.monotonic() - start) * 1000
    console.print(f"   Validate 50-step DAG x100: {elapsed:.1f}ms ({elapsed/100:.3f}ms each)")

    # Benchmark memory search
    from jarvis.memory.manager import MemoryManager, MemoryType
    import tempfile
    mem = MemoryManager(storage_path=tempfile.mkdtemp())
    for i in range(100):
        await mem.add(f"Memory entry {i} about topic {i % 10}", MemoryType.FACT)
    start = time.monotonic()
    for _ in range(100):
        await mem.search("topic 5")
    elapsed = (time.monotonic() - start) * 1000
    console.print(f"   Search 100 memories x100: {elapsed:.1f}ms ({elapsed/100:.3f}ms each)")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
