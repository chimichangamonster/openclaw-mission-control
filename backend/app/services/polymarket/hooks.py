"""Post-approval hook for Polymarket trade execution."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.trade_proposals import TradeProposal
from app.services.polymarket.queue import QueuedTradeExecution, enqueue_trade_execution

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.approvals import Approval

logger = get_logger(__name__)


async def handle_trade_approval_resolution(
    session: AsyncSession,
    approval: Approval,
) -> None:
    """Called when a polymarket_trade approval is approved or rejected.

    On approval: updates TradeProposal status and enqueues execution.
    On rejection: updates TradeProposal status to rejected.
    """
    payload = approval.payload
    if not isinstance(payload, dict):
        return

    trade_proposal_id_str = payload.get("trade_proposal_id")
    if not trade_proposal_id_str or not isinstance(trade_proposal_id_str, str):
        return

    try:
        trade_proposal_id = UUID(trade_proposal_id_str)
    except (ValueError, TypeError):
        logger.warning(
            "polymarket.hook.invalid_proposal_id",
            extra={"raw": trade_proposal_id_str},
        )
        return

    proposal = await session.get(TradeProposal, trade_proposal_id)
    if proposal is None:
        logger.warning(
            "polymarket.hook.proposal_missing",
            extra={"trade_proposal_id": trade_proposal_id_str},
        )
        return

    if approval.status == "approved":
        proposal.status = "approved"
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.flush()

        enqueue_trade_execution(
            QueuedTradeExecution(
                trade_proposal_id=proposal.id,
                organization_id=proposal.organization_id,
            )
        )
        logger.info(
            "polymarket.hook.approved_and_enqueued",
            extra={"proposal_id": str(proposal.id)},
        )

    elif approval.status == "rejected":
        proposal.status = "rejected"
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.flush()

        logger.info(
            "polymarket.hook.rejected",
            extra={"proposal_id": str(proposal.id)},
        )
