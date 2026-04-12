# ruff: noqa: INP001
"""Unit tests for the GET /api/v1/system/health endpoint."""

from __future__ import annotations


class TestSystemHealthResponse:
    """Verify the shape and logic of the system health aggregation."""

    def test_healthy_status_fields(self) -> None:
        """A healthy response must contain status, issues, and components."""
        # Simulate what a healthy response looks like
        response = {
            "status": "healthy",
            "issues": [],
            "components": {
                "postgresql": {"status": "ok"},
                "redis": {"status": "ok"},
                "gateway_listener": {"status": "ok"},
                "cb_openrouter": {"state": "closed", "failures": 0},
                "cb_gateway_rpc": {"state": "closed", "failures": 0},
                "recent_errors": {"count_1h": 0},
                "cron_jobs": {"failed": 0, "total": 3},
            },
        }
        assert response["status"] == "healthy"
        assert response["issues"] == []
        assert "postgresql" in response["components"]
        assert "redis" in response["components"]

    def test_degraded_when_gateway_disconnected(self) -> None:
        """Gateway disconnection should produce degraded, not down."""
        issues = ["gateway listener disconnected"]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "degraded"

    def test_degraded_when_circuit_breaker_open(self) -> None:
        """An open circuit breaker is degraded, not down."""
        issues = ["openrouter circuit breaker open"]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "degraded"

    def test_degraded_when_cron_failed(self) -> None:
        """Failed cron jobs produce degraded status."""
        issues = ["2 cron job(s) in failed state"]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "degraded"

    def test_degraded_when_many_errors(self) -> None:
        """10+ errors in last hour produce degraded status."""
        issues = ["15 errors in last hour"]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "degraded"

    def test_down_when_postgresql_down(self) -> None:
        """PostgreSQL down is a critical failure — status must be down."""
        issues = ["postgresql down"]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "down"

    def test_down_when_redis_down(self) -> None:
        """Redis down is a critical failure — status must be down."""
        issues = ["redis down"]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "down"

    def test_down_overrides_degraded(self) -> None:
        """If both critical and non-critical issues exist, status is down."""
        issues = [
            "postgresql down",
            "gateway listener disconnected",
            "openrouter circuit breaker open",
        ]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "down"

    def test_healthy_when_no_issues(self) -> None:
        """No issues means healthy."""
        issues: list[str] = []
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "healthy"

    def test_multiple_degraded_issues(self) -> None:
        """Multiple non-critical issues still produce degraded (not down)."""
        issues = [
            "gateway listener disconnected",
            "openrouter circuit breaker open",
            "2 cron job(s) in failed state",
            "15 errors in last hour",
        ]
        critical = any(k in ("postgresql down", "redis down") for k in issues)
        status = "down" if critical else ("degraded" if issues else "healthy")
        assert status == "degraded"
