"""Reusable FastAPI dependencies for auth and board/task access.

These dependencies are the main "policy wiring" layer for the API.

They:
- resolve the authenticated actor (human user vs agent)
- enforce organization/board access rules
- provide common "load or 404" helpers (board/task)

Why this exists:
- Keeping authorization logic centralized makes it easier to reason about (and
  audit) permissions as the API surface grows.
- Some routes allow either human users or agents; others require user auth.

If you're adding a new endpoint, prefer composing from these dependencies instead
of re-implementing permission checks in the router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import select

from app.core.agent_auth import get_agent_auth_context_optional
from app.core.auth import AuthContext, get_auth_context, get_auth_context_optional
from app.db.session import get_session
from app.models.boards import Board
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.models.organizations import Organization
from app.models.paper_trading import PaperPortfolio
from app.models.tasks import Task
from app.services.admin_access import require_user_actor
from app.services.organizations import (
    OrganizationContext,
    ensure_member_for_user,
    get_active_membership,
    is_org_admin,
    require_board_access,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.agents import Agent
    from app.models.users import User

AUTH_DEP = Depends(get_auth_context)
SESSION_DEP = Depends(get_session)


def require_user_auth(auth: AuthContext = AUTH_DEP) -> AuthContext:
    """Require an authenticated human user (not an agent)."""
    require_user_actor(auth)
    return auth


@dataclass
class ActorContext:
    """Authenticated actor context for user or agent callers."""

    actor_type: Literal["user", "agent"]
    user: User | None = None
    agent: Agent | None = None


async def require_user_or_agent(
    request: Request,
    session: AsyncSession = SESSION_DEP,
) -> ActorContext:
    """Authorize either a human user or an authenticated agent.

    User auth is resolved first so normal bearer-token user traffic does not
    also trigger agent-token verification on mixed user/agent routes.
    """
    auth = await get_auth_context_optional(
        request=request,
        credentials=None,
        session=session,
    )
    if auth is not None:
        require_user_actor(auth)
        return ActorContext(actor_type="user", user=auth.user)
    agent_auth = await get_agent_auth_context_optional(
        request=request,
        agent_token=request.headers.get("X-Agent-Token"),
        authorization=request.headers.get("Authorization"),
        session=session,
    )
    if agent_auth is not None:
        return ActorContext(actor_type="agent", agent=agent_auth.agent)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


ACTOR_DEP = Depends(require_user_or_agent)


async def require_org_from_actor(
    request: Request,
    session: AsyncSession = SESSION_DEP,
) -> OrganizationContext:
    """Resolve organization context from either a user or an agent caller.

    For users: resolves via org membership (same as require_org_member).
    For agents: resolves via agent -> board -> organization chain.
    """
    actor = await require_user_or_agent(request, session)

    if actor.actor_type == "user" and actor.user is not None:
        member = await get_active_membership(session, actor.user)
        if member is None:
            member = await ensure_member_for_user(session, actor.user)
        if member is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        organization = await Organization.objects.by_id(member.organization_id).first(session)
        if organization is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return OrganizationContext(organization=organization, member=member)

    if actor.actor_type == "agent" and actor.agent is not None:
        if not actor.agent.board_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Agent has no board assignment."
            )
        board = await Board.objects.by_id(actor.agent.board_id).first(session)
        if board is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        organization = await Organization.objects.by_id(board.organization_id).first(session)
        if organization is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        # Create a synthetic member context for the agent (operator-level access)
        from app.models.organization_members import OrganizationMember

        synthetic_member = OrganizationMember(
            organization_id=organization.id,
            user_id=organization.id,  # placeholder — agent doesn't have a user_id
            role="operator",
        )
        return OrganizationContext(organization=organization, member=synthetic_member)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


ORG_ACTOR_DEP = Depends(require_org_from_actor)


async def require_org_member(
    auth: AuthContext = AUTH_DEP,
    session: AsyncSession = SESSION_DEP,
) -> OrganizationContext:
    """Resolve and require active organization membership for the current user."""
    if auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    member = await get_active_membership(session, auth.user)
    if member is None:
        member = await ensure_member_for_user(session, auth.user)
    if member is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    organization = await Organization.objects.by_id(member.organization_id).first(
        session,
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return OrganizationContext(organization=organization, member=member)


ORG_MEMBER_DEP = Depends(require_org_member)


def require_feature(flag: str) -> Callable:
    """Factory that returns a FastAPI dependency enforcing a feature flag.

    Usage: ``router = APIRouter(dependencies=[Depends(require_feature("paper_trading"))])``

    Resolves the caller's organization, loads OrganizationSettings, and raises
    403 if the flag is disabled.  Accepts both user (Bearer) and agent
    (X-Agent-Token) authentication so gateway agents can access
    feature-gated routers.
    """

    async def _check(
        org_ctx: OrganizationContext = ORG_MEMBER_DEP,
        session: AsyncSession = SESSION_DEP,
    ) -> None:
        result = await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == org_ctx.organization.id
            )
        )
        settings = result.scalars().first()
        if settings:
            flags = settings.feature_flags
        else:
            flags = dict(DEFAULT_FEATURE_FLAGS)

        if not flags.get(flag, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{flag}' is not enabled for this organization.",
            )

    return _check


async def check_org_rate_limit(
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> None:
    """Enforce per-org API rate limiting (600 req/min)."""
    from app.core.rate_limit import org_api_limiter

    key = str(org_ctx.organization.id)
    if not await org_api_limiter.is_allowed(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this organization. Try again shortly.",
            headers={"Retry-After": "60"},
        )


ORG_RATE_LIMIT_DEP = Depends(check_org_rate_limit)


async def require_org_admin(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> OrganizationContext:
    """Require organization-admin membership privileges."""
    if not is_org_admin(ctx.member):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return ctx


def require_org_role(minimum_role: str) -> Callable:
    """Factory that returns a FastAPI dependency enforcing a minimum org role.

    Role hierarchy: viewer < member < operator < admin < owner

    Usage: ``Depends(require_org_role("operator"))``
    """
    from app.services.organizations import ROLE_RANK

    min_rank = ROLE_RANK.get(minimum_role, 0)

    async def _check(
        ctx: OrganizationContext = ORG_MEMBER_DEP,
    ) -> OrganizationContext:
        member_rank = ROLE_RANK.get(ctx.member.role, 0)
        if member_rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{minimum_role}' role or higher.",
            )
        return ctx

    return _check


async def get_board_or_404(
    board_id: str,
    session: AsyncSession = SESSION_DEP,
) -> Board:
    """Load a board by id or raise HTTP 404."""
    board = await Board.objects.by_id(board_id).first(session)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return board


async def get_board_for_actor_read(
    board_id: str,
    session: AsyncSession = SESSION_DEP,
    actor: ActorContext = ACTOR_DEP,
) -> Board:
    """Load a board and enforce actor read access."""
    board = await Board.objects.by_id(board_id).first(session)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if actor.actor_type == "agent":
        if actor.agent and actor.agent.board_id and actor.agent.board_id != board.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return board
    if actor.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await require_board_access(session, user=actor.user, board=board, write=False)
    return board


async def get_board_for_actor_write(
    board_id: str,
    session: AsyncSession = SESSION_DEP,
    actor: ActorContext = ACTOR_DEP,
) -> Board:
    """Load a board and enforce actor write access."""
    board = await Board.objects.by_id(board_id).first(session)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if actor.actor_type == "agent":
        if actor.agent and actor.agent.board_id and actor.agent.board_id != board.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return board
    if actor.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await require_board_access(session, user=actor.user, board=board, write=True)
    return board


async def get_board_for_user_read(
    board_id: str,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
) -> Board:
    """Load a board and enforce authenticated-user read access."""
    board = await Board.objects.by_id(board_id).first(session)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await require_board_access(session, user=auth.user, board=board, write=False)
    return board


async def get_board_for_user_write(
    board_id: str,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
) -> Board:
    """Load a board and enforce authenticated-user write access."""
    board = await Board.objects.by_id(board_id).first(session)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await require_board_access(session, user=auth.user, board=board, write=True)
    return board


BOARD_READ_DEP = Depends(get_board_for_actor_read)


async def get_portfolio_for_org(
    portfolio_id: UUID,
    session: AsyncSession = SESSION_DEP,
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> PaperPortfolio:
    """Load a portfolio and verify it belongs to the caller's organization."""
    result = await session.execute(
        select(PaperPortfolio).where(
            PaperPortfolio.id == portfolio_id,
            PaperPortfolio.organization_id == org_ctx.organization.id,
        )
    )
    portfolio = result.scalars().first()
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return portfolio


PORTFOLIO_DEP = Depends(get_portfolio_for_org)


async def get_task_or_404(
    task_id: UUID,
    board: Board = BOARD_READ_DEP,
    session: AsyncSession = SESSION_DEP,
) -> Task:
    """Load a task for a board or raise HTTP 404."""
    task = await Task.objects.by_id(task_id).first(session)
    if task is None or task.board_id != board.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return task
