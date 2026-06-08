"""Retry decorator with exponential backoff and jitter.

Provides both a dataclass-based configuration object and a simple
decorator for adding retry logic to async functions.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential: bool = True
    jitter: bool = True
    retry_on: tuple[type[Exception], ...] = field(default=(Exception,))


def _compute_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    exponential: bool,
    jitter: bool,
) -> float:
    """Calculate the delay before the next retry attempt."""
    if exponential:
        delay = base_delay * (2 ** attempt)
    else:
        delay = base_delay
    delay = min(delay, max_delay)
    if jitter:
        delay *= 0.5 + random.random()  # [0.5*delay, 1.5*delay)
    return delay


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential: bool = True,
    jitter: bool = True,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator for async functions with retry logic.

    Features:
        - Configurable maximum number of retries
        - Exponential backoff with optional jitter
        - Selective exception filtering via ``retry_on``
        - Logging on each retry attempt

    Usage::

        @retry(max_retries=3, base_delay=0.5, retry_on=(ConnectionError,))
        async def fetch(url: str) -> dict:
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as exc:
                    last_error = exc
                    if attempt < max_retries:
                        delay = _compute_delay(
                            attempt, base_delay, max_delay, exponential, jitter
                        )
                        logger.warning(
                            "Retry %d/%d for %s after %.1fs: %s",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            delay,
                            exc,
                        )
                        await asyncio.sleep(delay)
            # All attempts exhausted
            raise last_error  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def retry_with_config(config: RetryConfig) -> Callable[[F], F]:
    """Create a retry decorator from a RetryConfig object."""
    return retry(
        max_retries=config.max_retries,
        base_delay=config.base_delay,
        max_delay=config.max_delay,
        exponential=config.exponential,
        jitter=config.jitter,
        retry_on=config.retry_on,
    )
