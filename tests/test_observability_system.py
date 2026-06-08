"""Observability system tests.

Tests metrics collection, trace management, span tracking,
health checks, performance monitoring, and alerting.
"""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Metrics Models
# ---------------------------------------------------------------------------

@dataclass
class MetricPoint:
    name: str
    value: float
    timestamp: float = 0
    tags: dict[str, str] = field(default_factory=dict)
    metric_type: str = "gauge"  # gauge, counter, histogram

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class Counter:
    name: str
    value: float = 0
    tags: dict[str, str] = field(default_factory=dict)

    def increment(self, amount: float = 1.0) -> None:
        self.value += amount

    def reset(self) -> None:
        self.value = 0


@dataclass
class Gauge:
    name: str
    value: float = 0
    tags: dict[str, str] = field(default_factory=dict)

    def set(self, value: float) -> None:
        self.value = value

    def increment(self, amount: float = 1.0) -> None:
        self.value += amount

    def decrement(self, amount: float = 1.0) -> None:
        self.value -= amount


@dataclass
class Histogram:
    name: str
    values: list[float] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    def observe(self, value: float) -> None:
        self.values.append(value)

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def sum(self) -> float:
        return sum(self.values) if self.values else 0

    @property
    def mean(self) -> float:
        return self.sum / self.count if self.count > 0 else 0

    @property
    def min(self) -> float:
        return min(self.values) if self.values else 0

    @property
    def max(self) -> float:
        return max(self.values) if self.values else 0

    def percentile(self, p: float) -> float:
        if not self.values:
            return 0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * p / 100)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]


class MetricsCollector:
    """Collect and manage application metrics."""

    def __init__(self):
        self.counters: dict[str, Counter] = {}
        self.gauges: dict[str, Gauge] = {}
        self.histograms: dict[str, Histogram] = {}
        self.points: list[MetricPoint] = []

    def counter(self, name: str, tags: dict[str, str] | None = None) -> Counter:
        key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
        if key not in self.counters:
            self.counters[key] = Counter(name=name, tags=tags or {})
        return self.counters[key]

    def gauge(self, name: str, tags: dict[str, str] | None = None) -> Gauge:
        key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
        if key not in self.gauges:
            self.gauges[key] = Gauge(name=name, tags=tags or {})
        return self.gauges[key]

    def histogram(self, name: str, tags: dict[str, str] | None = None) -> Histogram:
        key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
        if key not in self.histograms:
            self.histograms[key] = Histogram(name=name, tags=tags or {})
        return self.histograms[key]

    def record(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        self.points.append(MetricPoint(name=name, value=value, tags=tags or {}))

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": {k: {"name": c.name, "value": c.value} for k, c in self.counters.items()},
            "gauges": {k: {"name": g.name, "value": g.value} for k, g in self.gauges.items()},
            "histograms": {k: {"name": h.name, "count": h.count, "mean": h.mean} for k, h in self.histograms.items()},
            "total_points": len(self.points),
        }


# ---------------------------------------------------------------------------
# Trace Models
# ---------------------------------------------------------------------------

@dataclass
class Span:
    trace_id: str
    span_id: str
    name: str
    service: str = "jarvis"
    parent_span_id: str | None = None
    start_time: float = 0
    end_time: float = 0
    duration_ms: float = 0
    status: str = "ok"  # ok, error
    tags: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def finish(self) -> None:
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)

    def set_error(self, error: str) -> None:
        self.status = "error"
        self.events.append({"type": "error", "message": error, "timestamp": time.time()})

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        self.events.append({
            "type": "event",
            "name": name,
            "attributes": attributes or {},
            "timestamp": time.time(),
        })

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "service": self.service,
            "parent_span_id": self.parent_span_id,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "tags": self.tags,
            "events": self.events,
        }


@dataclass
class Trace:
    trace_id: str
    spans: list[Span] = field(default_factory=list)
    root_span: Span | None = None

    def add_span(self, span: Span) -> None:
        self.spans.append(span)
        if span.parent_span_id is None:
            self.root_span = span

    @property
    def duration_ms(self) -> float:
        if self.root_span:
            return self.root_span.duration_ms
        return sum(s.duration_ms for s in self.spans)

    @property
    def span_count(self) -> int:
        return len(self.spans)

    @property
    def has_errors(self) -> bool:
        return any(s.status == "error" for s in self.spans)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_count": self.span_count,
            "duration_ms": self.duration_ms,
            "has_errors": self.has_errors,
            "spans": [s.to_dict() for s in self.spans],
        }


class TraceCollector:
    """Collect and manage distributed traces."""

    def __init__(self):
        self.traces: dict[str, Trace] = {}
        self._span_counter = 0

    def start_trace(self, name: str) -> tuple[Trace, Span]:
        import uuid
        trace_id = str(uuid.uuid4())[:8]
        span_id = self._next_span_id()
        span = Span(
            trace_id=trace_id, span_id=span_id, name=name,
            start_time=time.time(),
        )
        trace = Trace(trace_id=trace_id)
        trace.add_span(span)
        self.traces[trace_id] = trace
        return trace, span

    def start_span(self, trace_id: str, name: str,
                   parent_span_id: str | None = None) -> Span | None:
        trace = self.traces.get(trace_id)
        if not trace:
            return None
        span_id = self._next_span_id()
        span = Span(
            trace_id=trace_id, span_id=span_id, name=name,
            parent_span_id=parent_span_id,
            start_time=time.time(),
        )
        trace.add_span(span)
        return span

    def get_trace(self, trace_id: str) -> Trace | None:
        return self.traces.get(trace_id)

    def list_traces(self, limit: int = 50) -> list[Trace]:
        return list(self.traces.values())[-limit:]

    def _next_span_id(self) -> str:
        self._span_counter += 1
        return f"span-{self._span_counter:04d}"


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@dataclass
class HealthCheck:
    name: str
    status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    message: str = ""
    latency_ms: float = 0
    last_checked: str = ""

    def check(self, checker: Any = None) -> None:
        start = time.time()
        try:
            if checker:
                checker()
            self.status = "healthy"
            self.message = "OK"
        except Exception as exc:
            self.status = "unhealthy"
            self.message = str(exc)
        self.latency_ms = round((time.time() - start) * 1000, 2)
        self.last_checked = datetime.datetime.utcnow().isoformat()


class HealthManager:
    """Manage system health checks."""

    def __init__(self):
        self.checks: dict[str, HealthCheck] = {}

    def register(self, name: str, checker: Any = None) -> HealthCheck:
        check = HealthCheck(name=name)
        self.checks[name] = check
        return check

    def run_all(self) -> dict[str, str]:
        results = {}
        for name, check in self.checks.items():
            check.check()
            results[name] = check.status
        return results

    @property
    def overall_status(self) -> str:
        statuses = [c.status for c in self.checks.values()]
        if all(s == "healthy" for s in statuses):
            return "healthy"
        if any(s == "unhealthy" for s in statuses):
            return "unhealthy"
        return "degraded"


# ---------------------------------------------------------------------------
# Tests: Counter
# ---------------------------------------------------------------------------

class TestCounter:
    def test_create(self):
        c = Counter(name="requests")
        assert c.value == 0

    def test_increment(self):
        c = Counter(name="requests")
        c.increment()
        assert c.value == 1

    def test_increment_by(self):
        c = Counter(name="bytes")
        c.increment(100)
        assert c.value == 100

    def test_multiple_increments(self):
        c = Counter(name="events")
        for _ in range(10):
            c.increment()
        assert c.value == 10

    def test_reset(self):
        c = Counter(name="events")
        c.increment(50)
        c.reset()
        assert c.value == 0


# ---------------------------------------------------------------------------
# Tests: Gauge
# ---------------------------------------------------------------------------

class TestGauge:
    def test_create(self):
        g = Gauge(name="temperature")
        assert g.value == 0

    def test_set(self):
        g = Gauge(name="temperature")
        g.set(72.5)
        assert g.value == 72.5

    def test_increment(self):
        g = Gauge(name="active_connections")
        g.increment()
        assert g.value == 1

    def test_decrement(self):
        g = Gauge(name="active_connections")
        g.set(5)
        g.decrement()
        assert g.value == 4

    def test_negative(self):
        g = Gauge(name="balance")
        g.decrement(10)
        assert g.value == -10


# ---------------------------------------------------------------------------
# Tests: Histogram
# ---------------------------------------------------------------------------

class TestHistogram:
    def test_create(self):
        h = Histogram(name="latency")
        assert h.count == 0

    def test_observe(self):
        h = Histogram(name="latency")
        h.observe(100)
        h.observe(200)
        h.observe(150)
        assert h.count == 3

    def test_sum(self):
        h = Histogram(name="latency")
        h.observe(100)
        h.observe(200)
        assert h.sum == 300

    def test_mean(self):
        h = Histogram(name="latency")
        h.observe(100)
        h.observe(200)
        assert h.mean == 150

    def test_min_max(self):
        h = Histogram(name="latency")
        h.observe(50)
        h.observe(100)
        h.observe(200)
        assert h.min == 50
        assert h.max == 200

    def test_percentile(self):
        h = Histogram(name="latency")
        for i in range(100):
            h.observe(i)
        p50 = h.percentile(50)
        assert 45 <= p50 <= 55

    def test_percentile_p99(self):
        h = Histogram(name="latency")
        for i in range(100):
            h.observe(i)
        p99 = h.percentile(99)
        assert p99 >= 95

    def test_empty_histogram(self):
        h = Histogram(name="empty")
        assert h.mean == 0
        assert h.min == 0
        assert h.max == 0
        assert h.percentile(50) == 0


# ---------------------------------------------------------------------------
# Tests: MetricsCollector
# ---------------------------------------------------------------------------

class TestMetricsCollector:
    def test_counter(self):
        mc = MetricsCollector()
        c = mc.counter("requests_total")
        c.increment()
        c.increment()
        assert c.value == 2

    def test_gauge(self):
        mc = MetricsCollector()
        g = mc.gauge("cpu_usage")
        g.set(45.5)
        assert g.value == 45.5

    def test_histogram(self):
        mc = MetricsCollector()
        h = mc.histogram("response_time_ms")
        h.observe(100)
        h.observe(200)
        assert h.count == 2

    def test_record_point(self):
        mc = MetricsCollector()
        mc.record("temperature", 72.5, {"location": "office"})
        assert len(mc.points) == 1

    def test_snapshot(self):
        mc = MetricsCollector()
        mc.counter("requests").increment(10)
        mc.gauge("cpu").set(50)
        mc.histogram("latency").observe(100)
        snapshot = mc.snapshot()
        assert snapshot["total_points"] == 0
        assert len(snapshot["counters"]) == 1
        assert len(snapshot["gauges"]) == 1

    def test_same_counter_returned(self):
        mc = MetricsCollector()
        c1 = mc.counter("requests")
        c2 = mc.counter("requests")
        assert c1 is c2

    def test_tagged_metrics(self):
        mc = MetricsCollector()
        c1 = mc.counter("requests", {"method": "GET"})
        c2 = mc.counter("requests", {"method": "POST"})
        c1.increment(10)
        c2.increment(5)
        assert c1.value == 10
        assert c2.value == 5


# ---------------------------------------------------------------------------
# Tests: Span
# ---------------------------------------------------------------------------

class TestSpan:
    def test_create_span(self):
        s = Span(trace_id="t1", span_id="s1", name="test", start_time=time.time())
        assert s.status == "ok"
        assert s.duration_ms == 0

    def test_finish_span(self):
        s = Span(trace_id="t1", span_id="s1", name="test", start_time=time.time())
        time.sleep(0.01)
        s.finish()
        assert s.duration_ms > 0
        assert s.end_time > s.start_time

    def test_error_span(self):
        s = Span(trace_id="t1", span_id="s1", name="test")
        s.set_error("something failed")
        assert s.status == "error"
        assert len(s.events) == 1

    def test_add_event(self):
        s = Span(trace_id="t1", span_id="s1", name="test")
        s.add_event("cache_hit", {"key": "user:1"})
        assert len(s.events) == 1
        assert s.events[0]["name"] == "cache_hit"

    def test_span_to_dict(self):
        s = Span(trace_id="t1", span_id="s1", name="test", service="api")
        d = s.to_dict()
        assert d["trace_id"] == "t1"
        assert d["name"] == "test"
        assert d["service"] == "api"

    def test_child_span(self):
        parent = Span(trace_id="t1", span_id="s1", name="parent")
        child = Span(trace_id="t1", span_id="s2", name="child", parent_span_id="s1")
        assert child.parent_span_id == "s1"


# ---------------------------------------------------------------------------
# Tests: Trace
# ---------------------------------------------------------------------------

class TestTrace:
    def test_create_trace(self):
        trace = Trace(trace_id="t1")
        assert trace.span_count == 0

    def test_add_span(self):
        trace = Trace(trace_id="t1")
        span = Span(trace_id="t1", span_id="s1", name="root")
        trace.add_span(span)
        assert trace.span_count == 1
        assert trace.root_span is span

    def test_has_errors(self):
        trace = Trace(trace_id="t1")
        s1 = Span(trace_id="t1", span_id="s1", name="ok")
        s2 = Span(trace_id="t1", span_id="s2", name="fail")
        s2.set_error("failed")
        trace.add_span(s1)
        trace.add_span(s2)
        assert trace.has_errors is True

    def test_no_errors(self):
        trace = Trace(trace_id="t1")
        trace.add_span(Span(trace_id="t1", span_id="s1", name="ok"))
        assert trace.has_errors is False

    def test_trace_to_dict(self):
        trace = Trace(trace_id="t1")
        trace.add_span(Span(trace_id="t1", span_id="s1", name="root"))
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert d["span_count"] == 1


# ---------------------------------------------------------------------------
# Tests: TraceCollector
# ---------------------------------------------------------------------------

class TestTraceCollector:
    def test_start_trace(self):
        tc = TraceCollector()
        trace, span = tc.start_trace("test-operation")
        assert trace.trace_id != ""
        assert span.name == "test-operation"

    def test_add_child_span(self):
        tc = TraceCollector()
        trace, root = tc.start_trace("parent")
        child = tc.start_span(trace.trace_id, "child", root.span_id)
        assert child is not None
        assert child.parent_span_id == root.span_id
        assert trace.span_count == 2

    def test_get_trace(self):
        tc = TraceCollector()
        trace, _ = tc.start_trace("test")
        found = tc.get_trace(trace.trace_id)
        assert found is not None
        assert found.trace_id == trace.trace_id

    def test_get_nonexistent_trace(self):
        tc = TraceCollector()
        assert tc.get_trace("missing") is None

    def test_list_traces(self):
        tc = TraceCollector()
        tc.start_trace("a")
        tc.start_trace("b")
        tc.start_trace("c")
        traces = tc.list_traces()
        assert len(traces) == 3


# ---------------------------------------------------------------------------
# Tests: HealthCheck
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_healthy_check(self):
        check = HealthCheck(name="db")
        check.check(checker=lambda: None)
        assert check.status == "healthy"

    def test_unhealthy_check(self):
        check = HealthCheck(name="db")
        check.check(checker=lambda: (_ for _ in ()).throw(RuntimeError("connection failed")))
        assert check.status == "unhealthy"
        assert "connection failed" in check.message

    def test_latency_tracked(self):
        check = HealthCheck(name="db")
        check.check()
        assert check.latency_ms >= 0

    def test_timestamp_set(self):
        check = HealthCheck(name="db")
        check.check()
        assert check.last_checked != ""


# ---------------------------------------------------------------------------
# Tests: HealthManager
# ---------------------------------------------------------------------------

class TestHealthManager:
    def test_register_check(self):
        mgr = HealthManager()
        check = mgr.register("database")
        assert check.name == "database"

    def test_run_all(self):
        mgr = HealthManager()
        mgr.register("db")
        mgr.register("cache")
        mgr.register("api")
        results = mgr.run_all()
        assert len(results) == 3
        assert all(v == "healthy" for v in results.values())

    def test_overall_healthy(self):
        mgr = HealthManager()
        mgr.register("a")
        mgr.register("b")
        mgr.run_all()
        assert mgr.overall_status == "healthy"

    def test_overall_unhealthy(self):
        mgr = HealthManager()
        mgr.register("a")
        mgr.checks["a"].status = "unhealthy"
        assert mgr.overall_status == "unhealthy"

    def test_overall_degraded(self):
        mgr = HealthManager()
        mgr.register("a")
        mgr.register("b")
        mgr.checks["a"].status = "healthy"
        mgr.checks["b"].status = "degraded"
        assert mgr.overall_status == "degraded"
