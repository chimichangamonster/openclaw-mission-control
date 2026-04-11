"""Agent-scoped contact resolution — org members + manual contacts + email-derived."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, or_, select, union_all

from app.core.agent_auth import AgentAuthContext, get_agent_auth_context
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.email_accounts import EmailAccount
from app.models.email_messages import EmailMessage
from app.models.org_contacts import OrgContact
from app.models.organization_members import OrganizationMember
from app.models.users import User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/agent/contacts", tags=["agent"])

SESSION_DEP = Depends(get_session)
AGENT_CTX_DEP = Depends(get_agent_auth_context)


async def _get_org_id(agent_ctx: AgentAuthContext, session: AsyncSession) -> UUID:
    """Resolve organization_id from agent's board."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent has no board.")
    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return board.organization_id


@router.get("/members")
async def agent_list_org_members(
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, str]]:
    """List org members with name and email for scheduling/contact resolution."""
    org_id = await _get_org_id(agent_ctx, session)

    stmt = (
        select(User.email, User.name, User.preferred_name, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == org_id)
        .order_by(User.name)
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "name": row.preferred_name or row.name or "",
            "email": row.email or "",
            "role": row.role,
            "source": "org_member",
        }
        for row in rows
        if row.email  # skip members without email
    ]


@router.get("/search")
async def agent_search_contacts(
    q: str = Query(..., min_length=1, description="Search name or email"),
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict[str, str]]:
    """Unified contact search across org members, manual contacts, and email history.

    Returns deduplicated results sorted by source priority:
    org_member > manual > email_history
    """
    org_id = await _get_org_id(agent_ctx, session)
    search = f"%{q.lower()}%"
    results: dict[str, dict[str, str]] = {}  # keyed by lowercase email

    # 1. Org members
    member_stmt = (
        select(User.email, User.name, User.preferred_name)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(
            OrganizationMember.organization_id == org_id,
            or_(
                func.lower(User.name).like(search),
                func.lower(User.email).like(search),
                func.lower(User.preferred_name).like(search),
            ),
        )
    )
    for row in (await session.execute(member_stmt)).all():
        if row.email:
            key = row.email.lower()
            results[key] = {
                "name": row.preferred_name or row.name or "",
                "email": row.email,
                "company": "",
                "source": "org_member",
            }

    # 2. Manual contacts
    contact_stmt = (
        select(OrgContact)
        .where(
            OrgContact.organization_id == org_id,  # type: ignore[arg-type]
            or_(
                func.lower(OrgContact.name).like(search),
                func.lower(OrgContact.email).like(search),
                func.lower(OrgContact.company).like(search),
            ),
        )
        .limit(limit)
    )
    for contact in (await session.execute(contact_stmt)).scalars().all():
        key = contact.email.lower()
        if key not in results:
            results[key] = {
                "name": contact.name,
                "email": contact.email,
                "company": contact.company,
                "source": "contact",
            }

    # 3. Email history — senders and recipients from shared accounts only
    shared_account_ids = select(EmailAccount.id).where(
        EmailAccount.organization_id == org_id,
        EmailAccount.visibility == "shared",
    )

    # Search senders
    sender_stmt = (
        select(
            distinct(EmailMessage.sender_email),
            EmailMessage.sender_name,
        )
        .where(
            EmailMessage.organization_id == org_id,
            EmailMessage.email_account_id.in_(shared_account_ids),  # type: ignore[attr-defined]
            or_(
                func.lower(EmailMessage.sender_email).like(search),
                func.lower(EmailMessage.sender_name).like(search),
            ),
        )
        .limit(limit)
    )
    for row in (await session.execute(sender_stmt)).all():
        key = row.sender_email.lower()
        if key not in results:
            results[key] = {
                "name": row.sender_name or "",
                "email": row.sender_email,
                "company": "",
                "source": "email_history",
            }

    # Sort: org_member first, then contact, then email_history
    source_order = {"org_member": 0, "contact": 1, "email_history": 2}
    sorted_results = sorted(
        results.values(),
        key=lambda r: (source_order.get(r["source"], 9), r["name"].lower()),
    )

    return sorted_results[:limit]
