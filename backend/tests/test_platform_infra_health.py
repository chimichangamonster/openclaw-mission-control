"""Tests for app.services.infra_health (item 123).

Pure helper tests — no DB, no FastAPI test client. Each substrate is tested in
isolation, then check_infra_health() composition is tested with all three mocked.

Mirrors the test patterns from test_platform_cron_failures.py and test_skill_drift.py:
- tmp_path fixtures for backup-dir filesystem checks
- patched httpx.Client for Loki + ClickHouse HTTP mocks
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx

from app.services import infra_health

# ---------------------------------------------------------------------------
# Backup health
# ---------------------------------------------------------------------------


def test_backup_healthy_with_recent_file_and_checksum(tmp_path: Path) -> None:
    """Newest backup <26h old + has matching .sha256 → healthy."""
    sql = tmp_path / "mc_backup_2026-05-07_0300.sql.gz"
    sql.write_bytes(b"fake gzip data")
    (tmp_path / "mc_backup_2026-05-07_0300.sha256").write_text("deadbeef")

    result = infra_health.check_backup_health(str(tmp_path))

    assert result["status"] == "healthy"
    assert result["newest_backup"] == "mc_backup_2026-05-07_0300.sql.gz"
    assert result["has_checksum"] is True
    assert result["size_bytes"] == len(b"fake gzip data")
    assert result["backup_count"] == 1


def test_backup_stale_when_older_than_26h(tmp_path: Path) -> None:
    """Newest backup ≥26h old → stale."""
    sql = tmp_path / "mc_backup_2026-05-05_0300.sql.gz"
    sql.write_bytes(b"old backup")
    # Set mtime to 30h ago
    old_ts = (datetime.now(UTC) - timedelta(hours=30)).timestamp()
    import os

    os.utime(sql, (old_ts, old_ts))

    result = infra_health.check_backup_health(str(tmp_path))

    assert result["status"] == "stale"
    assert result["age_hours"] >= 26


def test_backup_picks_newest_by_filename_when_multiple(tmp_path: Path) -> None:
    """Sorted-by-filename-desc gives the latest date even if mtimes vary."""
    (tmp_path / "mc_backup_2026-05-05_0300.sql.gz").write_bytes(b"may 5")
    (tmp_path / "mc_backup_2026-05-07_0300.sql.gz").write_bytes(b"may 7")
    (tmp_path / "mc_backup_2026-05-06_0300.sql.gz").write_bytes(b"may 6")

    result = infra_health.check_backup_health(str(tmp_path))

    assert result["newest_backup"] == "mc_backup_2026-05-07_0300.sql.gz"
    assert result["backup_count"] == 3


def test_backup_missing_when_dir_empty(tmp_path: Path) -> None:
    """Empty dir → missing."""
    result = infra_health.check_backup_health(str(tmp_path))
    assert result["status"] == "missing"
    assert "No backup files" in result["message"]


def test_backup_missing_ignores_unrelated_files(tmp_path: Path) -> None:
    """Files that don't match the mc_backup_*.sql.gz pattern are ignored."""
    (tmp_path / "random.txt").write_text("noise")
    (tmp_path / "mc_backup_partial.sql").write_text("wrong suffix")
    (tmp_path / "mc_backup_2026-05-07.sql.gz").write_text("missing time")  # Wrong format

    result = infra_health.check_backup_health(str(tmp_path))
    assert result["status"] == "missing"


def test_backup_error_when_dir_does_not_exist(tmp_path: Path) -> None:
    """Nonexistent path → error."""
    result = infra_health.check_backup_health(str(tmp_path / "does-not-exist"))
    assert result["status"] == "error"
    assert "not found" in result["message"]


def test_backup_no_checksum_still_healthy(tmp_path: Path) -> None:
    """Missing .sha256 doesn't make it stale, but is reported."""
    (tmp_path / "mc_backup_2026-05-07_0300.sql.gz").write_bytes(b"data")
    result = infra_health.check_backup_health(str(tmp_path))
    assert result["status"] == "healthy"
    assert result["has_checksum"] is False


def test_backup_uses_env_var_when_no_arg(monkeypatch, tmp_path: Path) -> None:
    """BACKUP_DIR env var is the default when no argument is passed."""
    (tmp_path / "mc_backup_2026-05-07_0300.sql.gz").write_bytes(b"data")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    result = infra_health.check_backup_health()  # No arg
    assert result["status"] == "healthy"


# ---------------------------------------------------------------------------
# Loki ingestion
# ---------------------------------------------------------------------------


class _FakeHTTPClient:
    """Mimics httpx.Client context manager + .get/.post returning preset responses."""

    def __init__(self, responses: dict[str, dict]) -> None:
        # responses keyed by URL substring
        self._responses = responses

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass

    def get(self, url: str, params: dict | None = None) -> "_FakeResponse":  # noqa: ARG002
        for key, payload in self._responses.items():
            if key in url:
                return _FakeResponse(payload, params=params)
        return _FakeResponse({"status": "success", "data": {"result": []}}, params=params)

    def post(self, url: str, content=None, params=None) -> "_FakeResponse":  # noqa: ARG002
        for key, payload in self._responses.items():
            if key in url:
                return _FakeResponse(payload, params=params)
        return _FakeResponse({"data": []}, params=params)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, params: dict | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self._params = params or {}
        # Stash params so tests can inspect what was queried
        self.requested_params = params

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._payload


def _loki_count_payload(total: int, bins: int = 1) -> dict:
    """Build a Loki query_range response that sums to `total`."""
    per_bin = total // max(bins, 1)
    return {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {},
                    "values": [[str(i * 300), str(per_bin)] for i in range(bins)],
                }
            ]
        },
    }


def _loki_last_event_payload(seconds_ago: float) -> dict:
    """Build a Loki query response with one log line at now-seconds_ago."""
    ts = datetime.now(UTC) - timedelta(seconds=seconds_ago)
    ts_ns = str(int(ts.timestamp() * 1e9))
    return {
        "status": "success",
        "data": {
            "result": [
                {
                    "stream": {"service": "test"},
                    "values": [[ts_ns, "test log line"]],
                }
            ]
        },
    }


def test_loki_healthy_recent_event_with_count() -> None:
    """Last event <10 min ago + 24h count present → healthy."""
    responses = {
        "count_over_time": _loki_count_payload(50_000, bins=288),
    }

    fake_client = _FakeHTTPClient(responses)

    # Loki uses two query_range calls — both hit the same URL substring;
    # we differentiate via the `query` param in the responses dict.
    def _route(url: str, params: dict | None = None) -> _FakeResponse:
        if params and "count_over_time" in params.get("query", ""):
            return _FakeResponse(_loki_count_payload(50_000, bins=288))
        return _FakeResponse(_loki_last_event_payload(seconds_ago=120))

    fake_client.get = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_loki_ingestion("http://loki:3100")

    assert result["status"] == "healthy"
    assert result["events_24h"] >= 1
    assert result["last_event_age_seconds"] is not None
    assert result["last_event_age_seconds"] < 600


def test_loki_stale_when_last_event_old() -> None:
    """Last event >10 min ago → stale even if 24h count is high."""
    fake_client = _FakeHTTPClient({})

    def _route(url: str, params: dict | None = None) -> _FakeResponse:
        if params and "count_over_time" in params.get("query", ""):
            return _FakeResponse(_loki_count_payload(1000, bins=10))
        return _FakeResponse(_loki_last_event_payload(seconds_ago=900))  # 15 min ago

    fake_client.get = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_loki_ingestion("http://loki:3100")

    assert result["status"] == "stale"


def test_loki_stale_when_no_events_in_last_hour() -> None:
    """Empty query result → stale."""
    fake_client = _FakeHTTPClient({})

    def _route(url: str, params: dict | None = None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse({"status": "success", "data": {"result": []}})

    fake_client.get = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_loki_ingestion("http://loki:3100")

    assert result["status"] == "stale"
    assert result["events_24h"] == 0
    assert result["last_event_at"] is None


def test_loki_error_on_http_failure() -> None:
    """HTTP error → status=error with message."""
    fake_client = _FakeHTTPClient({})

    def _route(url: str, params: dict | None = None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse({}, status_code=500)

    fake_client.get = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_loki_ingestion("http://loki:3100")

    assert result["status"] == "error"
    assert "Loki" in result["message"]


# ---------------------------------------------------------------------------
# ClickHouse storage
# ---------------------------------------------------------------------------


def _ch_payload(rows: list[dict]) -> dict:
    """Build a ClickHouse FORMAT JSON response."""
    return {
        "meta": [
            {"name": "database", "type": "String"},
            {"name": "table", "type": "String"},
            {"name": "bytes", "type": "UInt64"},
            {"name": "rows", "type": "UInt64"},
        ],
        "data": rows,
    }


def test_clickhouse_healthy_when_under_thresholds() -> None:
    """Total <2 GiB AND no single table >500 MiB → healthy."""
    rows = [
        {
            "database": "default",
            "table": "observations",
            "bytes": "1048576",
            "rows": "100",
        },
        {"database": "system", "table": "text_log", "bytes": "524288", "rows": "1000"},
    ]
    fake_client = _FakeHTTPClient({"clickhouse": _ch_payload(rows)})

    def _route(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(_ch_payload(rows))

    fake_client.post = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_clickhouse_storage("http://clickhouse:8123")

    assert result["status"] == "healthy"
    assert result["total_bytes"] == 1048576 + 524288
    assert result["table_count"] == 2
    assert result["reason"] is None


def test_clickhouse_amber_when_table_exceeds_500mib() -> None:
    """Single table ≥500 MiB → amber even if total is under 2 GiB."""
    rows = [
        {
            "database": "system",
            "table": "text_log",
            "bytes": str(600 * 1024 * 1024),
            "rows": "10000000",
        },
    ]
    fake_client = _FakeHTTPClient({})

    def _route(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(_ch_payload(rows))

    fake_client.post = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_clickhouse_storage("http://clickhouse:8123")

    assert result["status"] == "amber"
    assert "MiB" in result["reason"]


def test_clickhouse_red_when_single_table_exceeds_1gib() -> None:
    """Single table ≥1 GiB → red. Replays the 2026-05-07 incident shape."""
    rows = [
        {
            "database": "system",
            "table": "text_log",
            "bytes": str(27 * 1024 * 1024 * 1024),  # 27 GiB — the actual incident value
            "rows": "598000000",
        },
    ]
    fake_client = _FakeHTTPClient({})

    def _route(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(_ch_payload(rows))

    fake_client.post = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_clickhouse_storage("http://clickhouse:8123")

    assert result["status"] == "red"
    assert "GiB" in result["reason"]
    assert result["tables"][0]["table"] == "text_log"


def test_clickhouse_red_when_total_exceeds_5gib() -> None:
    """Total ≥5 GiB across many small tables → red even if no single table is huge."""
    rows = [
        {
            "database": "system",
            "table": f"log_{i}",
            "bytes": str(700 * 1024 * 1024),  # Each 700 MiB, 8 tables = 5.5 GiB total
            "rows": "100000",
        }
        for i in range(8)
    ]
    fake_client = _FakeHTTPClient({})

    def _route(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(_ch_payload(rows))

    fake_client.post = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_clickhouse_storage("http://clickhouse:8123")

    assert result["status"] == "red"
    # Either trigger qualifies — single table at 700 MiB is amber-tier, but total at 5.5 GiB is red
    assert "GiB" in result["reason"]


def test_clickhouse_handles_no_active_parts() -> None:
    """Empty CH (fresh install) → healthy with explanatory message."""
    fake_client = _FakeHTTPClient({})

    def _route(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse({"data": []})

    fake_client.post = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_clickhouse_storage("http://clickhouse:8123")

    assert result["status"] == "healthy"
    assert result["total_bytes"] == 0
    assert result["tables"] == []


def test_clickhouse_error_on_unreachable_host() -> None:
    """HTTP failure → status=error."""
    fake_client = _FakeHTTPClient({})

    def _route(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse({}, status_code=500)

    fake_client.post = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_clickhouse_storage("http://clickhouse:8123")

    assert result["status"] == "error"
    assert "ClickHouse" in result["message"]


def test_clickhouse_top_10_truncation() -> None:
    """Response keeps top 10 tables by size — consumer doesn't need 20."""
    rows = [
        {
            "database": "system",
            "table": f"log_{i}",
            "bytes": str((20 - i) * 1024 * 1024),
            "rows": "1000",
        }
        for i in range(20)
    ]
    fake_client = _FakeHTTPClient({})

    def _route(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(_ch_payload(rows))

    fake_client.post = _route  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_clickhouse_storage("http://clickhouse:8123")

    assert len(result["tables"]) == 10
    assert result["table_count"] == 20  # All counted, only top 10 returned


# ---------------------------------------------------------------------------
# check_infra_health composition
# ---------------------------------------------------------------------------


def test_check_infra_health_aggregates_all_three(tmp_path: Path, monkeypatch) -> None:
    """All three substrates run; overall_status = worst of them."""
    (tmp_path / "mc_backup_2026-05-07_0300.sql.gz").write_bytes(b"data")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))

    fake_client = _FakeHTTPClient({})

    def _get(url, params=None) -> _FakeResponse:
        if params and "count_over_time" in params.get("query", ""):
            return _FakeResponse(_loki_count_payload(1000))
        return _FakeResponse(_loki_last_event_payload(seconds_ago=60))

    def _post(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(
            _ch_payload(
                [
                    {
                        "database": "default",
                        "table": "observations",
                        "bytes": "1024",
                        "rows": "10",
                    }
                ]
            )
        )

    fake_client.get = _get  # type: ignore[method-assign]
    fake_client.post = _post  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_infra_health()

    assert result["overall_status"] == "healthy"
    assert result["backup"]["status"] == "healthy"
    assert result["loki"]["status"] == "healthy"
    assert result["clickhouse"]["status"] == "healthy"
    assert "checked_at" in result


def test_check_infra_health_picks_worst_status(tmp_path: Path, monkeypatch) -> None:
    """If CH is red, overall is red even if backup is healthy."""
    (tmp_path / "mc_backup_2026-05-07_0300.sql.gz").write_bytes(b"data")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))

    fake_client = _FakeHTTPClient({})

    def _get(url, params=None) -> _FakeResponse:
        if params and "count_over_time" in params.get("query", ""):
            return _FakeResponse(_loki_count_payload(1000))
        return _FakeResponse(_loki_last_event_payload(seconds_ago=60))

    def _post(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        # 27 GiB on one table — replays the 2026-05-07 incident
        return _FakeResponse(
            _ch_payload(
                [
                    {
                        "database": "system",
                        "table": "text_log",
                        "bytes": str(27 * 1024 * 1024 * 1024),
                        "rows": "598000000",
                    }
                ]
            )
        )

    fake_client.get = _get  # type: ignore[method-assign]
    fake_client.post = _post  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_infra_health()

    assert result["overall_status"] == "red"
    assert result["backup"]["status"] == "healthy"
    assert result["clickhouse"]["status"] == "red"


def test_check_infra_health_one_error_doesnt_poison_others(tmp_path: Path, monkeypatch) -> None:
    """If Loki is down, backup + CH still report their actual status."""
    (tmp_path / "mc_backup_2026-05-07_0300.sql.gz").write_bytes(b"data")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))

    fake_client = _FakeHTTPClient({})

    def _get(url, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse({}, status_code=503)  # Loki unreachable

    def _post(url, content=None, params=None) -> _FakeResponse:  # noqa: ARG001
        return _FakeResponse(
            _ch_payload(
                [
                    {
                        "database": "default",
                        "table": "observations",
                        "bytes": "1024",
                        "rows": "10",
                    }
                ]
            )
        )

    fake_client.get = _get  # type: ignore[method-assign]
    fake_client.post = _post  # type: ignore[method-assign]

    with patch("app.services.infra_health.httpx.Client", return_value=fake_client):
        result = infra_health.check_infra_health()

    assert result["loki"]["status"] == "error"
    assert result["backup"]["status"] == "healthy"
    assert result["clickhouse"]["status"] == "healthy"
    # Overall is "error" because that's the worst severity
    assert result["overall_status"] == "error"
