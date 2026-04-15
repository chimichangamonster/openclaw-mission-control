# ruff: noqa: INP001
"""End-to-end tests for _maybe_autotitle_session.

These tests would have caught the bug shipped in deploy #4 where the titler
respected the sidebar's ``New chat HH:MM:SS`` collision-proof default labels
as if they were user renames, so the titler's "manual label wins" guard
always triggered and auto-titling never fired.

Covers:
- Unlabeled session → auto-title persists
- Session with default ``New chat HH:MM:SS`` label → auto-title overwrites
- Session with user-renamed label → titler respects it, does not overwrite
- Title generator returns None → original label preserved
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.openclaw.gateway_event_listener import _maybe_autotitle_session
from app.services.openclaw.session_service import GatewaySessionService


async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


def _session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_unlabeled_session_receives_title() -> None:
    org_id = uuid4()
    session_key = "org:the-claw:chat-abc"

    engine = await _make_engine()
    maker = _session_maker(engine)

    with (
        patch(
            "app.db.session.async_session_maker",
            maker,
        ),
        patch(
            "app.services.openclaw.session_titler.generate_title",
            new=AsyncMock(return_value="Budget Review"),
        ),
    ):
        await _maybe_autotitle_session(
            str(org_id),
            session_key,
            user_msg="How much did we spend last month?",
            assistant_msg="Your spend was $1,200 across all agents.",
        )

    async with maker() as session:
        service = GatewaySessionService(session)
        labels = await service._get_session_labels(org_id)
    assert labels.get(session_key) == "Budget Review"


@pytest.mark.asyncio
async def test_default_label_gets_overwritten() -> None:
    """The critical bug case: sidebar's `New chat HH:MM:SS` default must be
    overwritten by the titler, not respected as a user rename."""
    org_id = uuid4()
    session_key = "org:the-claw:chat-xyz"

    engine = await _make_engine()
    maker = _session_maker(engine)

    # Seed the DB with a default-pattern label (simulates sidebar create flow)
    async with maker() as session:
        service = GatewaySessionService(session)
        await service._save_session_label(org_id, session_key, "New chat 14:27:31")

    with (
        patch(
            "app.db.session.async_session_maker",
            maker,
        ),
        patch(
            "app.services.openclaw.session_titler.generate_title",
            new=AsyncMock(return_value="Market Update"),
        ),
    ):
        await _maybe_autotitle_session(
            str(org_id),
            session_key,
            user_msg="What's the market doing today?",
            assistant_msg="S&P 500 is up 0.3%.",
        )

    async with maker() as session:
        service = GatewaySessionService(session)
        labels = await service._get_session_labels(org_id)
    assert labels.get(session_key) == "Market Update", (
        "Default `New chat HH:MM:SS` label should be overwritten by titler, "
        "but label is now: " + repr(labels.get(session_key))
    )


@pytest.mark.asyncio
async def test_user_renamed_label_preserved() -> None:
    """User renames must win — titler does not overwrite."""
    org_id = uuid4()
    session_key = "org:the-claw:chat-user"

    engine = await _make_engine()
    maker = _session_maker(engine)

    async with maker() as session:
        service = GatewaySessionService(session)
        await service._save_session_label(org_id, session_key, "My Custom Name")

    with (
        patch(
            "app.db.session.async_session_maker",
            maker,
        ),
        patch(
            "app.services.openclaw.session_titler.generate_title",
            new=AsyncMock(return_value="Auto Generated"),
        ),
    ):
        await _maybe_autotitle_session(
            str(org_id),
            session_key,
            user_msg="hi",
            assistant_msg="hello",
        )

    async with maker() as session:
        service = GatewaySessionService(session)
        labels = await service._get_session_labels(org_id)
    assert labels.get(session_key) == "My Custom Name"


@pytest.mark.asyncio
async def test_title_generation_failure_leaves_label_untouched() -> None:
    """If LLM returns None (error / bad response), original label stays."""
    org_id = uuid4()
    session_key = "org:the-claw:chat-fail"

    engine = await _make_engine()
    maker = _session_maker(engine)

    async with maker() as session:
        service = GatewaySessionService(session)
        await service._save_session_label(org_id, session_key, "New chat 10:00:00")

    with (
        patch(
            "app.db.session.async_session_maker",
            maker,
        ),
        patch(
            "app.services.openclaw.session_titler.generate_title",
            new=AsyncMock(return_value=None),
        ),
    ):
        await _maybe_autotitle_session(
            str(org_id),
            session_key,
            user_msg="hi",
            assistant_msg="hello",
        )

    async with maker() as session:
        service = GatewaySessionService(session)
        labels = await service._get_session_labels(org_id)
    # Default label should still be there (not nulled out).
    assert labels.get(session_key) == "New chat 10:00:00"


@pytest.mark.asyncio
async def test_invalid_org_id_is_noop() -> None:
    """Garbage org_id must not crash — fire-and-forget caller won't see errors."""
    with patch(
        "app.services.openclaw.session_titler.generate_title",
        new=AsyncMock(return_value="Should Not Save"),
    ) as mock_gen:
        await _maybe_autotitle_session(
            "not-a-uuid",
            "org:the-claw:chat-x",
            user_msg="hi",
            assistant_msg="hello",
        )
    mock_gen.assert_not_called()  # Short-circuits on bad UUID before hitting LLM
