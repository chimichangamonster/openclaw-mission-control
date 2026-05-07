"""Infrastructure health checks for /platform/infra-health endpoint (item 123).

Three independent canaries:
- Backup: scan ${BACKUP_DIR} for newest mc_backup_*.sql.gz, report age + size + checksum-pair-present.
- Loki: query ${LOKI_URL}/loki/api/v1/query for last-event timestamp + 24h count.
- ClickHouse: query ${CLICKHOUSE_URL} system.parts for total bytes + per-table top 5 + dominance check.

Each helper is independent — one failing substrate doesn't 500 the others. Failures
return status="error" with the exception message; the endpoint composes them into
one response.

Status values per check: "healthy" | "stale" | "missing" | "error"
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level constants — overridable by tests via monkeypatch
BACKUP_FILENAME_RE = re.compile(r"^mc_backup_\d{4}-\d{2}-\d{2}_\d{4}\.sql\.gz$")
BACKUP_STALE_HOURS = 26  # Daily 03:00 UTC + 2h grace per Grafana alert
LOKI_STALE_MINUTES = 10  # Per Grafana log-ingestion-stopped alert
CH_TOTAL_RED_BYTES = 5 * 1024 * 1024 * 1024  # 5 GiB total system.parts → red
CH_TABLE_RED_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB single table → red
CH_TOTAL_AMBER_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB total → amber
CH_TABLE_AMBER_BYTES = 500 * 1024 * 1024  # 500 MiB single table → amber

# HTTP timeout for external substrates (seconds)
_HTTP_TIMEOUT = 5.0


def check_backup_health(backup_dir: str | None = None) -> dict[str, Any]:
    """Scan backup dir for newest mc_backup_*.sql.gz, classify health.

    Status:
      healthy: newest backup <26h old AND has matching .sha256
      stale:   newest backup ≥26h old (daily cron should fire by 05:00 UTC)
      missing: no backup files at all
      error:   dir unreadable
    """
    path_str = backup_dir or os.environ.get("BACKUP_DIR", "/app/backups")
    path = Path(path_str)

    if not path.exists():
        return {
            "status": "error",
            "message": f"Backup directory not found: {path_str}",
        }

    try:
        sql_files = sorted(
            (f for f in path.iterdir() if BACKUP_FILENAME_RE.match(f.name)),
            key=lambda f: f.name,
            reverse=True,
        )
    except OSError as e:
        return {"status": "error", "message": f"Cannot read backup dir: {e}"}

    if not sql_files:
        return {
            "status": "missing",
            "message": "No backup files found",
            "backup_dir": str(path),
        }

    newest = sql_files[0]
    stat = newest.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    age = datetime.now(UTC) - mtime
    checksum_path = newest.with_suffix("").with_suffix(".sha256")
    has_checksum = checksum_path.exists()

    is_stale = age > timedelta(hours=BACKUP_STALE_HOURS)
    return {
        "status": "stale" if is_stale else "healthy",
        "newest_backup": newest.name,
        "newest_backup_at": mtime.isoformat(),
        "age_hours": round(age.total_seconds() / 3600, 1),
        "size_bytes": stat.st_size,
        "has_checksum": has_checksum,
        "backup_count": len(sql_files),
    }


def check_loki_ingestion(loki_url: str | None = None) -> dict[str, Any]:
    """Query Loki for last-event timestamp + 24h count.

    Uses {service=~".+"} as a catch-all matcher since VC's Promtail labels logs
    with `service` (not the default `job`). If the Loki instance is using a
    different schema, this returns 0 entries — that's an early-warning signal
    in itself.

    Status:
      healthy: last event <10min ago
      stale:   last event ≥10min ago
      error:   Loki unreachable or query failed
    """
    base = (loki_url or os.environ.get("LOKI_URL", "http://loki:3100")).rstrip("/")
    now = datetime.now(UTC)
    start = now - timedelta(hours=24)

    # /loki/api/v1/query_range gives us a count over the window
    count_url = f"{base}/loki/api/v1/query_range"
    count_params = {
        "query": 'sum(count_over_time({service=~".+"}[5m]))',
        "start": str(int(start.timestamp() * 1e9)),
        "end": str(int(now.timestamp() * 1e9)),
        "step": "300",  # 5-min bins
    }

    # /loki/api/v1/query for the latest log line
    last_url = f"{base}/loki/api/v1/query_range"
    last_params = {
        "query": '{service=~".+"}',
        "start": str(int((now - timedelta(hours=1)).timestamp() * 1e9)),
        "end": str(int(now.timestamp() * 1e9)),
        "limit": "1",
        "direction": "backward",
    }

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            count_resp = client.get(count_url, params=count_params)
            count_resp.raise_for_status()
            count_data = count_resp.json()

            last_resp = client.get(last_url, params=last_params)
            last_resp.raise_for_status()
            last_data = last_resp.json()
    except (httpx.HTTPError, ValueError) as e:
        return {"status": "error", "message": f"Loki query failed: {e}"}

    # Sum across bin values: data.result[].values[][1] are stringified counts
    total_count = 0
    for series in count_data.get("data", {}).get("result", []):
        for _ts, val in series.get("values", []):
            try:
                total_count += int(float(val))
            except (TypeError, ValueError):
                pass

    last_event_at = None
    last_age_seconds: float | None = None
    for stream in last_data.get("data", {}).get("result", []):
        for ts_ns, _line in stream.get("values", []):
            try:
                ts = datetime.fromtimestamp(int(ts_ns) / 1e9, tz=UTC)
                last_event_at = ts.isoformat()
                last_age_seconds = (now - ts).total_seconds()
                break
            except (TypeError, ValueError):
                pass
        if last_event_at:
            break

    status = "healthy"
    if last_age_seconds is None:
        status = "stale"  # No events at all in the last hour
    elif last_age_seconds > LOKI_STALE_MINUTES * 60:
        status = "stale"

    return {
        "status": status,
        "last_event_at": last_event_at,
        "last_event_age_seconds": last_age_seconds,
        "events_24h": total_count,
    }


def check_clickhouse_storage(
    clickhouse_url: str | None = None,
    clickhouse_user: str | None = None,
    clickhouse_password: str | None = None,
) -> dict[str, Any]:
    """Query ClickHouse system.parts for total bytes + per-table breakdown.

    Status (whichever is worst wins):
      healthy: total <2 GiB AND no single table >500 MiB
      amber:   total ≥2 GiB OR any table ≥500 MiB
      red:     total ≥5 GiB OR any table ≥1 GiB (replays the 2026-05-07 incident shape)
      error:   CH unreachable or query failed

    The per-table breakdown is the early-warning channel: monthly/unbounded growth
    on any one table will trip the table-level threshold long before total disk
    usage becomes a problem.
    """
    base = (clickhouse_url or os.environ.get("CLICKHOUSE_URL", "http://clickhouse:8123")).rstrip(
        "/"
    )
    user = clickhouse_user or os.environ.get("CLICKHOUSE_USER", "default")
    password = clickhouse_password or os.environ.get("CLICKHOUSE_PASSWORD", "")

    sql = (
        "SELECT database, table, sum(bytes_on_disk) AS bytes, sum(rows) AS rows "
        "FROM system.parts WHERE active "
        "GROUP BY database, table "
        "ORDER BY bytes DESC "
        "LIMIT 20 "
        "FORMAT JSON"
    )

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.post(
                base + "/",
                content=sql.encode(),
                params={"user": user, "password": password},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        return {"status": "error", "message": f"ClickHouse query failed: {e}"}

    rows = data.get("data", [])
    if not rows:
        return {
            "status": "healthy",
            "total_bytes": 0,
            "tables": [],
            "message": "No active parts (fresh CH install or all tables empty)",
        }

    tables = []
    total_bytes = 0
    largest_table_bytes = 0
    for row in rows:
        # ClickHouse returns numeric columns as strings in JSON for UInt64 by default
        try:
            bytes_val = int(row.get("bytes", 0))
            rows_val = int(row.get("rows", 0))
        except (TypeError, ValueError):
            continue
        total_bytes += bytes_val
        largest_table_bytes = max(largest_table_bytes, bytes_val)
        tables.append(
            {
                "database": row.get("database"),
                "table": row.get("table"),
                "bytes": bytes_val,
                "rows": rows_val,
            }
        )

    status = "healthy"
    reason = None
    if total_bytes >= CH_TOTAL_RED_BYTES or largest_table_bytes >= CH_TABLE_RED_BYTES:
        status = "red"
        if largest_table_bytes >= CH_TABLE_RED_BYTES:
            reason = f"Single table ≥{CH_TABLE_RED_BYTES // (1024**3)} GiB"
        else:
            reason = f"Total ≥{CH_TOTAL_RED_BYTES // (1024**3)} GiB"
    elif total_bytes >= CH_TOTAL_AMBER_BYTES or largest_table_bytes >= CH_TABLE_AMBER_BYTES:
        status = "amber"
        if largest_table_bytes >= CH_TABLE_AMBER_BYTES:
            reason = f"Single table ≥{CH_TABLE_AMBER_BYTES // (1024**2)} MiB"
        else:
            reason = f"Total ≥{CH_TOTAL_AMBER_BYTES // (1024**3)} GiB"

    return {
        "status": status,
        "total_bytes": total_bytes,
        "table_count": len(tables),
        "tables": tables[:10],  # Top 10 by size for the UI
        "reason": reason,
    }


def check_infra_health() -> dict[str, Any]:
    """Aggregate all three infrastructure canaries into one response.

    Each substrate runs independently. Overall status is the worst of the three
    (red > amber > stale > healthy). Errors are surfaced but don't poison the
    whole response — useful for partial-outage signal.
    """
    backup = check_backup_health()
    loki = check_loki_ingestion()
    clickhouse = check_clickhouse_storage()

    severity = {
        "healthy": 0,
        "stale": 1,
        "amber": 2,
        "missing": 3,
        "red": 4,
        "error": 5,
    }
    overall_status = max(
        (backup["status"], loki["status"], clickhouse["status"]),
        key=lambda s: severity.get(s, 0),
    )

    return {
        "overall_status": overall_status,
        "backup": backup,
        "loki": loki,
        "clickhouse": clickhouse,
        "checked_at": datetime.now(UTC).isoformat(),
    }
