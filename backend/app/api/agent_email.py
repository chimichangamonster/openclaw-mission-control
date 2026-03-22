"""Agent-scoped email endpoints for triage, reply, and task creation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.agent_auth import AgentAuthContext, get_agent_auth_context
from app.core.logging import get_logger
from app.core.redact import RedactionLevel, redact_email_content
from app.core.sanitize import sanitize_text
from app.core.time import utcnow
from app.db.session import get_session
from app.models.email_accounts import EmailAccount
from app.models.email_messages import EmailMessage
from app.models.tasks import Task
from app.schemas.email import (
    EmailAccountRead,
    EmailMessageDetail,
    EmailMessageRead,
    EmailMessageUpdate,
    EmailReplyCreate,
)
from app.services.email.token_manager import get_valid_access_token

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/agent/email", tags=["agent"])

SESSION_DEP = Depends(get_session)
AGENT_CTX_DEP = Depends(get_agent_auth_context)


def _redact_message(msg: EmailMessage, level: RedactionLevel = RedactionLevel.MODERATE) -> EmailMessage:
    """Apply sanitization + redaction to email content before returning to agents.

    Modifies the ORM object in-place (detached from session) to avoid
    accidental persistence of redacted content.
    """
    msg.body_text = sanitize_text(msg.body_text)
    msg.body_html = sanitize_text(msg.body_html)

    if level != RedactionLevel.OFF:
        text, html, count, categories = redact_email_content(
            msg.body_text, msg.body_html, level=level,
        )
        msg.body_text = text
        msg.body_html = html
        if count > 0:
            logger.info(
                "agent_email.redacted message_id=%s count=%d categories=%s",
                msg.id, count, ",".join(sorted(categories)),
            )
    return msg


async def _get_org_id(agent_ctx: AgentAuthContext) -> UUID:
    """Resolve organization_id from the agent's board."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent has no board.")
    # The agent's board has an organization_id; fetch it via the board.
    from app.models.boards import Board

    # Agent already has board loaded in context — but let's just import and query.
    return agent.board_id  # We'll load org from accounts below.


@router.get("/accounts", response_model=list[EmailAccountRead])
async def agent_list_email_accounts(
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[EmailAccount]:
    """List email accounts available to the agent's organization."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    stmt = (
        select(EmailAccount)
        .where(
            EmailAccount.organization_id == board.organization_id,
            EmailAccount.sync_enabled == True,  # noqa: E712
        )
        .order_by(EmailAccount.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/messages", response_model=list[EmailMessageRead])
async def agent_list_email_messages(
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
    triage_status: str | None = Query(default="pending"),
    folder: str | None = Query(default="inbox"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[EmailMessage]:
    """List email messages accessible to the agent, filtered for triage."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    stmt = (
        select(EmailMessage)
        .where(EmailMessage.organization_id == board.organization_id)
        .order_by(EmailMessage.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if triage_status:
        stmt = stmt.where(EmailMessage.triage_status == triage_status)
    if folder:
        stmt = stmt.where(EmailMessage.folder == folder)

    result = await session.execute(stmt)
    messages = list(result.scalars().all())
    return [_redact_message(m) for m in messages]


@router.get("/messages/{message_id}", response_model=EmailMessageDetail)
async def agent_get_email_message(
    message_id: UUID,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailMessage:
    """Get full email message detail."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.organization_id != board.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _redact_message(msg)


@router.patch("/messages/{message_id}", response_model=EmailMessageRead)
async def agent_update_email_message(
    message_id: UUID,
    payload: EmailMessageUpdate,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailMessage:
    """Triage an email: set status, category, link to task."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.organization_id != board.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    for field in ("is_read", "is_starred", "triage_status", "triage_category", "linked_task_id"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(msg, field, value)

    msg.updated_at = utcnow()
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


@router.post("/messages/{message_id}/reply", status_code=status.HTTP_202_ACCEPTED)
async def agent_reply_to_email(
    message_id: UUID,
    payload: EmailReplyCreate,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, str]:
    """Agent proposes a reply — creates an approval instead of sending directly."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    from app.models.approvals import Approval
    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.organization_id != board.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    account = await session.get(EmailAccount, msg.email_account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Create approval instead of sending directly
    approval = Approval(
        id=uuid4(),
        board_id=board.id,
        agent_id=agent.id,
        action_type="email_reply",
        payload={
            "reason": f"Reply to '{msg.subject}' from {msg.sender_email}",
            "account_id": str(account.id),
            "message_id": str(msg.id),
            "body_text": payload.body_text,
            "to": msg.sender_email,
            "subject": f"Re: {msg.subject or ''}",
            "from_account": account.email_address,
            "original_subject": msg.subject,
            "original_sender": msg.sender_email,
            "original_preview": (msg.body_text or "")[:200],
        },
        confidence=80.0,
        status="pending",
        created_at=utcnow(),
    )
    session.add(approval)
    await session.commit()

    logger.info(
        "email.reply.approval_created",
        extra={
            "approval_id": str(approval.id),
            "to": msg.sender_email,
            "subject": msg.subject,
        },
    )

    return {"status": "pending_approval", "approval_id": str(approval.id)}


@router.post("/messages/{message_id}/archive", status_code=status.HTTP_202_ACCEPTED)
async def agent_archive_email(
    message_id: UUID,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Agent archives an email."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.organization_id != board.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    account = await session.get(EmailAccount, msg.email_account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import move_message

        await move_message(
            access_token,
            account.provider_account_id or "",
            msg.provider_message_id,
            target_folder="archive",
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import move_message

        await move_message(access_token, msg.provider_message_id, target_folder="archive")

    msg.folder = "archive"
    msg.updated_at = utcnow()
    session.add(msg)
    await session.commit()
    return {"ok": True}


@router.post("/messages/{message_id}/create-task", status_code=status.HTTP_201_CREATED)
async def agent_create_task_from_email(
    message_id: UUID,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, str]:
    """Create a board task from an email message."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.organization_id != board.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    now = utcnow()
    description = f"From: {msg.sender_email}\n"
    if msg.body_text:
        description += f"\n{msg.body_text[:2000]}"

    task = Task(
        id=uuid4(),
        board_id=agent.board_id,
        title=msg.subject or "Email task",
        description=description,
        status="inbox",
        priority="medium",
        assigned_agent_id=agent.id,
        auto_created=True,
        auto_reason=f"Created from email {msg.provider_message_id}",
        created_at=now,
        updated_at=now,
    )
    session.add(task)

    msg.linked_task_id = task.id
    msg.triage_status = "actioned"
    msg.updated_at = now
    session.add(msg)

    await session.commit()

    logger.info(
        "email.agent.task_created",
        extra={
            "task_id": str(task.id),
            "message_id": str(msg.id),
            "agent_id": str(agent.id),
        },
    )
    return {"task_id": str(task.id), "ok": "true"}
