"""Trade proposal creation with risk validation and post-approval execution."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.approvals import Approval
from app.models.polymarket_risk_config import PolymarketRiskConfig
from app.models.polymarket_wallets import PolymarketWallet
from app.models.trade_history import TradeHistory
from app.models.trade_proposals import TradeProposal
from app.schemas.polymarket import TradeProposalCreate
from app.services.polymarket.credentials import get_clob_client
from app.services.polymarket.markets import get_market_detail

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)


def validate_risk_controls(
    risk_config: PolymarketRiskConfig | None,
    size_usdc: float,
    condition_id: str,
) -> list[str]:
    """Validate trade against risk controls. Returns list of violations (empty = ok)."""
    violations: list[str] = []
    if risk_config is None:
        return violations  # no config = no restrictions (except approval gate)

    if size_usdc > risk_config.max_trade_size_usdc:
        violations.append(
            f"Trade size ${size_usdc:.2f} exceeds max ${risk_config.max_trade_size_usdc:.2f}"
        )

    if risk_config.market_blacklist and condition_id in risk_config.market_blacklist:
        violations.append(f"Market {condition_id} is blacklisted")

    if risk_config.market_whitelist and condition_id not in risk_config.market_whitelist:
        violations.append(f"Market {condition_id} is not in whitelist")

    return violations


async def create_trade_proposal(
    session: AsyncSession,
    *,
    org_id: UUID,
    board_id: UUID,
    agent_id: UUID | None,
    params: TradeProposalCreate,
) -> TradeProposal:
    """Create a trade proposal with an associated Approval row.

    The trade will only execute after human approval.
    """
    # Verify wallet exists
    stmt = select(PolymarketWallet).where(
        PolymarketWallet.organization_id == org_id,
        PolymarketWallet.is_active == True,  # noqa: E712
    )
    wallet = (await session.execute(stmt)).scalar_one_or_none()
    if wallet is None:
        raise ValueError("No active Polymarket wallet configured for this organization.")

    # Validate risk controls
    stmt_risk = select(PolymarketRiskConfig).where(
        PolymarketRiskConfig.organization_id == org_id
    )
    risk_config = (await session.execute(stmt_risk)).scalar_one_or_none()
    violations = validate_risk_controls(risk_config, params.size_usdc, params.condition_id)
    if violations:
        raise ValueError(f"Risk control violation: {'; '.join(violations)}")

    # Fetch market snapshot
    market = await get_market_detail(params.condition_id)
    market_question = market.question if market else ""
    market_slug = market.slug if market else ""
    outcome_label = ""
    if market:
        for tok in market.tokens:
            if tok.get("token_id") == params.token_id:
                outcome_label = tok.get("outcome", "")
                break

    now = utcnow()

    # Create trade proposal
    proposal = TradeProposal(
        id=uuid4(),
        organization_id=org_id,
        board_id=board_id,
        agent_id=agent_id,
        condition_id=params.condition_id,
        token_id=params.token_id,
        market_slug=market_slug,
        market_question=market_question,
        outcome_label=outcome_label,
        side=params.side.upper(),
        size_usdc=params.size_usdc,
        price=params.price,
        order_type=params.order_type,
        reasoning=params.reasoning,
        confidence=params.confidence,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(proposal)
    await session.flush()

    # Create linked Approval (enforced gate)
    approval = Approval(
        id=uuid4(),
        board_id=board_id,
        agent_id=agent_id,
        action_type="polymarket_trade",
        payload={
            "trade_proposal_id": str(proposal.id),
            "market_question": market_question,
            "outcome": outcome_label,
            "side": params.side.upper(),
            "size_usdc": params.size_usdc,
            "price": params.price,
            "reasoning": params.reasoning,
            "reason": params.reasoning,
        },
        confidence=params.confidence,
        status="pending",
        created_at=now,
    )
    session.add(approval)
    await session.flush()

    proposal.approval_id = approval.id
    session.add(proposal)
    await session.flush()

    logger.info(
        "polymarket.trade.proposed",
        extra={
            "proposal_id": str(proposal.id),
            "approval_id": str(approval.id),
            "market": market_question,
            "side": params.side,
            "size": params.size_usdc,
        },
    )
    return proposal


async def execute_approved_trade(
    session: AsyncSession,
    trade_proposal_id: UUID,
) -> TradeHistory | None:
    """Execute a trade that has been approved. Called by the background worker only."""
    proposal = await session.get(TradeProposal, trade_proposal_id)
    if proposal is None:
        logger.warning("polymarket.execute.proposal_missing", extra={"id": str(trade_proposal_id)})
        return None

    if proposal.status != "approved":
        logger.warning(
            "polymarket.execute.wrong_status",
            extra={"id": str(trade_proposal_id), "status": proposal.status},
        )
        return None

    # Load wallet
    stmt = select(PolymarketWallet).where(
        PolymarketWallet.organization_id == proposal.organization_id,
        PolymarketWallet.is_active == True,  # noqa: E712
    )
    wallet = (await session.execute(stmt)).scalar_one_or_none()
    if wallet is None:
        proposal.status = "failed"
        proposal.execution_error = "No active wallet"
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.commit()
        return None

    # Re-validate risk controls
    stmt_risk = select(PolymarketRiskConfig).where(
        PolymarketRiskConfig.organization_id == proposal.organization_id
    )
    risk_config = (await session.execute(stmt_risk)).scalar_one_or_none()
    violations = validate_risk_controls(risk_config, proposal.size_usdc, proposal.condition_id)
    if violations:
        proposal.status = "failed"
        proposal.execution_error = f"Risk control violation at execution: {'; '.join(violations)}"
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.commit()
        return None

    # Execute via py-clob-client
    try:
        client = get_clob_client(wallet)
        from py_clob_client.order_builder.constants import BUY, SELL

        side = BUY if proposal.side == "BUY" else SELL

        order_args = {
            "token_id": proposal.token_id,
            "price": proposal.price,
            "size": proposal.size_usdc,
            "side": side,
        }

        signed_order = client.create_order(order_args)
        result = client.post_order(signed_order, order_type=proposal.order_type)

        order_id = result.get("orderID", "") if isinstance(result, dict) else str(result)

        now = utcnow()
        proposal.status = "executed"
        proposal.polymarket_order_id = order_id
        proposal.executed_at = now
        proposal.updated_at = now
        session.add(proposal)

        history = TradeHistory(
            id=uuid4(),
            organization_id=proposal.organization_id,
            trade_proposal_id=proposal.id,
            condition_id=proposal.condition_id,
            token_id=proposal.token_id,
            market_slug=proposal.market_slug,
            market_question=proposal.market_question,
            outcome_label=proposal.outcome_label,
            side=proposal.side,
            size_usdc=proposal.size_usdc,
            price=proposal.price,
            polymarket_order_id=order_id,
            status="filled",
            executed_at=now,
            created_at=now,
        )
        session.add(history)
        await session.commit()

        logger.info(
            "polymarket.trade.executed",
            extra={
                "proposal_id": str(proposal.id),
                "order_id": order_id,
                "market": proposal.market_question,
            },
        )
        return history

    except Exception as exc:
        proposal.status = "failed"
        proposal.execution_error = str(exc)[:500]
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.commit()
        logger.exception(
            "polymarket.trade.execution_failed",
            extra={"proposal_id": str(trade_proposal_id), "error": str(exc)},
        )
        return None
