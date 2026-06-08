"""Tests for the JARVIS error handling / resilience framework.

Covers retry, circuit_breaker, rate_limiter, and fallback modules.
25+ test cases.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from jarvis.resilience.retry import retry, RetryConfig, retry_with_config
from jarvis.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    circuit_breaker,
)
from jarvis.resilience.rate_limiter import RateLimiter
from jarvis.resilience.fallback import fallback, with_timeout


# ======================================================================
# retry tests
# ======================================================================

@pytest.mark.asyncio
async def test_retry_success_first_attempt() -> None:
    call_count = 0

    @retry(max_retries=3, base_delay=0.01)
    async def succeed():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await succeed()
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_eventual_success() -> None:
    call_count = 0

    @retry(max_retries=3, base_delay=0.01, jitter=False)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("fail")
        return "recovered"

    result = await flaky()
    assert result == "recovered"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted() -> None:
    @retry(max_retries=2, base_delay=0.01, jitter=False)
    async def always_fail():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await always_fail()


@pytest.mark.asyncio
async def test_retry_selective_exception() -> None:
    """Only retry on specified exception types."""
    call_count = 0

    @retry(max_retries=3, base_delay=0.01, retry_on=(ConnectionError,))
    async def wrong_error():
        nonlocal call_count
        call_count += 1
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        await wrong_error()
    assert call_count == 1  # no retry for TypeError


@pytest.mark.asyncio
async def test_retry_linear_backoff() -> None:
    call_count = 0

    @retry(max_retries=2, base_delay=0.01, exponential=False, jitter=False)
    async def fail_twice():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("fail")
        return "ok"

    result = await fail_twice()
    assert result == "ok"


@pytest.mark.asyncio
async def test_retry_preserves_function_name() -> None:
    @retry(max_retries=1)
    async def my_func():
        pass

    assert my_func.__name__ == "my_func"


@pytest.mark.asyncio
async def test_retry_config_object() -> None:
    cfg = RetryConfig(max_retries=1, base_delay=0.01, jitter=False)
    call_count = 0

    @retry_with_config(cfg)
    async def func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("fail")
        return "ok"

    assert await func() == "ok"
    assert call_count == 2


# ======================================================================
# circuit_breaker tests
# ======================================================================

@pytest.mark.asyncio
async def test_cb_stays_closed_on_success() -> None:
    cb = CircuitBreaker(failure_threshold=3)

    async def ok():
        return "ok"

    result = await cb.call(ok)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_cb_opens_after_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=100)

    async def fail():
        raise RuntimeError("err")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(fail)

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_cb_rejects_when_open() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=100)

    async def fail():
        raise RuntimeError("err")

    with pytest.raises(RuntimeError):
        await cb.call(fail)

    with pytest.raises(CircuitOpenError):
        await cb.call(fail)


@pytest.mark.asyncio
async def test_cb_half_open_after_timeout() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

    async def fail():
        raise RuntimeError("err")

    with pytest.raises(RuntimeError):
        await cb.call(fail)

    assert cb.state == CircuitState.OPEN
    await asyncio.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_cb_recovers_from_half_open() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, half_open_max_calls=1)

    async def fail():
        raise RuntimeError("err")

    async def succeed():
        return "ok"

    with pytest.raises(RuntimeError):
        await cb.call(fail)

    await asyncio.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN

    result = await cb.call(succeed)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_cb_half_open_failure_reopens() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

    async def fail():
        raise RuntimeError("err")

    with pytest.raises(RuntimeError):
        await cb.call(fail)

    await asyncio.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN

    with pytest.raises(RuntimeError):
        await cb.call(fail)

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_cb_manual_reset() -> None:
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=100)

    async def fail():
        raise RuntimeError("err")

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_cb_decorator() -> None:
    call_count = 0

    @circuit_breaker(failure_threshold=2, recovery_timeout=100)
    async def service():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await service()

    with pytest.raises(CircuitOpenError):
        await service()

    assert service.circuit_breaker.state == CircuitState.OPEN


# ======================================================================
# rate_limiter tests
# ======================================================================

@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit() -> None:
    limiter = RateLimiter(max_calls=5, period_seconds=1.0)
    for _ in range(5):
        assert await limiter.acquire(timeout=1.0) is True


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_limit() -> None:
    limiter = RateLimiter(max_calls=2, period_seconds=10.0)
    assert await limiter.acquire(timeout=0.5) is True
    assert await limiter.acquire(timeout=0.5) is True
    # Third call should timeout quickly
    assert await limiter.acquire(timeout=0.1) is False


@pytest.mark.asyncio
async def test_rate_limiter_refills() -> None:
    limiter = RateLimiter(max_calls=2, period_seconds=0.2)
    assert await limiter.acquire(timeout=0.5) is True
    assert await limiter.acquire(timeout=0.5) is True
    # Wait for refill
    await asyncio.sleep(0.25)
    assert await limiter.acquire(timeout=0.5) is True


@pytest.mark.asyncio
async def test_rate_limiter_context_manager() -> None:
    limiter = RateLimiter(max_calls=3, period_seconds=1.0)
    async with limiter:
        pass  # token consumed


@pytest.mark.asyncio
async def test_rate_limiter_available_tokens() -> None:
    limiter = RateLimiter(max_calls=10, period_seconds=60.0)
    assert limiter.available_tokens == 10
    await limiter.acquire()
    assert limiter.available_tokens == 9


def test_rate_limiter_invalid_params() -> None:
    with pytest.raises(ValueError):
        RateLimiter(max_calls=0)
    with pytest.raises(ValueError):
        RateLimiter(max_calls=1, period_seconds=0)


# ======================================================================
# fallback tests
# ======================================================================

@pytest.mark.asyncio
async def test_fallback_default_value() -> None:
    @fallback(default={"cached": True})
    async def fail_func():
        raise RuntimeError("down")

    result = await fail_func()
    assert result == {"cached": True}


@pytest.mark.asyncio
async def test_fallback_no_failure() -> None:
    @fallback(default="backup")
    async def ok_func():
        return "primary"

    assert await ok_func() == "primary"


@pytest.mark.asyncio
async def test_fallback_with_func() -> None:
    async def backup(x: int) -> int:
        return x * 10

    @fallback(fallback_func=backup)
    async def primary(x: int) -> int:
        raise RuntimeError("fail")

    result = await primary(5)
    assert result == 50


@pytest.mark.asyncio
async def test_fallback_with_sync_func() -> None:
    def sync_backup() -> str:
        return "sync_fallback"

    @fallback(fallback_func=sync_backup)
    async def primary() -> str:
        raise RuntimeError("fail")

    assert await primary() == "sync_fallback"


# ======================================================================
# with_timeout tests
# ======================================================================

@pytest.mark.asyncio
async def test_with_timeout_completes() -> None:
    async def fast():
        return 42

    result = await with_timeout(fast(), timeout_seconds=1.0)
    assert result == 42


@pytest.mark.asyncio
async def test_with_timeout_expires() -> None:
    async def slow():
        await asyncio.sleep(10)
        return "never"

    result = await with_timeout(slow(), timeout_seconds=0.05, default="timed_out")
    assert result == "timed_out"


@pytest.mark.asyncio
async def test_with_timeout_default_none() -> None:
    async def slow():
        await asyncio.sleep(10)

    result = await with_timeout(slow(), timeout_seconds=0.05)
    assert result is None
