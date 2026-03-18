"""Polymarket market data fetching via Gamma and CLOB APIs."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.polymarket import MarketDetailRead, MarketSearchResult

logger = get_logger(__name__)

GAMMA_URL = settings.polymarket_gamma_base_url


async def search_markets(
    query: str = "",
    *,
    limit: int = 20,
    offset: int = 0,
    active: bool = True,
) -> list[MarketSearchResult]:
    """Search Polymarket markets via the Gamma API."""
    params: dict[str, str | int | bool] = {
        "limit": limit,
        "offset": offset,
        "closed": not active,
        "order": "volume",
        "ascending": False,
    }
    if query:
        params["tag"] = query  # Gamma supports tag-based filtering

    url = f"{GAMMA_URL}/markets"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for market in data if isinstance(data, list) else data.get("data", data.get("markets", [])):
        outcomes = []
        tokens = market.get("tokens", [])
        yes_price = None
        no_price = None

        for tok in tokens:
            outcome = tok.get("outcome", "")
            outcomes.append(outcome)
            price = tok.get("price")
            if price is not None:
                if outcome.lower() == "yes":
                    yes_price = float(price)
                elif outcome.lower() == "no":
                    no_price = float(price)

        if not outcomes:
            outcomes = market.get("outcomes", [])

        results.append(
            MarketSearchResult(
                condition_id=market.get("conditionId", market.get("condition_id", "")),
                question=market.get("question", ""),
                slug=market.get("slug", ""),
                outcomes=outcomes,
                end_date=market.get("endDate", market.get("end_date_iso")),
                volume=float(market.get("volume", 0) or 0),
                liquidity=float(market.get("liquidity", 0) or 0),
                yes_price=yes_price,
                no_price=no_price,
                active=not market.get("closed", False),
            )
        )
    return results


async def get_market_detail(condition_id: str) -> MarketDetailRead | None:
    """Fetch detailed market info from Gamma API."""
    url = f"{GAMMA_URL}/markets/{condition_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        market = resp.json()

    outcomes = []
    tokens_data = []
    yes_price = None
    no_price = None

    for tok in market.get("tokens", []):
        outcome = tok.get("outcome", "")
        outcomes.append(outcome)
        price = tok.get("price")
        tokens_data.append({
            "token_id": tok.get("token_id", ""),
            "outcome": outcome,
            "price": str(price) if price else "0",
        })
        if price is not None:
            if outcome.lower() == "yes":
                yes_price = float(price)
            elif outcome.lower() == "no":
                no_price = float(price)

    if not outcomes:
        outcomes = market.get("outcomes", [])

    return MarketDetailRead(
        condition_id=market.get("conditionId", market.get("condition_id", "")),
        question=market.get("question", ""),
        slug=market.get("slug", ""),
        description=market.get("description", ""),
        outcomes=outcomes,
        end_date=market.get("endDate", market.get("end_date_iso")),
        volume=float(market.get("volume", 0) or 0),
        liquidity=float(market.get("liquidity", 0) or 0),
        yes_price=yes_price,
        no_price=no_price,
        active=not market.get("closed", False),
        tokens=tokens_data,
    )
