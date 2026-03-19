"""Post-approval hook for crypto trade execution."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.crypto_trade_proposals import CryptoTradeProposal
from app.services.binance.queue import QueuedCryptoTrade, enqueue_crypto_trade

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.approvals import Approval

logger = get_logger(__name__)


async def handle_crypto_trade_approval_resolution(
    session: AsyncSession,
    approval: Approval,
) -> None:
    """Called when a crypto_trade approval is approved or rejected."""
    payload = approval.payload
    if not isinstance(payload, dict):
        return

    trade_proposal_id_str = payload.get("trade_proposal_id")
    if not trade_proposal_id_str:
        return

    try:
        trade_proposal_id = UUID(trade_proposal_id_str)
    except (ValueError, TypeError):
        return

    proposal = await session.get(CryptoTradeProposal, trade_proposal_id)
    if proposal is None:
        return

    if approval.status == "approved":
        proposal.status = "approved"
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.flush()

        enqueue_crypto_trade(
            QueuedCryptoTrade(
                trade_proposal_id=proposal.id,
                organization_id=proposal.organization_id,
            )
        )
        logger.info("binance.hook.approved", extra={"proposal_id": str(proposal.id)})

    elif approval.status == "rejected":
        proposal.status = "rejected"
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.flush()
        logger.info("binance.hook.rejected", extra={"proposal_id": str(proposal.id)})
