"""Budget monitoring — periodic check of per-agent spend against limits."""

from __future__ import annotations

import json
from datetime import date, datetime, UTC
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import select

from app.api.cost_tracker import _get_model_price, _classify_tier
from app.core.logging import get_logger
from app.core.resilience import gateway_rpc_breaker, retry_async
from app.core.time import utcnow
from app.services.error_tracker import track_error
from app.db.session import async_session_maker
from app.models.budget import BudgetConfig, DailyAgentSpend
from app.models.gateways import Gateway
from app.services.openclaw.gateway_rpc import GatewayConfig, openclaw_call

logger = get_logger(__name__)

# Track max tokens seen per session key to handle session compaction
_session_max_tokens: dict[str, tuple[int, int]] = {}
_session_max_date: str = ""


async def _get_gateway_config_for_org(org_id: UUID) -> GatewayConfig | None:
    """Resolve the gateway for a specific organization."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Gateway).where(Gateway.organization_id == org_id).limit(1)
        )
        gateway = result.scalars().first()
    if not gateway or not gateway.url:
        return None
    return GatewayConfig(url=gateway.url, token=gateway.token)


async def _get_or_create_budget_config(org_id: UUID) -> BudgetConfig:
    """Get the budget config for an org, creating a default if none exists."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(BudgetConfig).where(BudgetConfig.organization_id == org_id)
        )
        config = result.scalars().first()
        if config:
            return config
        config = BudgetConfig(id=uuid4(), organization_id=org_id, updated_at=utcnow())
        session.add(config)
        await session.commit()
        await session.refresh(config)
        return config


async def _aggregate_agent_spend(config: GatewayConfig) -> dict[str, dict]:
    """Fetch gateway sessions and aggregate tokens per agent."""
    global _session_max_tokens, _session_max_date

    today = date.today().isoformat()
    if _session_max_date != today:
        _session_max_tokens.clear()
        _session_max_date = today

    try:
        sessions_data = await retry_async(
            openclaw_call,
            "sessions.list",
            config=config,
            retries=2,
            base_delay=3.0,
            breaker=gateway_rpc_breaker,
            label="budget_monitor.sessions",
        )
    except Exception as exc:
        logger.warning("budget_monitor.sessions_rpc_failed")
        await track_error("budget_monitor", f"Failed to fetch gateway sessions: {str(exc)[:200]}")
        return {}

    raw_sessions = (
        sessions_data
        if isinstance(sessions_data, list)
        else sessions_data.get("sessions", [])
    )

    agent_agg: dict[str, dict] = {}

    for s in raw_sessions:
        key = s.get("key", "")
        if "heartbeat" in key or "mc-gateway" in key:
            continue

        parts = key.split(":")
        agent_name = parts[1] if len(parts) > 1 else "unknown"
        full_model = s.get("model") or "unknown"
        short_model = full_model.split("/")[-1]
        input_tok = s.get("inputTokens", 0)
        output_tok = s.get("outputTokens", 0)

        # Track max tokens per session key (handles compaction)
        prev = _session_max_tokens.get(key, (0, 0))
        input_tok = max(input_tok, prev[0])
        output_tok = max(output_tok, prev[1])
        _session_max_tokens[key] = (input_tok, output_tok)

        if agent_name not in agent_agg:
            agent_agg[agent_name] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "session_count": 0,
                "models": {},
            }

        agg = agent_agg[agent_name]
        agg["input_tokens"] += input_tok
        agg["output_tokens"] += output_tok
        agg["session_count"] += 1

        # Per-model cost breakdown
        prompt_pm, comp_pm = _get_model_price(short_model)
        model_cost = (input_tok / 1_000_000) * prompt_pm + (output_tok / 1_000_000) * comp_pm
        agg["models"][short_model] = agg["models"].get(short_model, 0.0) + model_cost

    # Compute total cost per agent
    for agent_name, agg in agent_agg.items():
        agg["estimated_cost"] = sum(agg["models"].values())

    return agent_agg


async def _upsert_daily_spend(org_id: UUID, agent_agg: dict[str, dict]) -> None:
    """Persist per-agent daily spend snapshots for an organization."""
    today = date.today()
    async with async_session_maker() as session:
        for agent_name, agg in agent_agg.items():
            result = await session.execute(
                select(DailyAgentSpend).where(
                    DailyAgentSpend.organization_id == org_id,
                    DailyAgentSpend.agent_name == agent_name,
                    DailyAgentSpend.date == today,
                )
            )
            existing = result.scalars().first()
            if existing:
                existing.input_tokens = agg["input_tokens"]
                existing.output_tokens = agg["output_tokens"]
                existing.estimated_cost = round(agg["estimated_cost"], 6)
                existing.model_breakdown_json = json.dumps(
                    {k: round(v, 6) for k, v in agg["models"].items()}
                )
                existing.session_count = agg["session_count"]
            else:
                spend = DailyAgentSpend(
                    id=uuid4(),
                    organization_id=org_id,
                    agent_name=agent_name,
                    date=today,
                    input_tokens=agg["input_tokens"],
                    output_tokens=agg["output_tokens"],
                    estimated_cost=round(agg["estimated_cost"], 6),
                    model_breakdown_json=json.dumps(
                        {k: round(v, 6) for k, v in agg["models"].items()}
                    ),
                    session_count=agg["session_count"],
                    created_at=utcnow(),
                )
                session.add(spend)
        await session.commit()


async def _send_discord_alert(gw_config: GatewayConfig, message: str) -> None:
    """Send an alert message to the #notifications channel via gateway."""
    try:
        await openclaw_call(
            "chat.send",
            params={
                "agentId": "notification-agent",
                "message": message,
            },
            config=gw_config,
        )
    except Exception:
        logger.warning("budget_monitor.alert_send_failed")


async def _check_thresholds(
    org_id: UUID,
    agent_agg: dict[str, dict],
    budget_config: BudgetConfig,
    gw_config: GatewayConfig,
) -> None:
    """Check monthly and daily thresholds for an org, send alerts if crossed."""
    if not budget_config.alerts_enabled:
        return

    current_month = datetime.now(UTC).strftime("%Y-%m")

    # Reset threshold tracking on new month
    if budget_config.last_alert_month != current_month:
        budget_config.last_alert_month = current_month
        budget_config.last_alert_thresholds_hit_json = "[]"

    already_hit = set(budget_config.last_alert_thresholds_hit)

    # Get monthly total for this org from database
    async with async_session_maker() as session:
        result = await session.execute(
            text(
                "SELECT COALESCE(SUM(estimated_cost), 0) FROM daily_agent_spends "
                "WHERE organization_id = :org_id AND date >= :month_start"
            ),
            {"org_id": str(org_id), "month_start": f"{current_month}-01"},
        )
        monthly_total = float(result.scalar() or 0)

    alerts: list[str] = []

    # Monthly budget threshold alerts
    for pct in budget_config.alert_thresholds:
        if pct in already_hit:
            continue
        threshold_amount = budget_config.monthly_budget * pct / 100
        if monthly_total >= threshold_amount:
            already_hit.add(pct)
            remaining = budget_config.monthly_budget - monthly_total
            alerts.append(
                f"**BUDGET ALERT — {pct}% of monthly budget reached**\n"
                f"Monthly spend: ${monthly_total:.2f} / ${budget_config.monthly_budget:.2f}\n"
                f"Remaining: ${remaining:.2f}"
            )

    # Per-agent daily limit alerts
    daily_limits = budget_config.agent_daily_limits
    exceeded_agents: list[str] = []
    for agent_name, agg in agent_agg.items():
        limit = daily_limits.get(agent_name)
        if limit and agg["estimated_cost"] > limit:
            exceeded_agents.append(
                f"  {agent_name}: ${agg['estimated_cost']:.4f} / ${limit:.2f} daily limit **EXCEEDED**"
            )

    if exceeded_agents:
        header = "**DAILY LIMIT EXCEEDED**\n"
        body = "\n".join(exceeded_agents)
        recommendation = ""
        if budget_config.throttle_to_tier1_on_exceed:
            recommendation = "\n\nRecommendation: Throttle exceeded agents to Tier 1 models for remaining tasks today."
        alerts.append(header + body + recommendation)

    # Send alerts and persist to error tracker
    for alert in alerts:
        await _send_discord_alert(gw_config, alert)
        await track_error("budget", alert[:500], severity="warning")

    # Persist updated thresholds
    if alerts:
        async with async_session_maker() as session:
            result = await session.execute(
                select(BudgetConfig).where(BudgetConfig.organization_id == org_id)
            )
            config = result.scalars().first()
            if config:
                config.last_alert_thresholds_hit_json = json.dumps(sorted(already_hit))
                config.last_alert_month = current_month
                config.updated_at = utcnow()
                await session.commit()


async def _update_prometheus_gauges(agent_agg: dict[str, dict], monthly_total: float, monthly_budget: float) -> None:
    """Update Prometheus gauges for budget metrics."""
    try:
        from app.core.prometheus import agent_daily_spend, monthly_budget_pct

        for agent_name, agg in agent_agg.items():
            agent_daily_spend.labels(agent=agent_name).set(round(agg["estimated_cost"], 6))

        if monthly_budget > 0:
            monthly_budget_pct.set(round((monthly_total / monthly_budget) * 100, 1))
    except Exception:  # noqa: BLE001
        pass


async def check_budgets() -> None:
    """Main budget check — called every 5 minutes from lifespan.

    Iterates over all organizations with a configured gateway and checks
    each org's budget independently.
    """
    from app.models.organizations import Organization

    # Get all orgs that have a gateway configured
    async with async_session_maker() as session:
        result = await session.execute(
            select(Gateway.organization_id).where(Gateway.url.isnot(None)).distinct()  # type: ignore[union-attr]
        )
        org_ids = [row[0] for row in result.all()]

    if not org_ids:
        return

    total_agents = 0
    total_monthly = 0.0

    for org_id in org_ids:
        gw_config = await _get_gateway_config_for_org(org_id)
        if not gw_config:
            continue

        budget_config = await _get_or_create_budget_config(org_id)
        agent_agg = await _aggregate_agent_spend(gw_config)
        if not agent_agg:
            continue

        await _upsert_daily_spend(org_id, agent_agg)
        await _check_thresholds(org_id, agent_agg, budget_config, gw_config)

        # Monthly total for Prometheus
        current_month = datetime.now(UTC).strftime("%Y-%m")
        async with async_session_maker() as session:
            result = await session.execute(
                text(
                    "SELECT COALESCE(SUM(estimated_cost), 0) FROM daily_agent_spends "
                    "WHERE organization_id = :org_id AND date >= :month_start"
                ),
                {"org_id": str(org_id), "month_start": f"{current_month}-01"},
            )
            monthly_total = float(result.scalar() or 0)

        await _update_prometheus_gauges(agent_agg, monthly_total, budget_config.monthly_budget)

        total_agents += len(agent_agg)
        total_monthly += monthly_total

    logger.info(
        "budget_monitor.check_complete orgs=%d agents=%d monthly=%.4f",
        len(org_ids),
        total_agents,
        total_monthly,
    )
