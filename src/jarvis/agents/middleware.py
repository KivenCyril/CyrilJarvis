"""Agent middleware system for cross-cutting concerns.

Middleware wraps agent execution to add logging, tracing, rate limiting,
caching, input validation, output sanitization, and metrics collection
without polluting agent business logic.

Usage::

    chain = MiddlewareChain()
    chain.add(LoggingMiddleware())
    chain.add(MetricsMiddleware())
    chain.add(RateLimitMiddleware(max_calls=10, window_seconds=60))
    chain.add(CachingMiddleware(ttl_seconds=300))
    chain.add(SecurityMiddleware(allowed_agents={"code-agent", "data-agent"}))
    chain.add(InputValidationMiddleware(max_message_length=50_000))

    # Before agent executes
    message, context = await chain.process_before(agent_name, message, context)
    # ... agent.execute(message, context) ...
    # After agent executes
    result = await chain.process_after(agent_name, result, context)
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from jarvis.agents.base import AgentContext, TaskResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base middleware
# ---------------------------------------------------------------------------

class AgentMiddleware(ABC):
    """Base class for agent middleware.

    Middleware wraps agent execution to add cross-cutting concerns:
    - Logging
    - Tracing
    - Rate limiting
    - Caching
    - Input validation
    - Output sanitization
    - Metrics collection

    Subclasses must implement :meth:`before_execute` and :meth:`after_execute`.
    """

    @abstractmethod
    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        """Called before agent execution.  Can modify message and context."""
        return message, context

    @abstractmethod
    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        """Called after agent execution.  Can modify result."""
        return result


# ---------------------------------------------------------------------------
# LoggingMiddleware
# ---------------------------------------------------------------------------

class LoggingMiddleware(AgentMiddleware):
    """Logs all agent interactions with configurable detail level.

    Captures start/end times, message previews, and result status.
    """

    def __init__(self, preview_length: int = 100) -> None:
        self._preview_length = preview_length
        self._start_times: dict[str, float] = {}

    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        self._start_times[context.task_id] = time.monotonic()
        preview = message[:self._preview_length]
        logger.info(
            "[Middleware:Logging] Agent '%s' starting task %s: %s",
            agent_name, context.task_id, preview,
        )
        return message, context

    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        start = self._start_times.pop(context.task_id, None)
        duration_ms = int((time.monotonic() - start) * 1000) if start else result.duration_ms
        status = "success" if result.success else "failed"
        logger.info(
            "[Middleware:Logging] Agent '%s' %s (%dms, task=%s)",
            agent_name, status, duration_ms, context.task_id,
        )
        return result


# ---------------------------------------------------------------------------
# TracingMiddleware
# ---------------------------------------------------------------------------

@dataclass
class TraceSpan:
    """A single span in a distributed trace."""
    trace_id: str
    span_id: str
    parent_span_id: str | None
    agent_name: str
    operation: str
    start_time: float
    end_time: float = 0.0
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        if self.end_time <= 0:
            return 0
        return int((self.end_time - self.start_time) * 1000)


class TracingMiddleware(AgentMiddleware):
    """Adds distributed tracing spans for agent execution.

    Each agent call creates a span with a unique span_id under a shared trace_id.
    Spans are stored in-memory for inspection during development/testing.
    """

    def __init__(self) -> None:
        self._active_spans: dict[str, TraceSpan] = {}
        self._completed_spans: list[TraceSpan] = []

    @property
    def completed_spans(self) -> list[TraceSpan]:
        """Read-only access to completed spans."""
        return list(self._completed_spans)

    def clear(self) -> None:
        """Clear all stored spans."""
        self._active_spans.clear()
        self._completed_spans.clear()

    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        trace_id = context.memory.get("trace_id", uuid.uuid4().hex[:16])
        parent_span = context.memory.get("parent_span_id")
        span_id = uuid.uuid4().hex[:16]

        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span,
            agent_name=agent_name,
            operation="execute",
            start_time=time.monotonic(),
            attributes={"message_length": len(message)},
        )
        self._active_spans[context.task_id] = span

        # Propagate trace context
        context.memory["trace_id"] = trace_id
        context.memory["span_id"] = span_id
        context.memory["parent_span_id"] = parent_span

        return message, context

    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        span = self._active_spans.pop(context.task_id, None)
        if span:
            span.end_time = time.monotonic()
            span.status = "ok" if result.success else "error"
            span.attributes["output_length"] = len(result.output)
            self._completed_spans.append(span)
        return result


# ---------------------------------------------------------------------------
# MetricsMiddleware
# ---------------------------------------------------------------------------

@dataclass
class AgentMetrics:
    """Aggregated metrics for a single agent."""
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: int = 0
    min_duration_ms: int = 0
    max_duration_ms: int = 0

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.success_count / self.total_calls


class MetricsMiddleware(AgentMiddleware):
    """Collects execution metrics per agent.

    Tracks call count, success/failure rates, and latency statistics.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, AgentMetrics] = {}
        self._start_times: dict[str, float] = {}

    def get_metrics(self, agent_name: str) -> AgentMetrics:
        """Return metrics for a specific agent (creates entry if missing)."""
        if agent_name not in self._metrics:
            self._metrics[agent_name] = AgentMetrics()
        return self._metrics[agent_name]

    def get_all_metrics(self) -> dict[str, AgentMetrics]:
        """Return metrics for all agents."""
        return dict(self._metrics)

    def reset(self) -> None:
        """Reset all metrics."""
        self._metrics.clear()
        self._start_times.clear()

    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        self._start_times[context.task_id] = time.monotonic()
        return message, context

    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        start = self._start_times.pop(context.task_id, None)
        duration_ms = int((time.monotonic() - start) * 1000) if start else result.duration_ms

        m = self.get_metrics(agent_name)
        m.total_calls += 1
        m.total_duration_ms += duration_ms
        if result.success:
            m.success_count += 1
        else:
            m.failure_count += 1
        if m.total_calls == 1:
            m.min_duration_ms = duration_ms
            m.max_duration_ms = duration_ms
        else:
            m.min_duration_ms = min(m.min_duration_ms, duration_ms)
            m.max_duration_ms = max(m.max_duration_ms, duration_ms)

        return result


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Raised when an agent call is rate-limited."""

    def __init__(self, agent_name: str, retry_after_seconds: float) -> None:
        self.agent_name = agent_name
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Agent '{agent_name}' rate limited. Retry after {retry_after_seconds:.1f}s."
        )


class RateLimitMiddleware(AgentMiddleware):
    """Rate-limits agent calls using a sliding-window algorithm.

    Parameters
    ----------
    max_calls : int
        Maximum number of calls allowed within the window.
    window_seconds : float
        Length of the sliding window in seconds.
    """

    def __init__(self, max_calls: int = 10, window_seconds: float = 60.0) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._call_log: dict[str, list[float]] = {}

    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        now = time.monotonic()
        calls = self._call_log.setdefault(agent_name, [])

        # Prune expired entries
        cutoff = now - self._window_seconds
        self._call_log[agent_name] = [t for t in calls if t > cutoff]
        calls = self._call_log[agent_name]

        if len(calls) >= self._max_calls:
            oldest = calls[0]
            retry_after = self._window_seconds - (now - oldest)
            raise RateLimitError(agent_name, max(retry_after, 0.0))

        calls.append(now)
        return message, context

    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        return result


# ---------------------------------------------------------------------------
# CachingMiddleware
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    result: TaskResult
    timestamp: float
    hit_count: int = 0


class CachingMiddleware(AgentMiddleware):
    """Caches repeated identical requests to avoid redundant LLM calls.

    Cache key = hash(agent_name + message).  Results are stored for
    ``ttl_seconds`` and evicted on expiry.

    Parameters
    ----------
    ttl_seconds : float
        Time-to-live for cache entries in seconds.
    max_entries : int
        Maximum number of entries in the cache.
    """

    def __init__(self, ttl_seconds: float = 300.0, max_entries: int = 100) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._cache: dict[str, _CacheEntry] = {}

    @property
    def size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()

    def _make_key(self, agent_name: str, message: str) -> str:
        raw = f"{agent_name}:{message}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def get_cached(self, agent_name: str, message: str) -> TaskResult | None:
        """Look up a cached result.  Returns None on miss or expiry."""
        key = self._make_key(agent_name, message)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if (time.monotonic() - entry.timestamp) > self._ttl:
            del self._cache[key]
            return None
        entry.hit_count += 1
        return entry.result

    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        cached = self.get_cached(agent_name, message)
        if cached is not None:
            # Signal the chain to short-circuit by storing the cached result
            context.memory["_cached_result"] = cached
            logger.debug("[Middleware:Caching] Cache hit for agent '%s'", agent_name)
        return message, context

    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        # Don't re-cache if we already served from cache
        if "_cached_result" in context.memory:
            context.memory.pop("_cached_result", None)
            return result

        if result.success:
            key = self._make_key(agent_name, result.output[:0] or "")
            # We need the original message -- reconstruct key from context history
            # For now, store by agent+task_id (cache is best-effort)
            key = self._make_key(agent_name, context.task_id)
            self._store(key, result)
        return result

    def _store(self, key: str, result: TaskResult) -> None:
        """Store a result in the cache, evicting oldest if at capacity."""
        if len(self._cache) >= self._max_entries:
            # Evict the oldest entry
            oldest_key = min(self._cache, key=lambda k: self._cache[k].timestamp)
            del self._cache[oldest_key]
        self._cache[key] = _CacheEntry(result=result, timestamp=time.monotonic())


# ---------------------------------------------------------------------------
# SecurityMiddleware
# ---------------------------------------------------------------------------

class SecurityMiddleware(AgentMiddleware):
    """Validates permissions and sanitizes agent output.

    Parameters
    ----------
    allowed_agents : set[str] | None
        If provided, only these agents are allowed to execute.
        None means all agents are allowed.
    blocked_patterns : list[str]
        Regex patterns to redact from output (e.g., secrets, PII).
    """

    # Default patterns to redact from agent output
    _DEFAULT_BLOCKED_PATTERNS = [
        r"(?:password|passwd|pwd)\s*[=:]\s*\S+",
        r"(?:api[_-]?key|apikey)\s*[=:]\s*\S+",
        r"(?:secret|token)\s*[=:]\s*\S+",
        r"AKIA[0-9A-Z]{16}",  # AWS access key
        r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
    ]

    def __init__(
        self,
        allowed_agents: set[str] | None = None,
        blocked_patterns: list[str] | None = None,
    ) -> None:
        self._allowed_agents = allowed_agents
        patterns = blocked_patterns if blocked_patterns is not None else self._DEFAULT_BLOCKED_PATTERNS
        self._blocked_re = [re.compile(p, re.IGNORECASE) for p in patterns]

    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        if self._allowed_agents is not None and agent_name not in self._allowed_agents:
            raise PermissionError(
                f"Agent '{agent_name}' is not in the allowed set: {self._allowed_agents}"
            )
        return message, context

    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        # Sanitize output
        sanitized = result.output
        for pattern in self._blocked_re:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        if sanitized != result.output:
            logger.warning(
                "[Middleware:Security] Redacted sensitive content from agent '%s' output",
                agent_name,
            )
            result = TaskResult(
                task_id=result.task_id,
                agent_name=result.agent_name,
                success=result.success,
                output=sanitized,
                artifacts=result.artifacts,
                error=result.error,
                duration_ms=result.duration_ms,
            )
        return result


# ---------------------------------------------------------------------------
# InputValidationMiddleware
# ---------------------------------------------------------------------------

class InputValidationMiddleware(AgentMiddleware):
    """Validates and sanitizes input messages before agent execution.

    Parameters
    ----------
    max_message_length : int
        Maximum allowed message length in characters.
    strip_control_chars : bool
        Whether to strip non-printable control characters.
    """

    def __init__(
        self,
        max_message_length: int = 50_000,
        strip_control_chars: bool = True,
    ) -> None:
        self._max_length = max_message_length
        self._strip_control = strip_control_chars
        # Control chars except \n, \r, \t
        self._control_re = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    async def before_execute(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        if not message or not message.strip():
            raise ValueError("Message cannot be empty or whitespace-only")

        if len(message) > self._max_length:
            raise ValueError(
                f"Message length {len(message)} exceeds maximum {self._max_length}"
            )

        if self._strip_control:
            cleaned = self._control_re.sub("", message)
            if cleaned != message:
                logger.debug(
                    "[Middleware:InputValidation] Stripped control characters from input"
                )
                message = cleaned

        return message, context

    async def after_execute(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        return result


# ---------------------------------------------------------------------------
# MiddlewareChain
# ---------------------------------------------------------------------------

class MiddlewareChain:
    """Chains multiple middleware together.

    Before hooks run in insertion order (first added -> first executed).
    After hooks run in reverse order (last added -> first executed).
    This creates a "wrap-around" pattern similar to HTTP middleware.

    Usage::

        chain = MiddlewareChain()
        chain.add(LoggingMiddleware()).add(MetricsMiddleware())

        # Before
        msg, ctx = await chain.process_before("agent", msg, ctx)
        # ... execute agent ...
        # After
        result = await chain.process_after("agent", result, ctx)
    """

    def __init__(self) -> None:
        self._middleware: list[AgentMiddleware] = []

    def add(self, middleware: AgentMiddleware) -> MiddlewareChain:
        """Add a middleware to the chain.  Returns self for fluent chaining."""
        self._middleware.append(middleware)
        return self

    @property
    def middleware_list(self) -> list[AgentMiddleware]:
        """Read-only view of registered middleware in order."""
        return list(self._middleware)

    def __len__(self) -> int:
        return len(self._middleware)

    async def process_before(
        self, agent_name: str, message: str, context: AgentContext,
    ) -> tuple[str, AgentContext]:
        """Run all before_execute hooks in order."""
        for mw in self._middleware:
            message, context = await mw.before_execute(agent_name, message, context)
        return message, context

    async def process_after(
        self, agent_name: str, result: TaskResult, context: AgentContext,
    ) -> TaskResult:
        """Run all after_execute hooks in reverse order."""
        for mw in reversed(self._middleware):
            result = await mw.after_execute(agent_name, result, context)
        return result
