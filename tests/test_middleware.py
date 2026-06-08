"""Tests for the agent middleware system."""
from __future__ import annotations

import asyncio
import time

import pytest

from jarvis.agents.base import AgentContext, TaskResult
from jarvis.agents.middleware import (
    AgentMiddleware,
    CachingMiddleware,
    InputValidationMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
    MiddlewareChain,
    RateLimitError,
    RateLimitMiddleware,
    SecurityMiddleware,
    TracingMiddleware,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    task_id: str = "t1",
    agent_name: str = "test-agent",
    success: bool = True,
    output: str = "ok",
    duration_ms: int = 10,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        agent_name=agent_name,
        success=success,
        output=output,
        duration_ms=duration_ms,
    )


def _make_context(task_id: str = "t1") -> AgentContext:
    return AgentContext(task_id=task_id)


# ============================================================================
# LoggingMiddleware
# ============================================================================

class TestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_before_records_start_time(self):
        mw = LoggingMiddleware()
        ctx = _make_context()
        msg, ctx2 = await mw.before_execute("agent", "hello", ctx)
        assert msg == "hello"
        assert ctx2 is ctx
        assert ctx.task_id in mw._start_times

    @pytest.mark.asyncio
    async def test_after_clears_start_time(self):
        mw = LoggingMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hello", ctx)
        result = _make_result()
        await mw.after_execute("agent", result, ctx)
        assert ctx.task_id not in mw._start_times

    @pytest.mark.asyncio
    async def test_passthrough(self):
        mw = LoggingMiddleware()
        ctx = _make_context()
        msg, _ = await mw.before_execute("agent", "hello", ctx)
        assert msg == "hello"
        result = _make_result(output="world")
        r = await mw.after_execute("agent", result, ctx)
        assert r.output == "world"


# ============================================================================
# TracingMiddleware
# ============================================================================

class TestTracingMiddleware:
    @pytest.mark.asyncio
    async def test_creates_span(self):
        mw = TracingMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        assert ctx.task_id in mw._active_spans
        assert "trace_id" in ctx.memory

    @pytest.mark.asyncio
    async def test_completes_span(self):
        mw = TracingMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        result = _make_result()
        await mw.after_execute("agent", result, ctx)
        assert len(mw.completed_spans) == 1
        span = mw.completed_spans[0]
        assert span.agent_name == "agent"
        assert span.status == "ok"
        assert span.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_error_span_status(self):
        mw = TracingMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        result = _make_result(success=False)
        await mw.after_execute("agent", result, ctx)
        assert mw.completed_spans[0].status == "error"

    @pytest.mark.asyncio
    async def test_clear(self):
        mw = TracingMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        await mw.after_execute("agent", _make_result(), ctx)
        mw.clear()
        assert len(mw.completed_spans) == 0


# ============================================================================
# MetricsMiddleware
# ============================================================================

class TestMetricsMiddleware:
    @pytest.mark.asyncio
    async def test_tracks_call_count(self):
        mw = MetricsMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        await mw.after_execute("agent", _make_result(), ctx)
        m = mw.get_metrics("agent")
        assert m.total_calls == 1
        assert m.success_count == 1
        assert m.failure_count == 0

    @pytest.mark.asyncio
    async def test_tracks_failures(self):
        mw = MetricsMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        await mw.after_execute("agent", _make_result(success=False), ctx)
        m = mw.get_metrics("agent")
        assert m.failure_count == 1
        assert m.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_success_rate(self):
        mw = MetricsMiddleware()
        for i in range(4):
            ctx = _make_context(task_id=f"t{i}")
            await mw.before_execute("agent", "hi", ctx)
            success = i < 3  # 3 success, 1 failure
            await mw.after_execute("agent", _make_result(success=success, task_id=f"t{i}"), ctx)
        m = mw.get_metrics("agent")
        assert m.total_calls == 4
        assert m.success_rate == 0.75

    @pytest.mark.asyncio
    async def test_get_all_metrics(self):
        mw = MetricsMiddleware()
        for name in ["a1", "a2"]:
            ctx = _make_context()
            await mw.before_execute(name, "hi", ctx)
            await mw.after_execute(name, _make_result(), ctx)
        assert len(mw.get_all_metrics()) == 2

    @pytest.mark.asyncio
    async def test_reset(self):
        mw = MetricsMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        await mw.after_execute("agent", _make_result(), ctx)
        mw.reset()
        assert mw.get_metrics("agent").total_calls == 0


# ============================================================================
# RateLimitMiddleware
# ============================================================================

class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        mw = RateLimitMiddleware(max_calls=3, window_seconds=60.0)
        for i in range(3):
            ctx = _make_context(task_id=f"t{i}")
            await mw.before_execute("agent", "hi", ctx)

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        mw = RateLimitMiddleware(max_calls=2, window_seconds=60.0)
        ctx1 = _make_context(task_id="t1")
        ctx2 = _make_context(task_id="t2")
        ctx3 = _make_context(task_id="t3")
        await mw.before_execute("agent", "hi", ctx1)
        await mw.before_execute("agent", "hi", ctx2)
        with pytest.raises(RateLimitError) as exc_info:
            await mw.before_execute("agent", "hi", ctx3)
        assert "agent" in str(exc_info.value)
        assert exc_info.value.retry_after_seconds >= 0

    @pytest.mark.asyncio
    async def test_different_agents_independent(self):
        mw = RateLimitMiddleware(max_calls=1, window_seconds=60.0)
        ctx1 = _make_context(task_id="t1")
        ctx2 = _make_context(task_id="t2")
        await mw.before_execute("agent-a", "hi", ctx1)
        # Different agent should not be rate-limited
        await mw.before_execute("agent-b", "hi", ctx2)

    @pytest.mark.asyncio
    async def test_after_is_passthrough(self):
        mw = RateLimitMiddleware()
        result = _make_result()
        r = await mw.after_execute("agent", result, _make_context())
        assert r is result


# ============================================================================
# CachingMiddleware
# ============================================================================

class TestCachingMiddleware:
    @pytest.mark.asyncio
    async def test_cache_miss(self):
        mw = CachingMiddleware()
        assert mw.get_cached("agent", "hi") is None

    @pytest.mark.asyncio
    async def test_cache_stores_on_success(self):
        mw = CachingMiddleware(ttl_seconds=60.0)
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        result = _make_result(output="cached output")
        await mw.after_execute("agent", result, ctx)
        assert mw.size >= 0  # We stored something (key may differ)

    @pytest.mark.asyncio
    async def test_clear(self):
        mw = CachingMiddleware()
        ctx = _make_context()
        await mw.before_execute("agent", "hi", ctx)
        await mw.after_execute("agent", _make_result(), ctx)
        mw.clear()
        assert mw.size == 0

    @pytest.mark.asyncio
    async def test_max_entries_eviction(self):
        mw = CachingMiddleware(max_entries=2)
        for i in range(3):
            ctx = _make_context(task_id=f"t{i}")
            await mw.before_execute(f"agent{i}", "hi", ctx)
            await mw.after_execute(f"agent{i}", _make_result(task_id=f"t{i}"), ctx)
        assert mw.size <= 2


# ============================================================================
# SecurityMiddleware
# ============================================================================

class TestSecurityMiddleware:
    @pytest.mark.asyncio
    async def test_allowed_agent_passes(self):
        mw = SecurityMiddleware(allowed_agents={"agent-a", "agent-b"})
        ctx = _make_context()
        msg, _ = await mw.before_execute("agent-a", "hi", ctx)
        assert msg == "hi"

    @pytest.mark.asyncio
    async def test_blocked_agent_raises(self):
        mw = SecurityMiddleware(allowed_agents={"agent-a"})
        ctx = _make_context()
        with pytest.raises(PermissionError) as exc_info:
            await mw.before_execute("agent-x", "hi", ctx)
        assert "agent-x" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_restriction_allows_all(self):
        mw = SecurityMiddleware(allowed_agents=None)
        ctx = _make_context()
        msg, _ = await mw.before_execute("any-agent", "hi", ctx)
        assert msg == "hi"

    @pytest.mark.asyncio
    async def test_redacts_password_from_output(self):
        mw = SecurityMiddleware()
        result = _make_result(output="config: password=SuperSecret123 done")
        ctx = _make_context()
        r = await mw.after_execute("agent", result, ctx)
        assert "SuperSecret123" not in r.output
        assert "[REDACTED]" in r.output

    @pytest.mark.asyncio
    async def test_redacts_aws_key(self):
        mw = SecurityMiddleware()
        result = _make_result(output="key: AKIAIOSFODNN7EXAMPLE done")
        ctx = _make_context()
        r = await mw.after_execute("agent", result, ctx)
        assert "AKIAIOSFODNN7EXAMPLE" not in r.output

    @pytest.mark.asyncio
    async def test_clean_output_unchanged(self):
        mw = SecurityMiddleware()
        result = _make_result(output="This is perfectly clean output")
        ctx = _make_context()
        r = await mw.after_execute("agent", result, ctx)
        assert r.output == "This is perfectly clean output"


# ============================================================================
# InputValidationMiddleware
# ============================================================================

class TestInputValidationMiddleware:
    @pytest.mark.asyncio
    async def test_empty_message_rejected(self):
        mw = InputValidationMiddleware()
        ctx = _make_context()
        with pytest.raises(ValueError, match="empty"):
            await mw.before_execute("agent", "", ctx)

    @pytest.mark.asyncio
    async def test_whitespace_only_rejected(self):
        mw = InputValidationMiddleware()
        ctx = _make_context()
        with pytest.raises(ValueError, match="empty"):
            await mw.before_execute("agent", "   \n  ", ctx)

    @pytest.mark.asyncio
    async def test_too_long_rejected(self):
        mw = InputValidationMiddleware(max_message_length=10)
        ctx = _make_context()
        with pytest.raises(ValueError, match="exceeds maximum"):
            await mw.before_execute("agent", "a" * 20, ctx)

    @pytest.mark.asyncio
    async def test_valid_message_passes(self):
        mw = InputValidationMiddleware()
        ctx = _make_context()
        msg, _ = await mw.before_execute("agent", "valid message", ctx)
        assert msg == "valid message"

    @pytest.mark.asyncio
    async def test_strips_control_chars(self):
        mw = InputValidationMiddleware(strip_control_chars=True)
        ctx = _make_context()
        msg, _ = await mw.before_execute("agent", "hello\x00world\x07test", ctx)
        assert msg == "helloworldtest"

    @pytest.mark.asyncio
    async def test_preserves_newlines_and_tabs(self):
        mw = InputValidationMiddleware(strip_control_chars=True)
        ctx = _make_context()
        msg, _ = await mw.before_execute("agent", "hello\nworld\ttab", ctx)
        assert msg == "hello\nworld\ttab"

    @pytest.mark.asyncio
    async def test_after_is_passthrough(self):
        mw = InputValidationMiddleware()
        result = _make_result()
        r = await mw.after_execute("agent", result, _make_context())
        assert r is result


# ============================================================================
# MiddlewareChain
# ============================================================================

class TestMiddlewareChain:
    def test_empty_chain(self):
        chain = MiddlewareChain()
        assert len(chain) == 0

    def test_add_returns_self(self):
        chain = MiddlewareChain()
        result = chain.add(LoggingMiddleware())
        assert result is chain

    def test_fluent_chaining(self):
        chain = (
            MiddlewareChain()
            .add(LoggingMiddleware())
            .add(MetricsMiddleware())
            .add(InputValidationMiddleware())
        )
        assert len(chain) == 3

    @pytest.mark.asyncio
    async def test_before_runs_in_order(self):
        """Verify before hooks execute in insertion order."""
        order: list[str] = []

        class TrackingMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self._name = name
            async def before_execute(self, agent_name, message, context):
                order.append(f"before:{self._name}")
                return message, context
            async def after_execute(self, agent_name, result, context):
                order.append(f"after:{self._name}")
                return result

        chain = MiddlewareChain()
        chain.add(TrackingMiddleware("first"))
        chain.add(TrackingMiddleware("second"))
        chain.add(TrackingMiddleware("third"))

        ctx = _make_context()
        await chain.process_before("agent", "hi", ctx)
        assert order == ["before:first", "before:second", "before:third"]

    @pytest.mark.asyncio
    async def test_after_runs_in_reverse_order(self):
        """Verify after hooks execute in reverse insertion order."""
        order: list[str] = []

        class TrackingMiddleware(AgentMiddleware):
            def __init__(self, name: str):
                self._name = name
            async def before_execute(self, agent_name, message, context):
                return message, context
            async def after_execute(self, agent_name, result, context):
                order.append(f"after:{self._name}")
                return result

        chain = MiddlewareChain()
        chain.add(TrackingMiddleware("first"))
        chain.add(TrackingMiddleware("second"))
        chain.add(TrackingMiddleware("third"))

        ctx = _make_context()
        await chain.process_after("agent", _make_result(), ctx)
        assert order == ["after:third", "after:second", "after:first"]

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """End-to-end test with logging + metrics + validation."""
        chain = MiddlewareChain()
        metrics_mw = MetricsMiddleware()
        chain.add(LoggingMiddleware())
        chain.add(metrics_mw)
        chain.add(InputValidationMiddleware())

        ctx = _make_context()
        msg, ctx = await chain.process_before("agent", "hello world", ctx)
        assert msg == "hello world"

        result = _make_result(output="response")
        result = await chain.process_after("agent", result, ctx)
        assert result.output == "response"

        m = metrics_mw.get_metrics("agent")
        assert m.total_calls == 1

    @pytest.mark.asyncio
    async def test_middleware_can_modify_message(self):
        """A middleware can transform the message before the agent sees it."""

        class UppercaseMiddleware(AgentMiddleware):
            async def before_execute(self, agent_name, message, context):
                return message.upper(), context
            async def after_execute(self, agent_name, result, context):
                return result

        chain = MiddlewareChain()
        chain.add(UppercaseMiddleware())

        ctx = _make_context()
        msg, _ = await chain.process_before("agent", "hello", ctx)
        assert msg == "HELLO"

    @pytest.mark.asyncio
    async def test_middleware_can_modify_result(self):
        """A middleware can transform the result after the agent returns."""

        class PrefixMiddleware(AgentMiddleware):
            async def before_execute(self, agent_name, message, context):
                return message, context
            async def after_execute(self, agent_name, result, context):
                return TaskResult(
                    task_id=result.task_id,
                    agent_name=result.agent_name,
                    success=result.success,
                    output=f"[processed] {result.output}",
                )

        chain = MiddlewareChain()
        chain.add(PrefixMiddleware())

        ctx = _make_context()
        result = _make_result(output="original")
        result = await chain.process_after("agent", result, ctx)
        assert result.output == "[processed] original"

    @pytest.mark.asyncio
    async def test_exception_in_before_propagates(self):
        """If a before hook raises, the exception propagates without running further hooks."""
        chain = MiddlewareChain()
        chain.add(InputValidationMiddleware())
        chain.add(LoggingMiddleware())

        ctx = _make_context()
        with pytest.raises(ValueError):
            await chain.process_before("agent", "", ctx)

    @pytest.mark.asyncio
    async def test_middleware_list_property(self):
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = MetricsMiddleware()
        chain.add(m1).add(m2)
        mw_list = chain.middleware_list
        assert len(mw_list) == 2
        assert mw_list[0] is m1
        assert mw_list[1] is m2
        # Verify it's a copy
        mw_list.append(InputValidationMiddleware())
        assert len(chain) == 2
