"""Cron health scan for /api/v1/system/health — gateway RPC path (item 142).

Resolves each org's gateway from the DB and calls the ``cron.list`` RPC,
aggregating counts of cron jobs and their last-run status.

History: this scanner originally walked ``GATEWAY_WORKSPACES_ROOT`` and read
``.openclaw/cron/jobs.json`` off disk. OpenClaw 2026.5.2 chmods ``cron/`` to
0700 and ``jobs.json``/``jobs-state.json`` to 0600 on EVERY cron save
(upstream ``tightenStateDirPermissionsIfNeeded``), so uid-999 mc-backend can
never read them — the disk path is structurally dead, not a perms bug to
chase. The RPC path asks the gateway itself, which owns the files.

GatewayConfig MUST come from ``gateway_resolver`` (the sole
GatewayConfig-from-Gateway constructor) so ``disable_device_pairing`` survives
— a directly-constructed config defaults to device mode and 2026.5.2 silently
rejects every call (listener-green ≠ rpc-green).

Results are cached for a short TTL because ``/system/health`` is
unauthenticated (external monitoring) — without the cache every poll would
fan out WebSocket calls to all gateways.

Disabled jobs (``enabled: False``) are excluded from the failed count: a
disabled job's stale ``lastRunStatus: error`` is operator-acknowledged
history, not a live alert. Without this guard, a once-failed cron that the
operator deliberately disabled keeps ``/system/health`` permanently flagged
as degraded — exactly what happened with ``ecosystem-intel-verify`` on
2026-05-07.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlmodel import select

from app.core.logging import get_logger
from app.models.gateways import Gateway
from app.services.openclaw.gateway_resolver import optional_gateway_client_config
from app.services.openclaw.gateway_rpc import OpenClawGatewayError, openclaw_call

logger = get_logger(__name__)

_FAILURE_STATUSES = ("error", "failed")

_CACHE_TTL_SECONDS = 30.0
_cache: tuple[float, dict[str, Any]] | None = None


def _job_last_status(job: Any) -> str | None:
    """Extract last-run status from a job dict, supporting both modern and legacy shapes."""
    if not isinstance(job, dict):
        return None
    raw_state = job.get("state")
    state: dict[str, Any] = raw_state if isinstance(raw_state, dict) else {}
    last_status = state.get("lastRunStatus")
    if last_status is None:
        last_status = job.get("last_status")
    return last_status if isinstance(last_status, str) else None


def _job_is_enabled(job: Any) -> bool:
    """Return whether the job should count toward the failed total. Missing key → enabled."""
    if not isinstance(job, dict):
        return False
    flag = job.get("enabled", True)
    return bool(flag)


def _unwrap_jobs(rpc_result: Any) -> list[Any]:
    """Unwrap cron.list response — ``{"jobs": [...]}`` dict or bare list."""
    if isinstance(rpc_result, dict) and "jobs" in rpc_result:
        jobs = rpc_result["jobs"]
    elif isinstance(rpc_result, list):
        jobs = rpc_result
    else:
        jobs = []
    return jobs if isinstance(jobs, list) else []


async def _list_jobs_for_gateway(gateway: Gateway) -> list[Any] | None:
    """Call cron.list on one gateway. Returns None when unreachable/unconfigured."""
    config = optional_gateway_client_config(gateway)
    if config is None:
        logger.warning(
            "cron_health.no_config gateway=%s org=%s", gateway.name, gateway.organization_id
        )
        return None
    try:
        result = await openclaw_call(
            "cron.list", None, config=config, org_id=str(gateway.organization_id)
        )
    except OpenClawGatewayError as exc:
        logger.warning(
            "cron_health.rpc_failed gateway=%s org=%s error=%s",
            gateway.name,
            gateway.organization_id,
            exc,
        )
        return None
    return _unwrap_jobs(result)


async def scan_cron_health(cache_ttl: float | None = None) -> dict[str, Any]:
    """Aggregate cron health across all org gateways via the cron.list RPC.

    Args:
        cache_ttl: Seconds a prior result stays fresh. ``None`` uses the
            module default; pass ``0`` to force a live scan (tests).

    Returns:
        A dict with keys ``status`` (``ok`` | ``failing`` | ``no_data``),
        ``failed``, ``total``, ``gateways_scanned``, ``gateways_unreachable``.
    """
    global _cache

    ttl = _CACHE_TTL_SECONDS if cache_ttl is None else cache_ttl
    if _cache is not None and ttl > 0:
        cached_at, cached_result = _cache
        if time.monotonic() - cached_at < ttl:
            return dict(cached_result)

    from app.db.session import async_session_maker

    async with async_session_maker() as session:
        gateways = (await session.execute(select(Gateway))).scalars().all()

    results = await asyncio.gather(*(_list_jobs_for_gateway(gw) for gw in gateways))

    failed = 0
    total = 0
    gateways_scanned = 0
    gateways_unreachable = 0

    for jobs in results:
        if jobs is None:
            gateways_unreachable += 1
            continue
        gateways_scanned += 1
        total += len(jobs)
        for job in jobs:
            if not _job_is_enabled(job):
                continue
            if _job_last_status(job) in _FAILURE_STATUSES:
                failed += 1

    if gateways_scanned == 0:
        result = {
            "status": "no_data",
            "failed": 0,
            "total": 0,
            "gateways_scanned": 0,
            "gateways_unreachable": gateways_unreachable,
        }
    else:
        result = {
            "status": "ok" if failed == 0 else "failing",
            "failed": failed,
            "total": total,
            "gateways_scanned": gateways_scanned,
            "gateways_unreachable": gateways_unreachable,
        }

    _cache = (time.monotonic(), result)
    return dict(result)
