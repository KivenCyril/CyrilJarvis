"""Fallback and timeout utilities for resilient async operations.

Provides a decorator that supplies a fallback value (or function)
when the primary function fails, and a helper that wraps a coroutine
with a timeout.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")


def fallback(
    fallback_func: Callable[..., Any] | None = None,
    default: Any = None,
) -> Callable[[F], F]:
    """Decorator that provides a fallback when the primary function fails.

    If *fallback_func* is given it will be called (with the same arguments)
    when the decorated function raises.  Otherwise *default* is returned.

    Usage::

        @fallback(default={"status": "cached"})
        async def fetch_data():
            ...

        @fallback(fallback_func=fetch_from_cache)
        async def fetch_data():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                logger.warning(
                    "Function %s failed (%s), using fallback", func.__name__, exc
                )
                if fallback_func is not None:
                    result = fallback_func(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        return await result
                    return result
                return default

        return wrapper  # type: ignore[return-value]

    return decorator


async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout_seconds: float,
    default: T | None = None,
) -> T | None:
    """Execute a coroutine with a timeout, returning *default* on timeout.

    Unlike ``asyncio.wait_for`` this helper never raises
    ``asyncio.TimeoutError``; the caller receives the *default* value
    instead.

    Usage::

        result = await with_timeout(fetch_data(), timeout_seconds=5.0)
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning("Operation timed out after %.1fs", timeout_seconds)
        return default
