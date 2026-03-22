# ruff: noqa: INP001
"""Unit tests for per-org rate limiting."""

from __future__ import annotations

import pytest

from app.core.rate_limit import InMemoryRateLimiter


class TestInMemoryRateLimiter:
    """Sliding window rate limiter tests."""

    @pytest.mark.asyncio
    async def test_allows_under_limit(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert await limiter.is_allowed("org-a") is True

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert await limiter.is_allowed("org-a") is True
        # 4th request should be blocked
        assert await limiter.is_allowed("org-a") is False

    @pytest.mark.asyncio
    async def test_different_orgs_independent(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        assert await limiter.is_allowed("org-a") is True
        assert await limiter.is_allowed("org-a") is True
        assert await limiter.is_allowed("org-a") is False  # org-a exhausted

        # org-b should still be allowed
        assert await limiter.is_allowed("org-b") is True
        assert await limiter.is_allowed("org-b") is True

    @pytest.mark.asyncio
    async def test_window_expires(self) -> None:
        """After window expires, requests should be allowed again."""
        import time

        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=0.05)
        assert await limiter.is_allowed("org-a") is True
        assert await limiter.is_allowed("org-a") is True
        assert await limiter.is_allowed("org-a") is False

        time.sleep(0.06)
        # Window expired, should be allowed
        assert await limiter.is_allowed("org-a") is True

    @pytest.mark.asyncio
    async def test_single_request_allowed(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        assert await limiter.is_allowed("org-a") is True
        assert await limiter.is_allowed("org-a") is False

    @pytest.mark.asyncio
    async def test_high_limit(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=600, window_seconds=60)
        for _ in range(600):
            assert await limiter.is_allowed("org-a") is True
        assert await limiter.is_allowed("org-a") is False
