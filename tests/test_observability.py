"""Tests for observability: tracing and metrics."""
import pytest
import asyncio
import json
import time
from pathlib import Path

from jarvis.observability import Tracer, Span, Metrics
from jarvis.observability.metrics import Counter, Histogram


# ── Span ──

class TestSpan:
    def test_span_creation(self):
        span = Span(trace_id="abc123", operation="test_op")
        assert span.trace_id == "abc123"
        assert span.operation == "test_op"
        assert span.status == "ok"
        assert span.duration_ms == 0

    def test_span_end(self):
        span = Span(trace_id="abc123", operation="test_op")
        time.sleep(0.01)
        span.end("ok")
        assert span.ended_at is not None
        assert span.duration_ms > 0
        assert span.status == "ok"

    def test_span_end_error(self):
        span = Span(trace_id="abc123", operation="fail_op")
        span.end("error")
        assert span.status == "error"

    def test_add_event(self):
        span = Span(trace_id="abc123")
        span.add_event("checkpoint", step=1)
        assert len(span.events) == 1
        assert span.events[0]["name"] == "checkpoint"
        assert span.events[0]["step"] == 1

    def test_set_attribute(self):
        span = Span(trace_id="abc123")
        span.set_attribute("model", "gpt-4")
        assert span.attributes["model"] == "gpt-4"

    def test_to_dict(self):
        span = Span(trace_id="abc123", operation="test")
        span.set_attribute("key", "val")
        span.end()
        d = span.to_dict()
        assert d["trace_id"] == "abc123"
        assert d["operation"] == "test"
        assert d["attributes"]["key"] == "val"
        assert d["duration_ms"] >= 0


# ── Tracer ──

class TestTracer:
    def test_start_trace(self):
        tracer = Tracer()
        tid = tracer.start_trace("root")
        assert len(tid) == 16
        assert tid in tracer._traces

    def test_start_and_end_span(self):
        tracer = Tracer()
        tid = tracer.start_trace()
        span = tracer.start_span(tid, "my_op", model="gpt-4")
        assert span.operation == "my_op"
        assert span.attributes["model"] == "gpt-4"
        assert span.span_id in tracer._active_spans

        tracer.end_span(span.span_id)
        assert span.span_id not in tracer._active_spans
        assert span.status == "ok"
        assert span.duration_ms >= 0

    def test_end_span_error(self):
        tracer = Tracer()
        tid = tracer.start_trace()
        span = tracer.start_span(tid, "failing")
        tracer.end_span(span.span_id, status="error")
        assert span.status == "error"

    def test_end_nonexistent_span(self):
        tracer = Tracer()
        tracer.end_span("nonexistent")  # should not raise

    def test_parent_child_spans(self):
        tracer = Tracer()
        tid = tracer.start_trace()
        parent = tracer.start_span(tid, "parent_op")
        child = tracer.start_span(tid, "child_op", parent_span_id=parent.span_id)
        assert child.parent_span_id == parent.span_id

    def test_get_trace(self):
        tracer = Tracer()
        tid = tracer.start_trace()
        tracer.start_span(tid, "op1")
        tracer.start_span(tid, "op2")
        trace = tracer.get_trace(tid)
        assert len(trace) == 2
        assert trace[0]["operation"] == "op1"
        assert trace[1]["operation"] == "op2"

    def test_get_trace_nonexistent(self):
        tracer = Tracer()
        assert tracer.get_trace("nope") == []

    def test_list_traces(self):
        tracer = Tracer()
        tid1 = tracer.start_trace()
        span1 = tracer.start_span(tid1, "op1")
        span1.end()
        tid2 = tracer.start_trace()
        span2 = tracer.start_span(tid2, "op2")
        span2.end("error")

        traces = tracer.list_traces()
        assert len(traces) == 2
        # Find the error trace
        error_traces = [t for t in traces if t["status"] == "error"]
        assert len(error_traces) == 1

    def test_list_traces_limit(self):
        tracer = Tracer()
        for i in range(10):
            tid = tracer.start_trace()
            tracer.start_span(tid, f"op-{i}")
        assert len(tracer.list_traces(limit=3)) == 3

    def test_save_trace(self, tmp_path):
        tracer = Tracer(storage_path=str(tmp_path / "traces"))
        tid = tracer.start_trace()
        span = tracer.start_span(tid, "saved_op")
        span.end()
        tracer.save_trace(tid)

        fp = tmp_path / "traces" / f"{tid}.json"
        assert fp.exists()
        data = json.loads(fp.read_text())
        assert len(data) == 1
        assert data[0]["operation"] == "saved_op"

    def test_save_trace_no_storage(self):
        tracer = Tracer()  # no storage_path
        tid = tracer.start_trace()
        tracer.save_trace(tid)  # should not raise

    @pytest.mark.asyncio
    async def test_trace_operation_success(self):
        tracer = Tracer()
        tid = tracer.start_trace()
        async with tracer.trace_operation(tid, "async_op", key="val") as span:
            assert span.operation == "async_op"
            assert span.attributes["key"] == "val"
        assert span.status == "ok"
        assert span.duration_ms >= 0
        assert span.span_id not in tracer._active_spans

    @pytest.mark.asyncio
    async def test_trace_operation_error(self):
        tracer = Tracer()
        tid = tracer.start_trace()
        with pytest.raises(ValueError, match="boom"):
            async with tracer.trace_operation(tid, "fail_op") as span:
                raise ValueError("boom")
        assert span.status == "error"
        assert span.attributes["error.message"] == "boom"
        assert span.span_id not in tracer._active_spans


# ── Counter ──

class TestCounter:
    def test_inc_default(self):
        c = Counter(name="requests")
        c.inc()
        assert c.value == 1

    def test_inc_amount(self):
        c = Counter(name="tokens")
        c.inc(100)
        c.inc(50)
        assert c.value == 150


# ── Histogram ──

class TestHistogram:
    def test_observe(self):
        h = Histogram(name="latency")
        h.observe(10.0)
        h.observe(20.0)
        h.observe(30.0)
        assert h.count == 3
        assert h.sum == 60.0
        assert h.avg == 20.0

    def test_percentiles(self):
        h = Histogram(name="latency")
        for i in range(1, 101):
            h.observe(float(i))
        # _percentile uses floor-index: idx = int(N * p / 100)
        # For N=100: p50 -> idx 50 -> value 51, p95 -> idx 95 -> value 96, p99 -> idx 99 -> value 100
        assert h.p50 == 51.0
        assert h.p95 == 96.0
        assert h.p99 == 100.0

    def test_empty_histogram(self):
        h = Histogram(name="empty")
        assert h.count == 0
        assert h.sum == 0
        assert h.avg == 0
        assert h.p50 == 0
        assert h.p95 == 0
        assert h.p99 == 0


# ── Metrics ──

class TestMetrics:
    def test_counter(self):
        m = Metrics()
        c = m.counter("requests")
        c.inc()
        c.inc(5)
        assert m.counter("requests").value == 6

    def test_counter_with_labels(self):
        m = Metrics()
        c1 = m.counter("requests", agent="planner")
        c2 = m.counter("requests", agent="executor")
        c1.inc()
        c2.inc(3)
        assert c1.value == 1
        assert c2.value == 3
        # Same labels returns same counter
        assert m.counter("requests", agent="planner").value == 1

    def test_histogram(self):
        m = Metrics()
        h = m.histogram("latency_ms")
        h.observe(50.0)
        h.observe(100.0)
        assert m.histogram("latency_ms").count == 2

    def test_histogram_with_labels(self):
        m = Metrics()
        h1 = m.histogram("latency", op="llm")
        h2 = m.histogram("latency", op="tool")
        h1.observe(100.0)
        h2.observe(10.0)
        assert h1.count == 1
        assert h2.count == 1

    def test_gauge(self):
        m = Metrics()
        m.gauge("active_sessions", 5.0)
        assert m.get_gauge("active_sessions") == 5.0
        m.gauge("active_sessions", 3.0)
        assert m.get_gauge("active_sessions") == 3.0

    def test_get_gauge_default(self):
        m = Metrics()
        assert m.get_gauge("nonexistent") == 0

    def test_snapshot(self):
        m = Metrics()
        m.counter("reqs").inc(10)
        m.histogram("lat").observe(50.0)
        m.gauge("active", 2.0)

        snap = m.snapshot()
        assert "counters" in snap
        assert "histograms" in snap
        assert "gauges" in snap
        assert snap["gauges"]["active"] == 2.0
        # Check counter in snapshot
        counter_snap = snap["counters"]["reqs"]
        assert counter_snap["value"] == 10
        # Check histogram in snapshot
        hist_snap = snap["histograms"]["lat"]
        assert hist_snap["count"] == 1
        assert hist_snap["avg"] == 50.0

    def test_reset(self):
        m = Metrics()
        m.counter("c").inc()
        m.histogram("h").observe(1.0)
        m.gauge("g", 1.0)
        m.reset()
        snap = m.snapshot()
        assert snap["counters"] == {}
        assert snap["histograms"] == {}
        assert snap["gauges"] == {}
