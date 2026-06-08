"""Token-bucket rate limiter.

Controls the rate of operations to prevent overwhelming external services.
Supports both context-manager and direct ``acquire`` usage.
"""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Token bucket rate limiter.

    Tokens are refilled continuously based on elapsed time.
    Callers acquire a token before making an operation; if no tokens
    are available the caller waits (up to *timeout* seconds) for a
    token to become available.

    Usage::

        limiter = RateLimiter(max_calls=10, period_seconds=1.0)

        async with limiter:
            await do_work()

    Or::

        if await limiter.acquire(timeout=5.0):
            await do_work()
    """

    def __init__(self, max_calls: int, period_seconds: float = 60.0) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")

        self._max_calls = max_calls
        self._period = period_seconds
        self._tokens = float(max_calls)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _refill(self) -> None:
        """Add tokens based on time elapsed since the last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * (self._max_calls / self._period)
        self._tokens = min(self._max_calls, self._tokens + new_tokens)
        self._last_refill = now

    @property
    def available_tokens(self) -> int:
        """Approximate number of tokens currently available."""
        self._refill()
        return int(self._tokens)

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    async def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a token.

        Returns ``True`` if a token was acquired within *timeout* seconds,
        ``False`` otherwise.
        """
        deadline = time.monotonic() + timeout
        poll_interval = min(0.05, self._period / self._max_calls)

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True

            if time.monotonic() >= deadline:
                return False

            await asyncio.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "RateLimiter":
        acquired = await self.acquire()
        if not acquired:
            raise TimeoutError("Rate limiter: could not acquire token in time")
        return self

    async def __aexit__(self, *args: object) -> None:
        pass
