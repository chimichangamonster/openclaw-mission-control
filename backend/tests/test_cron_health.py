# ruff: noqa: INP001
"""Unit tests for app.services.cron_health.scan_cron_health (RPC path, item 142).

The scanner resolves every Gateway row from the DB and calls the ``cron.list``
RPC per gateway, aggregating ``failed`` / ``total`` / ``gateways_scanned`` /
``gateways_unreachable``. Disabled jobs are excluded from ``failed`` because a
disabled job's stale ``lastRunStatus: error`` is operator-acknowledged history,
not a live alert.

The pre-142 disk-walk implementation (GATEWAY_WORKSPACES_ROOT/*/jobs.json) was
removed: OpenClaw 2026.5.2 chmods the cron tree unreadable for mc-backend on
every cron save, so the file path is structurally dead.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

import app.services.cron_health as cron_health_module  # noqa: E402
from app.models.gateways import Gateway  # noqa: E402
from app.services.cron_health import scan_cron_health  # noqa: E402
from app.services.openclaw.gateway_rpc import (  # noqa: E402
    OpenClawGatewayError,
    _resolve_connect_mode,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """The module-level TTL cache must not leak between tests."""
    cron_health_module._cache = None
    yield
    cron_health_module._cache = None


@pytest_asyncio.fixture()
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


async def _seed_gateways(engine, *specs: dict[str, Any]):
    """Seed Gateway rows and return a sessionmaker bound to the same engine.

    Each spec may override name/url/disable_device_pairing; defaults are valid.
    """
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        for spec in specs:
            session.add(
                Gateway(
                    organization_id=spec.get("org_id", uuid4()),
                    name=spec.get("name", "gw"),
                    url=spec.get("url", f"ws://openclaw-gateway-{spec.get('name', 'gw')}:18800"),
                    token="gw-token",
                    workspace_root="/ws",
                    disable_device_pairing=spec.get("disable_device_pairing", True),
                )
            )
        await session.commit()
    return maker


def _job(name: str, last_status: str, *, enabled: bool = True) -> dict[str, Any]:
    return {
        "id": name,
        "name": name,
        "enabled": enabled,
        "state": {"lastRunStatus": last_status},
    }


def _fake_cron_list(responses_by_gateway_name: dict[str, Any]):
    """Build an openclaw_call stub keyed by gateway container name in the URL.

    A response value of OpenClawGatewayError (the class) raises it.
    """

    async def fake_call(method, params, *, config, org_id=None, **kwargs):
        assert method == "cron.list"
        for name, response in responses_by_gateway_name.items():
            if name in config.url:
                if response is OpenClawGatewayError:
                    raise OpenClawGatewayError("simulated gateway failure")
                return response
        raise AssertionError(f"no stubbed response for url {config.url}")

    return fake_call


async def _scan(maker, responses: dict[str, Any]) -> dict[str, Any]:
    with (
        patch("app.db.session.async_session_maker", maker),
        patch("app.services.cron_health.openclaw_call", _fake_cron_list(responses)),
    ):
        return await scan_cron_health(cache_ttl=0)


class TestScanCronHealth:
    @pytest.mark.asyncio()
    async def test_no_gateways_returns_no_data(self, db_engine) -> None:
        maker = await _seed_gateways(db_engine)  # zero rows
        result = await _scan(maker, {})
        assert result["status"] == "no_data"
        assert result["failed"] == 0
        assert result["total"] == 0
        assert result["gateways_scanned"] == 0

    @pytest.mark.asyncio()
    async def test_all_ok_returns_status_ok(self, db_engine) -> None:
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        result = await _scan(
            maker, {"vantage": {"jobs": [_job("a", "ok"), _job("b", "ok")]}}
        )
        assert result["status"] == "ok"
        assert result["failed"] == 0
        assert result["total"] == 2
        assert result["gateways_scanned"] == 1
        assert result["gateways_unreachable"] == 0

    @pytest.mark.asyncio()
    async def test_bare_list_response_supported(self, db_engine) -> None:
        """cron.list may return a bare list instead of {"jobs": [...]}."""
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        result = await _scan(maker, {"vantage": [_job("a", "error")]})
        assert result["failed"] == 1
        assert result["total"] == 1

    @pytest.mark.asyncio()
    async def test_enabled_error_counts_as_failed(self, db_engine) -> None:
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        result = await _scan(
            maker, {"vantage": {"jobs": [_job("a", "ok"), _job("bad", "error")]}}
        )
        assert result["status"] == "failing"
        assert result["failed"] == 1
        assert result["total"] == 2

    @pytest.mark.asyncio()
    async def test_disabled_error_does_not_count(self, db_engine) -> None:
        """The bug fix — a disabled job's stale `lastRunStatus: error` must be ignored.

        Replays the 2026-05-07 ecosystem-intel-verify situation: the cron was disabled,
        but its prior error state kept /system/health flagged as degraded forever.
        """
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        result = await _scan(
            maker,
            {
                "vantage": {
                    "jobs": [
                        _job("ok-job", "ok"),
                        _job("disabled-old-error", "error", enabled=False),
                    ]
                }
            },
        )
        assert result["status"] == "ok"
        assert result["failed"] == 0
        assert result["total"] == 2  # total still counts disabled jobs

    @pytest.mark.asyncio()
    async def test_missing_enabled_field_defaults_to_enabled(self, db_engine) -> None:
        """If `enabled` key is missing, treat as enabled (backwards-compat)."""
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        job_no_flag = {"id": "x", "name": "x", "state": {"lastRunStatus": "error"}}
        result = await _scan(maker, {"vantage": {"jobs": [job_no_flag]}})
        assert result["failed"] == 1

    @pytest.mark.asyncio()
    async def test_failed_status_alias_also_counts(self, db_engine) -> None:
        """Some gateway versions write `failed` instead of `error` — both must count."""
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        result = await _scan(maker, {"vantage": {"jobs": [_job("a", "failed")]}})
        assert result["failed"] == 1

    @pytest.mark.asyncio()
    async def test_legacy_last_status_field(self, db_engine) -> None:
        """Old job format used top-level `last_status` instead of `state.lastRunStatus`."""
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        legacy = {"id": "x", "name": "x", "enabled": True, "last_status": "error"}
        result = await _scan(maker, {"vantage": {"jobs": [legacy]}})
        assert result["failed"] == 1

    @pytest.mark.asyncio()
    async def test_legacy_last_status_respects_disabled(self, db_engine) -> None:
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        legacy = {"id": "x", "name": "x", "enabled": False, "last_status": "error"}
        result = await _scan(maker, {"vantage": {"jobs": [legacy]}})
        assert result["failed"] == 0

    @pytest.mark.asyncio()
    async def test_multiple_gateways_aggregate(self, db_engine) -> None:
        maker = await _seed_gateways(
            db_engine, {"name": "vantage"}, {"name": "personal"}, {"name": "magnetik"}
        )
        result = await _scan(
            maker,
            {
                "vantage": {"jobs": [_job("a", "ok"), _job("b", "error")]},
                "personal": {"jobs": [_job("c", "ok"), _job("d", "ok")]},
                "magnetik": {
                    "jobs": [_job("e", "error", enabled=False), _job("f", "error")]
                },
            },
        )
        assert result["gateways_scanned"] == 3
        assert result["total"] == 6
        assert result["failed"] == 2  # b + f, NOT the disabled e
        assert result["status"] == "failing"

    @pytest.mark.asyncio()
    async def test_rpc_error_skips_gateway_others_still_counted(self, db_engine) -> None:
        """One unreachable gateway cannot break the whole scan."""
        maker = await _seed_gateways(db_engine, {"name": "good"}, {"name": "broken"})
        result = await _scan(
            maker,
            {"good": {"jobs": [_job("a", "ok")]}, "broken": OpenClawGatewayError},
        )
        assert result["gateways_scanned"] == 1
        assert result["gateways_unreachable"] == 1
        assert result["total"] == 1
        assert result["failed"] == 0
        assert result["status"] == "ok"

    @pytest.mark.asyncio()
    async def test_all_gateways_unreachable_returns_no_data(self, db_engine) -> None:
        maker = await _seed_gateways(db_engine, {"name": "a"}, {"name": "b"})
        result = await _scan(
            maker, {"a": OpenClawGatewayError, "b": OpenClawGatewayError}
        )
        assert result["status"] == "no_data"
        assert result["gateways_scanned"] == 0
        assert result["gateways_unreachable"] == 2

    @pytest.mark.asyncio()
    async def test_empty_url_gateway_counts_unreachable(self, db_engine) -> None:
        """A Gateway row with no URL is skipped gracefully (optional resolver returns None)."""
        maker = await _seed_gateways(
            db_engine, {"name": "good"}, {"name": "blank", "url": ""}
        )
        result = await _scan(maker, {"good": {"jobs": [_job("a", "ok")]}})
        assert result["gateways_scanned"] == 1
        assert result["gateways_unreachable"] == 1

    @pytest.mark.asyncio()
    async def test_malformed_rpc_result_treated_as_empty(self, db_engine) -> None:
        """A non-dict/non-list response degrades to zero jobs, not a crash."""
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        result = await _scan(maker, {"vantage": "garbage"})
        assert result["gateways_scanned"] == 1
        assert result["total"] == 0
        assert result["status"] == "ok"

    @pytest.mark.asyncio()
    async def test_config_threads_pairing_flag(self, db_engine) -> None:
        """Chokepoint lock (840fb9f) — config must come from gateway_resolver so
        disable_device_pairing survives; on 2026.5.2 this MUST connect control_ui."""
        maker = await _seed_gateways(
            db_engine, {"name": "vantage", "disable_device_pairing": True}
        )
        captured: dict[str, Any] = {}

        async def fake_call(method, params, *, config, org_id=None, **kwargs):
            captured["config"] = config
            return {"jobs": []}

        with (
            patch("app.db.session.async_session_maker", maker),
            patch("app.services.cron_health.openclaw_call", fake_call),
        ):
            await scan_cron_health(cache_ttl=0)

        assert "config" in captured, "RPC was never called — scan short-circuited"
        assert captured["config"].disable_device_pairing is True
        assert _resolve_connect_mode(captured["config"]) == "control_ui"

    @pytest.mark.asyncio()
    async def test_cache_avoids_repeat_rpc(self, db_engine) -> None:
        """/system/health is unauthenticated — the TTL cache must absorb poll storms."""
        maker = await _seed_gateways(db_engine, {"name": "vantage"})
        calls = {"n": 0}

        async def counting_call(method, params, *, config, org_id=None, **kwargs):
            calls["n"] += 1
            return {"jobs": [_job("a", "ok")]}

        with (
            patch("app.db.session.async_session_maker", maker),
            patch("app.services.cron_health.openclaw_call", counting_call),
        ):
            first = await scan_cron_health(cache_ttl=60)
            second = await scan_cron_health(cache_ttl=60)

        assert calls["n"] == 1
        assert first == second
