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
    """Search Polymarket markets via the Gamma API.

    When a category tag is provided, uses the /events endpoint with tag_slug
    and flattens nested markets. Otherwise uses /markets for top-by-volume.
    """
    # Known category tags that map to Gamma event tag_slugs
    CATEGORY_TAGS = {
        "elections", "politics", "crypto", "sports", "finance",
        "science", "pop-culture", "us-presidential-election",
        "global-elections", "world-elections",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        if query and query.lower() in CATEGORY_TAGS:
            # Use events endpoint for category filtering
            params: dict[str, str | int | bool] = {
                "limit": min(limit, 10),  # events contain multiple markets each
                "closed": not active,
                "order": "volume",
                "ascending": False,
                "tag_slug": query.lower(),
            }
            url = f"{GAMMA_URL}/events"
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            events = resp.json()

            # Flatten markets from events
            raw_markets = []
            for event in (events if isinstance(events, list) else []):
                for m in event.get("markets", []):
                    if not m.get("closed", False):
                        raw_markets.append(m)

            # Sort by volume and limit
            raw_markets.sort(
                key=lambda m: float(m.get("volumeNum", m.get("volume", 0)) or 0),
                reverse=True,
            )
            data = raw_markets[:limit]
        else:
            # Use markets endpoint for top-by-volume or free-text search
            params = {
                "limit": limit,
                "offset": offset,
                "closed": not active,
                "order": "volume",
                "ascending": False,
            }
            url = f"{GAMMA_URL}/markets"
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

    results = []
    for market in data if isinstance(data, list) else data.get("data", data.get("markets", [])):
        outcomes: list[str] = []
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
            raw_outcomes = market.get("outcomes", [])
            if isinstance(raw_outcomes, str):
                try:
                    import json as _json
                    raw_outcomes = _json.loads(raw_outcomes)
                except (ValueError, TypeError):
                    raw_outcomes = []
            outcomes = raw_outcomes if isinstance(raw_outcomes, list) else []

        # Parse prices from outcomePrices string if tokens didn't provide them
        if yes_price is None or no_price is None:
            raw_prices = market.get("outcomePrices", "")
            if isinstance(raw_prices, str) and raw_prices:
                try:
                    import json as _json
                    price_list = _json.loads(raw_prices)
                    if isinstance(price_list, list) and len(price_list) >= 2:
                        yes_price = yes_price or float(price_list[0])
                        no_price = no_price or float(price_list[1])
                except (ValueError, TypeError, IndexError):
                    pass

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
        raw_outcomes = market.get("outcomes", [])
        if isinstance(raw_outcomes, str):
            try:
                import json as _json
                raw_outcomes = _json.loads(raw_outcomes)
            except (ValueError, TypeError):
                raw_outcomes = []
        outcomes = raw_outcomes if isinstance(raw_outcomes, list) else []

    if yes_price is None or no_price is None:
        raw_prices = market.get("outcomePrices", "")
        if isinstance(raw_prices, str) and raw_prices:
            try:
                import json as _json
                price_list = _json.loads(raw_prices)
                if isinstance(price_list, list) and len(price_list) >= 2:
                    yes_price = yes_price or float(price_list[0])
                    no_price = no_price or float(price_list[1])
            except (ValueError, TypeError, IndexError):
                pass

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
