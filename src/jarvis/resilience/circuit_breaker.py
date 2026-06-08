"""Circuit breaker pattern for external service calls.

When a service fails repeatedly the circuit *opens* and subsequent
requests are rejected immediately (fail-fast) instead of waiting for
timeouts.  After a recovery timeout the circuit moves to *half-open*
and allows a probe request to test if the service has recovered.
"""

from __future__ import annotations

import functools
import time
from enum import Enum
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(str, Enum):
    """Possible states of a circuit breaker."""

    CLOSED = "closed"       # normal operation
    OPEN = "open"           # failing -- reject requests
    HALF_OPEN = "half_open" # testing if service recovered


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is open."""


class CircuitBreaker:
    """Circuit breaker for protecting calls to unreliable services.

    States:
        - **CLOSED**: normal operation; failures are counted.
        - **OPEN**: failure threshold exceeded; calls are rejected
          with :class:`CircuitOpenError`.
        - **HALF_OPEN**: recovery timeout has elapsed; a limited
          number of probe calls are allowed through.

    Args:
        failure_threshold: consecutive failures before opening.
        recovery_timeout: seconds to wait before moving to HALF_OPEN.
        half_open_max_calls: how many probe calls to allow in HALF_OPEN.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max_calls
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state (may trigger a transition)."""
        self._check_state()
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _check_state(self) -> None:
        """Transition from OPEN -> HALF_OPEN if recovery timeout elapsed."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0

    def _on_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._half_open_max:
                # Service recovered
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
        else:
            self._failure_count = 0
            self._success_count += 1

    def _on_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            # Probe failed -- reopen
            self._state = CircuitState.OPEN
        elif self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the circuit to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute *func* through the circuit breaker.

        Raises :class:`CircuitOpenError` if the circuit is OPEN.
        """
        self._check_state()

        if self._state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit is OPEN ({self._failure_count} failures), rejecting call"
            )

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls > self._half_open_max:
                raise CircuitOpenError(
                    "Circuit is HALF_OPEN and max probe calls reached"
                )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_max_calls: int = 1,
) -> Callable[[F], F]:
    """Decorator that wraps an async function with a circuit breaker.

    Each decorated function gets its own :class:`CircuitBreaker` instance.
    The instance is accessible as ``func.circuit_breaker``.

    Usage::

        @circuit_breaker(failure_threshold=3, recovery_timeout=10.0)
        async def call_api(payload):
            ...
    """

    def decorator(func: F) -> F:
        cb = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
        )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await cb.call(func, *args, **kwargs)

        wrapper.circuit_breaker = cb  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
