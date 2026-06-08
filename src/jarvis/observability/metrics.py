from __future__ import annotations
import time, logging, json
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class Counter:
    name: str
    value: int = 0
    labels: dict[str, str] = field(default_factory=dict)

    def inc(self, amount: int = 1) -> None:
        self.value += amount

@dataclass
class Histogram:
    name: str
    values: list[float] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)

    def observe(self, value: float) -> None:
        self.values.append(value)

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def sum(self) -> float:
        return sum(self.values) if self.values else 0

    @property
    def avg(self) -> float:
        return self.sum / self.count if self.count else 0

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def p99(self) -> float:
        return self._percentile(99)

    def _percentile(self, p: int) -> float:
        if not self.values:
            return 0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * p / 100)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

class Metrics:
    """Application metrics collection.

    Tracks:
    - Request counts (by agent, tool, status)
    - Latency distributions (by operation)
    - Token usage
    - Error rates
    - Active sessions
    """

    def __init__(self):
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}
        self._gauges: dict[str, float] = {}

    def counter(self, name: str, **labels) -> Counter:
        key = f"{name}:{json.dumps(labels, sort_keys=True)}" if labels else name
        if key not in self._counters:
            self._counters[key] = Counter(name=name, labels=labels)
        return self._counters[key]

    def histogram(self, name: str, **labels) -> Histogram:
        key = f"{name}:{json.dumps(labels, sort_keys=True)}" if labels else name
        if key not in self._histograms:
            self._histograms[key] = Histogram(name=name, labels=labels)
        return self._histograms[key]

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def get_gauge(self, name: str) -> float:
        return self._gauges.get(name, 0)

    def snapshot(self) -> dict[str, Any]:
        """Get a snapshot of all metrics."""
        return {
            "counters": {
                k: {"value": c.value, "labels": c.labels}
                for k, c in self._counters.items()
            },
            "histograms": {
                k: {
                    "count": h.count,
                    "sum": round(h.sum, 2),
                    "avg": round(h.avg, 2),
                    "p50": round(h.p50, 2),
                    "p95": round(h.p95, 2),
                    "p99": round(h.p99, 2),
                    "labels": h.labels,
                }
                for k, h in self._histograms.items()
            },
            "gauges": self._gauges,
        }

    def reset(self) -> None:
        self._counters.clear()
        self._histograms.clear()
        self._gauges.clear()

# Global metrics instance
metrics = Metrics()
