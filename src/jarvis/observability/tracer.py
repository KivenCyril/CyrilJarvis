from __future__ import annotations
import logging, time, uuid, json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

@dataclass
class Span:
    """A single operation span in a trace.

    Follows OpenTelemetry span semantics.
    """
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    operation: str = ""
    service: str = "jarvis"
    status: str = "ok"  # ok, error
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    duration_ms: float = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def end(self, status: str = "ok") -> None:
        self.ended_at = time.monotonic()
        self.duration_ms = (self.ended_at - self.started_at) * 1000
        self.status = status

    def add_event(self, name: str, **attrs) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.monotonic(),
            **attrs,
        })

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation": self.operation,
            "service": self.service,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "attributes": self.attributes,
            "events": self.events,
        }

class Tracer:
    """Distributed tracing for JARVIS operations.

    Tracks:
    - Agent executions (which agent, duration, success)
    - Tool calls (which tool, arguments, result)
    - LLM calls (model, tokens, latency)
    - Spec execution (step timings, dependencies)
    - End-to-end request traces

    Stores traces in memory and optionally persists to JSON files.
    """

    def __init__(self, storage_path: str | None = None):
        self._traces: dict[str, list[Span]] = {}  # trace_id -> spans
        self._storage_path = Path(storage_path) if storage_path else None
        self._active_spans: dict[str, Span] = {}  # span_id -> span

    def start_trace(self, operation: str = "") -> str:
        trace_id = uuid.uuid4().hex[:16]
        self._traces[trace_id] = []
        return trace_id

    def start_span(
        self,
        trace_id: str,
        operation: str,
        parent_span_id: str | None = None,
        **attributes,
    ) -> Span:
        span = Span(
            trace_id=trace_id,
            operation=operation,
            parent_span_id=parent_span_id,
            attributes=attributes,
        )
        self._traces.setdefault(trace_id, []).append(span)
        self._active_spans[span.span_id] = span
        return span

    def end_span(self, span_id: str, status: str = "ok") -> None:
        span = self._active_spans.pop(span_id, None)
        if span:
            span.end(status)

    @asynccontextmanager
    async def trace_operation(self, trace_id: str, operation: str, parent_span_id: str | None = None, **attrs):
        """Context manager for tracing an async operation."""
        span = self.start_span(trace_id, operation, parent_span_id, **attrs)
        try:
            yield span
            span.end("ok")
        except Exception as e:
            span.end("error")
            span.set_attribute("error.message", str(e))
            raise
        finally:
            self._active_spans.pop(span.span_id, None)

    def get_trace(self, trace_id: str) -> list[dict]:
        spans = self._traces.get(trace_id, [])
        return [s.to_dict() for s in spans]

    def list_traces(self, limit: int = 50) -> list[dict]:
        result = []
        for trace_id, spans in list(self._traces.items())[-limit:]:
            if spans:
                total_duration = sum(s.duration_ms for s in spans if s.duration_ms > 0)
                result.append({
                    "trace_id": trace_id,
                    "span_count": len(spans),
                    "total_duration_ms": round(total_duration, 2),
                    "root_operation": spans[0].operation if spans else "",
                    "status": "error" if any(s.status == "error" for s in spans) else "ok",
                })
        return result

    def save_trace(self, trace_id: str) -> None:
        if not self._storage_path:
            return
        self._storage_path.mkdir(parents=True, exist_ok=True)
        spans = self._traces.get(trace_id, [])
        fp = self._storage_path / f"{trace_id}.json"
        fp.write_text(
            json.dumps([s.to_dict() for s in spans], indent=2),
            encoding="utf-8",
        )

# Global tracer instance
tracer = Tracer()
