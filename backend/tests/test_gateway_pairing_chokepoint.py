# ruff: noqa: INP001
"""Regression lock: every gateway-RPC config builder must thread disable_device_pairing.

Root cause (2026-06-08): OpenClaw 2026.5.2 enforces a device-pairing gate on gateway
WS connections. MC's event-listener connects in control_ui mode (Origin header) and is
exempt, but four sites constructed ``GatewayConfig(url=..., token=...)`` directly from a
Gateway DB row, dropping ``disable_device_pairing`` (and ``allow_insecure_tls``). On
2026.5.2 those connections default to device mode -> rejected ("pairing required:
device is not approved yet") -> sessions.list / chat.send / compaction silently fail.

The fix routes all four through ``gateway_resolver``, the sole GatewayConfig-from-Gateway
constructor. These tests assert the per-org pairing flag survives construction and selects
``control_ui`` connect mode — and the negative control proves we derive from the DB record
rather than blanket-forcing control_ui (which would wrongly flip genuine device callers).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from app.models.gateways import Gateway  # noqa: E402
from app.services.openclaw.gateway_rpc import _resolve_connect_mode  # noqa: E402

GATEWAY_URL = "ws://openclaw-gateway-vantage-solutions:18800"


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


async def _seed_gateway(
    engine,
    *,
    org_id,
    disable_device_pairing: bool,
    allow_insecure_tls: bool = False,
):
    """Seed one Gateway row and return a sessionmaker bound to the same engine."""
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(
            Gateway(
                organization_id=org_id,
                name="vantage",
                url=GATEWAY_URL,
                token="gw-token",
                workspace_root="/ws",
                disable_device_pairing=disable_device_pairing,
                allow_insecure_tls=allow_insecure_tls,
            )
        )
        await session.commit()
    return maker


# ---------------------------------------------------------------------------
# budget_monitor — the CONFIRMED live break (every-~5-min background loop,
# hits every org's gateway). sessions.list / compact / reset / send.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_budget_monitor_config_threads_pairing(db_engine):
    from app.services.budget_monitor import _get_gateway_config_for_org

    org_id = uuid4()
    maker = await _seed_gateway(
        db_engine, org_id=org_id, disable_device_pairing=True, allow_insecure_tls=True
    )
    with patch("app.services.budget_monitor.async_session_maker", maker):
        cfg = await _get_gateway_config_for_org(org_id)

    assert cfg is not None
    assert cfg.disable_device_pairing is True
    assert cfg.allow_insecure_tls is True  # latent second bug — also dropped pre-fix
    # Load-bearing: on a 2026.5.2 gateway this MUST connect control_ui, not device.
    assert _resolve_connect_mode(cfg) == "control_ui"


@pytest.mark.asyncio()
async def test_budget_monitor_config_device_when_pairing_required(db_engine):
    # Negative control: a gateway that still REQUIRES pairing must stay device mode,
    # proving the fix derives from the DB record rather than blanket-forcing control_ui.
    from app.services.budget_monitor import _get_gateway_config_for_org

    org_id = uuid4()
    maker = await _seed_gateway(db_engine, org_id=org_id, disable_device_pairing=False)
    with patch("app.services.budget_monitor.async_session_maker", maker):
        cfg = await _get_gateway_config_for_org(org_id)

    assert cfg is not None
    assert cfg.disable_device_pairing is False
    assert _resolve_connect_mode(cfg) == "device"


# ---------------------------------------------------------------------------
# cron_watchdog — stale-cron alert background loop (send/chat.send).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_cron_watchdog_config_threads_pairing(db_engine):
    from app.services.cron_watchdog import _get_first_gateway_config

    org_id = uuid4()
    maker = await _seed_gateway(db_engine, org_id=org_id, disable_device_pairing=True)
    with patch("app.services.cron_watchdog.async_session_maker", maker):
        cfg = await _get_first_gateway_config()

    assert cfg is not None
    assert cfg.disable_device_pairing is True
    assert _resolve_connect_mode(cfg) == "control_ui"


# ---------------------------------------------------------------------------
# cost_tracker /usage-by-model — user-triggered sessions.list. Assert the
# config handed to the RPC layer threads the pairing flag.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_cost_tracker_passes_pairing_config_to_rpc(db_engine):
    from app.api.cost_tracker import get_usage_by_model

    org_id = uuid4()
    maker = await _seed_gateway(db_engine, org_id=org_id, disable_device_pairing=True)
    captured: dict = {}

    async def fake_call(method, *, config, org_id=None, **kwargs):
        captured["config"] = config
        return []

    ctx = SimpleNamespace(organization=SimpleNamespace(id=org_id))
    with (
        patch("app.db.session.async_session_maker", maker),
        patch("app.services.openclaw.gateway_rpc.openclaw_call", fake_call),
    ):
        await get_usage_by_model(org_ctx=ctx)

    assert "config" in captured, "RPC was never called — endpoint short-circuited"
    assert captured["config"].disable_device_pairing is True
    assert _resolve_connect_mode(captured["config"]) == "control_ui"


# ---------------------------------------------------------------------------
# gateway_live feed — user-triggered sessions.list. Same assertion. Note this
# site MUST use optional_gateway_client_config (its guard omits the url-empty
# check), so an empty-url row stays a graceful empty feed, not a 422.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_gateway_live_passes_pairing_config_to_rpc(db_engine):
    from app.api.gateway_live import get_live_feed

    org_id = uuid4()
    maker = await _seed_gateway(db_engine, org_id=org_id, disable_device_pairing=True)
    captured: dict = {}

    async def fake_call(method, *, config, org_id=None, **kwargs):
        captured["config"] = config
        return []

    ctx = SimpleNamespace(organization=SimpleNamespace(id=org_id))
    with (
        patch("app.db.session.async_session_maker", maker),
        patch("app.api.gateway_live.openclaw_call", fake_call),
    ):
        await get_live_feed(ctx=ctx)

    assert "config" in captured, "RPC was never called — endpoint short-circuited"
    assert captured["config"].disable_device_pairing is True
    assert _resolve_connect_mode(captured["config"]) == "control_ui"
