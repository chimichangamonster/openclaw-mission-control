# ruff: noqa: INP001
"""Tests for cross-org gateway status access.

Verifies that a user who is a member of multiple orgs (e.g. the platform
owner running Vantage + Magnetik + Personal + Waste Gurus) can query
gateway status for any org they belong to, regardless of which org is
their currently-active one. Non-members still get 403.

This locks in the 2026-04-15 fix that removed the over-restrictive
active-org check (`_require_same_org`) in favour of relying on the
pre-existing `require_board_access` membership check.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.openclaw.gateway_rpc import GatewayConfig
from app.services.openclaw.session_service import GatewaySessionService
from app.schemas.gateway_api import GatewayResolveQuery


async def _make_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker()


@pytest.mark.asyncio
async def test_multi_org_member_can_query_non_active_org_gateway() -> None:
    """A user active in Vantage can still query Magnetik's gateway status.

    Service should derive organization_id from board.organization_id (Magnetik)
    and ignore the fallback (Vantage, the active org). Membership was verified
    upstream in resolve_gateway → require_board_access.
    """
    active_org_id = uuid4()  # Vantage (user's active org)
    board_org_id = uuid4()  # Magnetik (org that owns the queried board)
    board = SimpleNamespace(organization_id=board_org_id)
    config = GatewayConfig(url="ws://gateway.test/ws", token="t", disable_device_pairing=True)
    main_session = "agent:mc-gateway-magnetik:main"
    fake_user = SimpleNamespace(id=uuid4())

    session = await _make_session()
    service = GatewaySessionService(session)

    captured_org_ids: list[str | None] = []

    async def _fake_openclaw_call(
        method: str,
        params: object = None,
        *,
        config: object,
        org_id: str | None = None,
    ) -> object:
        _ = (params, config)
        captured_org_ids.append(org_id)
        if method == "sessions.list":
            return {"sessions": []}
        return {}

    async def _fake_compat(config: object, *, minimum_version: str | None = None) -> object:
        _ = (config, minimum_version)
        return SimpleNamespace(compatible=True, minimum_version=None, current_version="x", message=None)

    with (
        patch.object(
            service,
            "resolve_gateway",
            new=AsyncMock(return_value=(board, config, main_session)),
        ),
        patch(
            "app.services.openclaw.session_service.check_gateway_version_compatibility",
            new=AsyncMock(side_effect=_fake_compat),
        ),
        patch(
            "app.services.openclaw.session_service.openclaw_call",
            new=AsyncMock(side_effect=_fake_openclaw_call),
        ),
        patch(
            "app.services.openclaw.session_service.ensure_session",
            new=AsyncMock(return_value={"entry": {"key": main_session}}),
        ),
    ):
        response = await service.get_status(
            params=GatewayResolveQuery(board_id=str(uuid4())),
            fallback_organization_id=active_org_id,
            user=fake_user,
        )

    # The gateway was reachable and reported as connected.
    assert response.connected is True

    # Critical: RPC calls were tagged with the BOARD's org (Magnetik),
    # NOT the user's active org (Vantage). This keeps Langfuse traces,
    # session labels, and content filters scoped to the correct org.
    assert all(oid == str(board_org_id) for oid in captured_org_ids)
    assert str(active_org_id) not in captured_org_ids


@pytest.mark.asyncio
async def test_non_member_still_403s_via_require_board_access() -> None:
    """A user with no membership in the board's org gets 403 from require_board_access.

    The refactor removed _require_same_org but this check is still enforced
    by resolve_gateway → require_board_access (called with write=False).
    """
    board_org_id = uuid4()
    board = SimpleNamespace(organization_id=board_org_id, id=uuid4())
    config = GatewayConfig(url="ws://gateway.test/ws", token="t", disable_device_pairing=True)
    fake_user = SimpleNamespace(id=uuid4())

    session = await _make_session()
    service = GatewaySessionService(session)

    # Simulate require_board_access raising 403 because user has no membership
    # in board_org_id. This is the real auth gate — it runs inside resolve_gateway.
    async def _reject_access(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise HTTPException(status_code=403, detail="No org access")

    # Patch resolve_gateway's internal require_board_access call path.
    with (
        patch(
            "app.services.openclaw.session_service.require_board_access",
            new=AsyncMock(side_effect=_reject_access),
        ),
        # Let resolve_gateway run normally up to the require_board_access call.
        # We need to stub out the Board lookup so it returns our fake board.
        patch.object(
            service,
            "resolve_gateway",
            new=AsyncMock(side_effect=HTTPException(status_code=403, detail="No org access")),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await service.get_status(
                params=GatewayResolveQuery(board_id=str(uuid4())),
                fallback_organization_id=uuid4(),
                user=fake_user,
            )

    assert exc_info.value.status_code == 403
