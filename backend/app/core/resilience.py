"""Lightweight retry and circuit breaker utilities for external API calls."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class CircuitBreaker:
    """Simple circuit breaker — opens after N consecutive failures, resets after cooldown.

    States:
        CLOSED  — normal operation, requests pass through
        OPEN    — too many failures, requests fail fast without calling the target
        HALF_OPEN — cooldown expired, allow one request to test recovery
    """

    name: str
    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _state: str = field(default="closed", init=False)

    def _should_allow(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if time.time() - self._last_failure_time >= self.cooldown_seconds:
                self._state = "half_open"
                return True
            return False
        # half_open — allow one attempt
        return True

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold and self._state != "open":
            self._state = "open"
            logger.warning(
                "circuit_breaker.opened name=%s failures=%d cooldown=%ss",
                self.name,
                self._failure_count,
                self.cooldown_seconds,
            )
            # Persist circuit breaker trip to activity events (fire-and-forget)
            try:
                import asyncio

                from app.services.error_tracker import track_error

                asyncio.ensure_future(
                    track_error(
                        source="circuit_breaker",
                        message=f"Circuit breaker '{self.name}' opened after {self._failure_count} consecutive failures. Cooldown: {self.cooldown_seconds}s.",
                        severity="warning",
                    )
                )
            except Exception:  # noqa: BLE001
                pass

    @property
    def is_open(self) -> bool:
        return self._state == "open" and not self._should_allow()

    @property
    def state(self) -> str:
        # Re-evaluate in case cooldown expired
        self._should_allow()
        return self._state


# Global circuit breakers for external services
openrouter_breaker = CircuitBreaker(name="openrouter", failure_threshold=5, cooldown_seconds=60)
gateway_rpc_breaker = CircuitBreaker(name="gateway_rpc", failure_threshold=3, cooldown_seconds=30)


async def retry_async(
    fn: Callable[..., Any],
    *args: Any,
    retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    breaker: CircuitBreaker | None = None,
    label: str = "retry",
    **kwargs: Any,
) -> Any:
    """Retry an async function with exponential backoff and optional circuit breaker.

    Returns the function result on success, raises the last exception on exhaustion.
    """
    if breaker and breaker.is_open:
        raise RuntimeError(f"Circuit breaker '{breaker.name}' is open — skipping call")

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            result = await fn(*args, **kwargs)
            if breaker:
                breaker.record_success()
            return result
        except Exception as exc:
            last_exc = exc
            if breaker:
                breaker.record_failure()

            if attempt < retries - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                logger.warning(
                    "%s.attempt_failed attempt=%d/%d delay=%.1fs error=%s",
                    label,
                    attempt + 1,
                    retries,
                    delay,
                    str(exc)[:100],
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "%s.exhausted attempts=%d error=%s",
                    label,
                    retries,
                    str(exc)[:100],
                )

    raise last_exc  # type: ignore[misc]
