# ruff: noqa: INP001
"""Tests for session label persistence across create + rename paths.

Verifies that labels passed to `create_session` are persisted to
`OrgConfigData` (not just sent to the gateway), so they survive gateway
restarts. Regression test for the create-time persistence gap shipped
as item 34b of the chat reorganization plan.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.openclaw.gateway_rpc import GatewayConfig
from app.services.openclaw.session_service import GatewaySessionService


async def _make_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker()


@pytest.mark.asyncio
async def test_create_session_persists_label_to_org_config() -> None:
    """Labels passed to create_session must be persisted to OrgConfigData.

    Before the fix, only rename_session persisted the label — the create path
    relied entirely on the gateway, which doesn't persist rename metadata.
    """
    org_id = uuid4()
    board = SimpleNamespace(organization_id=org_id)
    config = GatewayConfig(url="ws://gateway.test/ws", token="t", disable_device_pairing=True)
    main_session = "agent:mc-gateway-abc123:main"
    fake_user = SimpleNamespace(id=uuid4())

    session = await _make_session()
    service = GatewaySessionService(session)

    with (
        patch.object(
            service,
            "require_gateway",
            new=AsyncMock(return_value=(board, config, main_session)),
        ),
        patch(
            "app.services.openclaw.session_service.require_board_access",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.openclaw.session_service.ensure_session",
            new=AsyncMock(return_value={"entry": {"key": "stub"}}),
        ),
    ):
        response = await service.create_session(
            label="Property Smart Discovery",
            board_id=str(uuid4()),
            organization_id=org_id,
            user=fake_user,
        )

    assert response.session_key.startswith("agent:mc-gateway-abc123:chat-")
    labels = await service._get_session_labels(org_id)
    assert labels.get(response.session_key) == "Property Smart Discovery"


@pytest.mark.asyncio
async def test_create_session_label_survives_gateway_restart_simulation() -> None:
    """Label persists in MC DB even if gateway forgets it after create."""
    org_id = uuid4()
    board = SimpleNamespace(organization_id=org_id)
    config = GatewayConfig(url="ws://gateway.test/ws", token="t", disable_device_pairing=True)
    main_session = "agent:mc-gateway-xyz:main"
    fake_user = SimpleNamespace(id=uuid4())

    session = await _make_session()
    service = GatewaySessionService(session)

    with (
        patch.object(
            service,
            "require_gateway",
            new=AsyncMock(return_value=(board, config, main_session)),
        ),
        patch(
            "app.services.openclaw.session_service.require_board_access",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.openclaw.session_service.ensure_session",
            new=AsyncMock(return_value={"entry": {"key": "stub"}}),
        ),
    ):
        response = await service.create_session(
            label="Magnetik Q2 Proposal",
            board_id=str(uuid4()),
            organization_id=org_id,
            user=fake_user,
        )

    # Simulate gateway restart by reading labels fresh (no gateway state retained)
    labels = await service._get_session_labels(org_id)
    assert response.session_key in labels
    assert labels[response.session_key] == "Magnetik Q2 Proposal"


@pytest.mark.asyncio
async def test_create_session_isolates_labels_per_org() -> None:
    """Labels created in one org must not appear in another org's label set."""
    org_a = uuid4()
    org_b = uuid4()
    config = GatewayConfig(url="ws://gateway.test/ws", token="t", disable_device_pairing=True)
    main_session = "agent:mc-gateway-shared:main"
    fake_user = SimpleNamespace(id=uuid4())

    session = await _make_session()
    service = GatewaySessionService(session)

    async def _create(org_id, label):
        board = SimpleNamespace(organization_id=org_id)
        with (
            patch.object(
                service,
                "require_gateway",
                new=AsyncMock(return_value=(board, config, main_session)),
            ),
            patch(
                "app.services.openclaw.session_service.require_board_access",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.openclaw.session_service.ensure_session",
                new=AsyncMock(return_value={"entry": {"key": "stub"}}),
            ),
        ):
            return await service.create_session(
                label=label,
                board_id=str(uuid4()),
                organization_id=org_id,
                user=fake_user,
            )

    resp_a = await _create(org_a, "Org A Session")
    resp_b = await _create(org_b, "Org B Session")

    labels_a = await service._get_session_labels(org_a)
    labels_b = await service._get_session_labels(org_b)

    assert labels_a.get(resp_a.session_key) == "Org A Session"
    assert labels_b.get(resp_b.session_key) == "Org B Session"
    assert resp_b.session_key not in labels_a
    assert resp_a.session_key not in labels_b
