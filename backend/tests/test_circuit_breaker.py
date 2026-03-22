# ruff: noqa: INP001
"""Unit tests for CircuitBreaker and retry_async logic."""

from __future__ import annotations

import time

import pytest

from app.core.resilience import CircuitBreaker


class TestCircuitBreaker:
    """Circuit breaker state machine tests."""

    def test_starts_closed(self) -> None:
        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=1)
        assert cb.state == "closed"
        assert not cb.is_open

    def test_stays_closed_below_threshold(self) -> None:
        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"
        assert not cb.is_open

    def test_opens_at_threshold(self) -> None:
        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        assert cb.is_open

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == "closed"
        # Now 3 more failures needed to open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"

    def test_half_open_after_cooldown(self) -> None:
        cb = CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"

        time.sleep(0.02)
        # Accessing state should transition to half_open after cooldown
        assert cb.state == "half_open"
        assert not cb.is_open  # half_open allows one request

    def test_half_open_success_closes(self) -> None:
        cb = CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)

        # half_open allows request
        assert cb.state == "half_open"
        cb.record_success()
        assert cb.state == "closed"
        assert cb._failure_count == 0

    def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)

        assert cb.state == "half_open"
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"


@pytest.mark.asyncio
async def test_retry_async_succeeds_first_try() -> None:
    from app.core.resilience import retry_async

    call_count = 0

    async def _fn() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_async(_fn, retries=3, base_delay=0.01, label="test")
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_retries_on_failure() -> None:
    from app.core.resilience import retry_async

    call_count = 0

    async def _fn() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "ok"

    result = await retry_async(_fn, retries=3, base_delay=0.01, label="test")
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausts_and_raises() -> None:
    from app.core.resilience import retry_async

    async def _fn() -> str:
        raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        await retry_async(_fn, retries=2, base_delay=0.01, label="test")


@pytest.mark.asyncio
async def test_retry_async_respects_circuit_breaker() -> None:
    from app.core.resilience import retry_async

    cb = CircuitBreaker(name="test", failure_threshold=1, cooldown_seconds=60)
    cb.record_failure()  # opens the breaker

    async def _fn() -> str:
        return "should not reach"

    with pytest.raises(RuntimeError, match="Circuit breaker.*is open"):
        await retry_async(_fn, retries=3, base_delay=0.01, breaker=cb, label="test")


@pytest.mark.asyncio
async def test_retry_async_records_breaker_success() -> None:
    from app.core.resilience import retry_async

    cb = CircuitBreaker(name="test", failure_threshold=5, cooldown_seconds=60)

    async def _fn() -> str:
        return "ok"

    await retry_async(_fn, retries=1, base_delay=0.01, breaker=cb, label="test")
    assert cb._failure_count == 0
    assert cb.state == "closed"
