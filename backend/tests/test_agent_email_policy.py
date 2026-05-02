# ruff: noqa: INP001
"""Tests for agent email security invariants shipped 2026-05-02.

Two related guarantees are locked in here:

1. Per-org `data_policy.allow_email_content_to_llm` enforcement — when an org
   sets the flag to false, agent endpoints exposing email content must return
   HTTP 403. Default behaviour (flag absent or true) must be unchanged.

2. Approval-row and task-description redaction — when the agent drafts a reply
   or creates a board task from an email, the original-message preview
   persisted in `Approval.payload["original_preview"]` and the body slice
   persisted in `Task.description` must pass through `redact_email_content`.
   This prevents credentials/financial data from sitting unredacted in DB
   rows that humans (and observability tools) read during review.

Without these tests, removing either the `_enforce_email_to_llm_policy` calls
or the `redact_email_content` calls would silently regress to the prior
state where the controls existed in code review only.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.agent_email import (
    agent_create_task_from_email,
    agent_get_email_message,
    agent_list_email_messages,
    agent_reply_to_email,
)
from app.core.agent_auth import AgentAuthContext
from app.core.time import utcnow
from app.models.agents import Agent
from app.models.approvals import Approval
from app.models.boards import Board
from app.models.email_accounts import EmailAccount
from app.models.email_messages import EmailMessage
from app.models.organization_settings import OrganizationSettings
from app.models.tasks import Task
from app.schemas.email import EmailReplyCreate

ORG_ID = uuid4()
GATEWAY_ID = uuid4()


async def _make_session() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(session: AsyncSession, *, email_to_llm_allowed: bool) -> dict:
    """Seed an org with a board, agent, shared email account, one message, and a
    data policy that either allows or blocks email-to-LLM access."""
    board = Board(
        id=uuid4(),
        organization_id=ORG_ID,
        name="Test Board",
        slug="test-board",
    )
    agent = Agent(
        id=uuid4(),
        board_id=board.id,
        gateway_id=GATEWAY_ID,
        name="test-agent",
        status="ready",
    )
    account = EmailAccount(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=uuid4(),
        provider="microsoft",
        email_address="info@example.com",
        visibility="shared",
        sync_enabled=True,
    )
    msg = EmailMessage(
        id=uuid4(),
        organization_id=ORG_ID,
        email_account_id=account.id,
        provider_message_id="msg-1",
        subject="Test",
        sender_email="client@example.com",
        sender_name="Client",
        body_text="Hello",
        received_at=utcnow(),
        folder="inbox",
        triage_status="pending",
    )
    settings = OrganizationSettings(
        organization_id=ORG_ID,
        data_policy_json=json.dumps(
            {
                "redaction_level": "moderate",
                "allow_email_content_to_llm": email_to_llm_allowed,
                "log_llm_inputs": False,
            }
        ),
    )
    session.add_all([board, agent, account, msg, settings])
    await session.commit()
    return {"board": board, "agent": agent, "account": account, "msg": msg}


def _ctx(agent: Agent) -> AgentAuthContext:
    return AgentAuthContext(actor_type="agent", agent=agent)


@pytest.mark.asyncio
async def test_list_messages_blocked_when_policy_disallows():
    maker = await _make_session()
    async with maker() as session:
        seed = await _seed(session, email_to_llm_allowed=False)
        with pytest.raises(HTTPException) as exc:
            await agent_list_email_messages(agent_ctx=_ctx(seed["agent"]), session=session)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_messages_allowed_when_policy_allows():
    maker = await _make_session()
    async with maker() as session:
        seed = await _seed(session, email_to_llm_allowed=True)
        # Should not raise. Pass explicit Query defaults since we're calling the
        # handler outside FastAPI (no dependency resolution).
        result = await agent_list_email_messages(
            agent_ctx=_ctx(seed["agent"]),
            session=session,
            triage_status="pending",
            folder="inbox",
            limit=50,
            offset=0,
        )
        assert len(result) == 1


@pytest.mark.asyncio
async def test_get_message_blocked_when_policy_disallows():
    maker = await _make_session()
    async with maker() as session:
        seed = await _seed(session, email_to_llm_allowed=False)
        with pytest.raises(HTTPException) as exc:
            await agent_get_email_message(
                message_id=seed["msg"].id,
                agent_ctx=_ctx(seed["agent"]),
                session=session,
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reply_blocked_when_policy_disallows():
    maker = await _make_session()
    async with maker() as session:
        seed = await _seed(session, email_to_llm_allowed=False)
        with pytest.raises(HTTPException) as exc:
            await agent_reply_to_email(
                message_id=seed["msg"].id,
                payload=EmailReplyCreate(body_text="Sure thing."),
                agent_ctx=_ctx(seed["agent"]),
                session=session,
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_task_blocked_when_policy_disallows():
    maker = await _make_session()
    async with maker() as session:
        seed = await _seed(session, email_to_llm_allowed=False)
        with pytest.raises(HTTPException) as exc:
            await agent_create_task_from_email(
                message_id=seed["msg"].id,
                agent_ctx=_ctx(seed["agent"]),
                session=session,
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_default_policy_allows_email_access():
    """Org with no explicit data_policy_json (uses model default) gets access."""
    maker = await _make_session()
    async with maker() as session:
        # Don't override default — model default is allow_email_content_to_llm=true
        board = Board(
            id=uuid4(),
            organization_id=ORG_ID,
            name="Test",
            slug="test",
        )
        agent = Agent(
            id=uuid4(),
            board_id=board.id,
            gateway_id=GATEWAY_ID,
            name="a",
            status="ready",
        )
        settings = OrganizationSettings(organization_id=ORG_ID)
        session.add_all([board, agent, settings])
        await session.commit()

        # Should not raise even with no messages present
        result = await agent_list_email_messages(
            agent_ctx=_ctx(agent),
            session=session,
            triage_status="pending",
            folder="inbox",
            limit=50,
            offset=0,
        )
        assert result == []


@pytest.mark.asyncio
async def test_no_settings_row_defaults_to_allow():
    """Org without any OrganizationSettings row should not be blocked
    (defensive default — settings are auto-created on first access)."""
    maker = await _make_session()
    async with maker() as session:
        board = Board(
            id=uuid4(),
            organization_id=ORG_ID,
            name="Test",
            slug="test",
        )
        agent = Agent(
            id=uuid4(),
            board_id=board.id,
            gateway_id=GATEWAY_ID,
            name="a",
            status="ready",
        )
        session.add_all([board, agent])
        await session.commit()

        result = await agent_list_email_messages(
            agent_ctx=_ctx(agent),
            session=session,
            triage_status="pending",
            folder="inbox",
            limit=50,
            offset=0,
        )
        assert result == []


# ---------------------------------------------------------------------------
# Approval / task-description redaction
# ---------------------------------------------------------------------------

# Body containing a credential pattern that MODERATE-level redaction strips.
SECRET_BODY = (
    "Hi team,\nHere's the staging password: hunter2-secret\n"
    "Let me know when you're in."
)


async def _seed_with_secret_body(session: AsyncSession) -> dict:
    """Same shape as `_seed`, but the message body contains a credential
    that the MODERATE redactor will replace with [REDACTED_PASSWORD]."""
    board = Board(
        id=uuid4(),
        organization_id=ORG_ID,
        name="Test Board",
        slug="test-board",
    )
    agent = Agent(
        id=uuid4(),
        board_id=board.id,
        gateway_id=GATEWAY_ID,
        name="test-agent",
        status="ready",
    )
    account = EmailAccount(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=uuid4(),
        provider="microsoft",
        email_address="info@example.com",
        visibility="shared",
        sync_enabled=True,
    )
    msg = EmailMessage(
        id=uuid4(),
        organization_id=ORG_ID,
        email_account_id=account.id,
        provider_message_id="msg-1",
        subject="Staging access",
        sender_email="ops@example.com",
        body_text=SECRET_BODY,
        received_at=utcnow(),
        folder="inbox",
        triage_status="pending",
    )
    settings = OrganizationSettings(organization_id=ORG_ID)
    session.add_all([board, agent, account, msg, settings])
    await session.commit()
    return {"board": board, "agent": agent, "msg": msg}


@pytest.mark.asyncio
async def test_reply_approval_preview_is_redacted():
    """When the agent drafts a reply, the original-message preview persisted
    on the Approval row must be passed through MODERATE redaction. The raw
    secret must not appear in payload['original_preview']."""
    from sqlmodel import select

    maker = await _make_session()
    async with maker() as session:
        seed = await _seed_with_secret_body(session)
        await agent_reply_to_email(
            message_id=seed["msg"].id,
            payload=EmailReplyCreate(body_text="On it."),
            agent_ctx=_ctx(seed["agent"]),
            session=session,
        )

        approvals = list(
            (await session.execute(select(Approval))).scalars().all()
        )
        assert len(approvals) == 1
        preview = (approvals[0].payload or {}).get("original_preview", "")
        assert isinstance(preview, str)
        assert "hunter2-secret" not in preview
        assert "[REDACTED_PASSWORD]" in preview


@pytest.mark.asyncio
async def test_create_task_description_is_redacted():
    """When the agent converts an email to a board task, the email body
    embedded in Task.description must be redacted before persistence."""
    from sqlmodel import select

    maker = await _make_session()
    async with maker() as session:
        seed = await _seed_with_secret_body(session)
        await agent_create_task_from_email(
            message_id=seed["msg"].id,
            agent_ctx=_ctx(seed["agent"]),
            session=session,
        )

        tasks = list((await session.execute(select(Task))).scalars().all())
        assert len(tasks) == 1
        description = tasks[0].description or ""
        assert "hunter2-secret" not in description
        assert "[REDACTED_PASSWORD]" in description
        # Sanity: the From: header still rendered
        assert "ops@example.com" in description
