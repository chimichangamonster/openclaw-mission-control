"""Crypto trade proposal creation with risk validation and post-approval execution."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.approvals import Approval
from app.models.crypto_trade_proposals import CryptoTradeProposal
from app.models.exchange_accounts import ExchangeAccount
from app.models.polymarket_risk_config import PolymarketRiskConfig
from app.schemas.crypto_trading import CryptoTradeProposalCreate
from app.services.binance.credentials import get_binance_client
from app.services.binance.queue import QueuedCryptoTrade, enqueue_crypto_trade

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)


async def create_crypto_trade_proposal(
    session: AsyncSession,
    *,
    org_id: UUID,
    board_id: UUID,
    agent_id: UUID | None,
    params: CryptoTradeProposalCreate,
) -> CryptoTradeProposal:
    """Create a crypto trade proposal with an associated Approval."""
    # Verify exchange account exists
    stmt = select(ExchangeAccount).where(
        ExchangeAccount.organization_id == org_id,
        ExchangeAccount.exchange == "binance",
        ExchangeAccount.is_active == True,  # noqa: E712
    )
    exchange_account = (await session.execute(stmt)).scalar_one_or_none()
    if exchange_account is None:
        raise ValueError("No active Binance account configured for this organization.")

    now = utcnow()

    # Determine trade value for display
    trade_value = ""
    if params.quote_amount:
        trade_value = f"${params.quote_amount:.2f} USDT"
    elif params.price and params.quantity:
        trade_value = (
            f"{params.quantity} @ ${params.price:.2f} = ~${params.quantity * params.price:.2f}"
        )
    elif params.quantity:
        trade_value = f"{params.quantity} units (market)"

    # Create trade proposal
    proposal = CryptoTradeProposal(
        id=uuid4(),
        organization_id=org_id,
        board_id=board_id,
        agent_id=agent_id,
        exchange_account_id=exchange_account.id,
        exchange="binance",
        symbol=params.symbol.upper(),
        side=params.side.upper(),
        order_type=params.order_type.upper(),
        quantity=params.quantity or 0.0,
        price=params.price,
        stop_price=params.stop_price,
        quote_amount=params.quote_amount,
        time_in_force=params.time_in_force,
        reasoning=params.reasoning,
        confidence=params.confidence,
        strategy=params.strategy,
        entry_signal=params.entry_signal,
        target_price=params.target_price,
        stop_loss_price=params.stop_loss_price,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(proposal)
    await session.flush()

    # Check if auto-execution is allowed (uses shared Polymarket risk config)
    stmt_risk = select(PolymarketRiskConfig).where(PolymarketRiskConfig.organization_id == org_id)
    risk_config = (await session.execute(stmt_risk)).scalar_one_or_none()

    # Determine trade size for auto-execute check
    trade_size = params.quote_amount or ((params.quantity or 0) * (params.price or 0))
    auto_execute = (
        risk_config is not None
        and not risk_config.require_approval
        and trade_size <= (risk_config.auto_execute_max_size_usdc or 50.0)
        and params.confidence >= (risk_config.auto_execute_min_confidence or 75.0)
    )

    if auto_execute:
        proposal.status = "approved"
        session.add(proposal)
        await session.flush()

        enqueue_crypto_trade(
            QueuedCryptoTrade(
                trade_proposal_id=proposal.id,
                organization_id=org_id,
            )
        )

        logger.info(
            "binance.trade.auto_approved",
            extra={
                "proposal_id": str(proposal.id),
                "symbol": params.symbol,
                "side": params.side,
                "value": trade_value,
                "confidence": params.confidence,
            },
        )
    else:
        # Create linked Approval (human review required)
        approval = Approval(
            id=uuid4(),
            board_id=board_id,
            agent_id=agent_id,
            action_type="crypto_trade",
            payload={
                "trade_proposal_id": str(proposal.id),
                "exchange": "binance",
                "symbol": params.symbol.upper(),
                "side": params.side.upper(),
                "order_type": params.order_type,
                "value": trade_value,
                "reasoning": params.reasoning,
                "reason": params.reasoning,
                "strategy": params.strategy,
                "target": str(params.target_price) if params.target_price else None,
                "stop_loss": str(params.stop_loss_price) if params.stop_loss_price else None,
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
            "binance.trade.proposed",
            extra={
                "proposal_id": str(proposal.id),
                "symbol": params.symbol,
                "side": params.side,
                "value": trade_value,
            },
        )
    return proposal


async def execute_approved_crypto_trade(
    session: AsyncSession,
    trade_proposal_id: UUID,
) -> CryptoTradeProposal | None:
    """Execute an approved crypto trade on Binance. Called by background worker only."""
    proposal = await session.get(CryptoTradeProposal, trade_proposal_id)
    if proposal is None:
        logger.warning("binance.execute.proposal_missing", extra={"id": str(trade_proposal_id)})
        return None

    if proposal.status != "approved":
        logger.warning(
            "binance.execute.wrong_status",
            extra={"id": str(trade_proposal_id), "status": proposal.status},
        )
        return None

    # Load exchange account
    exchange_account = await session.get(ExchangeAccount, proposal.exchange_account_id)
    if exchange_account is None or not exchange_account.is_active:
        proposal.status = "failed"
        proposal.execution_error = "No active exchange account"
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.commit()
        return None

    try:
        client = get_binance_client(exchange_account)

        order_params: dict = {
            "symbol": proposal.symbol,
            "side": proposal.side,
            "type": proposal.order_type,
        }

        if proposal.order_type == "MARKET":
            if proposal.quote_amount and proposal.side == "BUY":
                order_params["quoteOrderQty"] = proposal.quote_amount
            else:
                order_params["quantity"] = proposal.quantity
        elif proposal.order_type == "LIMIT":
            order_params["quantity"] = proposal.quantity
            order_params["price"] = str(proposal.price)
            order_params["timeInForce"] = proposal.time_in_force
        elif proposal.order_type in ("STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"):
            order_params["quantity"] = proposal.quantity
            order_params["price"] = str(proposal.price)
            order_params["stopPrice"] = str(proposal.stop_price)
            order_params["timeInForce"] = proposal.time_in_force

        result = client.create_order(**order_params)

        now = utcnow()
        proposal.status = "executed"
        proposal.exchange_order_id = str(result.get("orderId", ""))
        proposal.filled_price = float(result.get("price", 0) or 0)
        proposal.filled_quantity = float(result.get("executedQty", 0) or 0)
        proposal.executed_at = now
        proposal.updated_at = now
        session.add(proposal)
        await session.commit()

        logger.info(
            "binance.trade.executed",
            extra={
                "proposal_id": str(proposal.id),
                "order_id": proposal.exchange_order_id,
                "symbol": proposal.symbol,
                "side": proposal.side,
                "filled_qty": proposal.filled_quantity,
            },
        )
        return proposal

    except Exception as exc:
        proposal.status = "failed"
        proposal.execution_error = str(exc)[:500]
        proposal.updated_at = utcnow()
        session.add(proposal)
        await session.commit()
        logger.exception(
            "binance.trade.execution_failed",
            extra={"proposal_id": str(trade_proposal_id), "error": str(exc)},
        )
        return None
