"""Ecosystem intelligence fetcher — pulls trending repos from GitHub Search API.

One refresh cycle issues a small number of GitHub Search requests (each
returning up to 100 repos), upserts results into `ecosystem_repos`, and
captures a stars/forks snapshot per repo into `ecosystem_snapshots` so the
next cycle can compute a 24h growth delta.

Design notes
------------
- **Global, not org-scoped.** GitHub data is the same for every viewer; the
  per-org `ecosystem_intel` flag gates *access* at the API layer, not storage.
- **Query budget.** 5 search calls per refresh (AI/ML stars, AI/ML trending,
  SWE stars, SWE trending, Skills topics) = 500 results max. The 5000 req/hr
  authenticated limit is plenty even with hourly retries.
- **Auth.** Reads `GITHUB_API_TOKEN` from settings. Without a token GitHub
  caps unauthenticated traffic at 60 req/hr — too tight for this loop, so we
  fail fast on missing token rather than silently degrade.
- **No issue scraping.** Build-opportunity cards (heyneo's main differentiator)
  are deliberately out of scope for v1 — they multiply API load and the value
  hasn't been validated yet.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.time import utcnow
from app.models.ecosystem_repos import EcosystemRepo, EcosystemSnapshot

logger = logging.getLogger(__name__)


GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

# Per-category search queries. `q` is GitHub Search syntax; `sort` is `stars`
# or `updated`; `order` is desc. `category` is the label we attach to results.
#
# Topic strings include MCP because the gateway speaks that protocol — tracking
# MCP server repos surfaces ecosystem integrations worth watching.
SEARCH_QUERIES: list[dict[str, str]] = [
    {
        "category": "ai_ml",
        "q": (
            "(topic:ai OR topic:llm OR topic:agent OR topic:ai-agents OR "
            "topic:llm-agent OR topic:claude OR topic:claude-code OR "
            "topic:anthropic OR topic:mcp OR topic:model-context-protocol) "
            "stars:>100"
        ),
        "sort": "stars",
    },
    {
        "category": "ai_ml_trending",
        "q": (
            "(topic:ai OR topic:llm OR topic:agent OR topic:ai-agents OR "
            "topic:claude-code OR topic:mcp) "
            "pushed:>2026-04-23 stars:>50"
        ),
        "sort": "stars",
    },
    {
        "category": "swe",
        "q": "(topic:developer-tools OR topic:cli OR topic:productivity) stars:>500",
        "sort": "stars",
    },
    {
        "category": "swe_trending",
        "q": (
            "(topic:developer-tools OR topic:cli OR topic:productivity) "
            "pushed:>2026-04-23 stars:>100"
        ),
        "sort": "stars",
    },
    {
        "category": "skills_ecosystem",
        "q": (
            "(topic:claude-skills OR topic:claude-code-skills OR "
            "topic:agent-skills OR topic:claude-code-agents OR "
            "topic:claude-agents) stars:>10"
        ),
        "sort": "stars",
    },
]

# Pinned repos — always present in the Skills Ecosystem tab regardless of
# topic tagging. Adjust as the ecosystem matures.
PINNED_REPOS: list[tuple[str, str]] = [
    ("openclaw", "openclaw"),
    ("anthropics", "claude-code"),
    ("mattpocock", "skills"),
    ("forrestchang", "andrej-karpathy-skills"),
    ("affaan-m", "everything-claude-code"),
    ("nextlevelbuilder", "ui-ux-pro-max-skill"),
    ("VoltAgent", "awesome-design-md"),
]


@dataclass
class RefreshResult:
    """Summary of a refresh cycle, returned by `refresh_ecosystem`."""

    fetched: int
    upserted: int
    snapshots: int
    started_at: datetime
    finished_at: datetime
    error: str | None = None


def _trending_pushed_threshold() -> str:
    """ISO date string for `pushed:>` filters — 7 days ago in UTC."""
    from datetime import timedelta

    return (utcnow() - timedelta(days=7)).date().isoformat()


def _build_search_queries() -> list[dict[str, str]]:
    """Return search queries with a fresh trending threshold each call.

    The `pushed:>...` literal in SEARCH_QUERIES is a placeholder — this helper
    overrides it so the trending window is always the last 7 days.
    """
    threshold = _trending_pushed_threshold()
    out: list[dict[str, str]] = []
    for q in SEARCH_QUERIES:
        if "pushed:>" in q["q"]:
            new_q = q["q"].replace("pushed:>2026-04-23", f"pushed:>{threshold}")
            out.append({**q, "q": new_q})
        else:
            out.append(dict(q))
    return out


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _fetch_search_page(
    client: httpx.AsyncClient,
    query: str,
    sort: str,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """Issue a single GitHub Search call and return the `items` array."""
    params = {"q": query, "sort": sort, "order": "desc", "per_page": per_page}
    resp = await client.get(GITHUB_SEARCH_URL, params=params)
    if resp.status_code == 422:
        # Malformed query — log and skip rather than failing the whole refresh.
        logger.warning(
            "ecosystem_intel.search_invalid query=%s body=%s",
            query,
            resp.text[:500],
        )
        return []
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        logger.warning("ecosystem_intel.rate_limited body=%s", resp.text[:200])
        return []
    resp.raise_for_status()
    body = resp.json()
    items = body.get("items", [])
    return items if isinstance(items, list) else []


async def _fetch_repo_direct(
    client: httpx.AsyncClient,
    owner: str,
    name: str,
) -> dict[str, Any] | None:
    """Fetch a single repo's metadata (used for pinned repos)."""
    url = f"https://api.github.com/repos/{owner}/{name}"
    resp = await client.get(url)
    if resp.status_code == 404:
        return None
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        logger.warning("ecosystem_intel.rate_limited body=%s", resp.text[:200])
        return None
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else None


def _coerce_to_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _normalize_item(item: dict[str, Any], category: str) -> dict[str, Any] | None:
    """Convert a GitHub API repo dict into our normalized field set."""
    full_name = item.get("full_name")
    if not isinstance(full_name, str) or "/" not in full_name:
        return None
    owner_obj = item.get("owner") or {}
    owner = owner_obj.get("login") if isinstance(owner_obj, dict) else None
    if not isinstance(owner, str):
        owner = full_name.split("/", 1)[0]
    name = item.get("name")
    if not isinstance(name, str):
        name = full_name.split("/", 1)[1]
    topics = item.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    return {
        "full_name": full_name,
        "owner": owner,
        "name": name,
        "description": item.get("description") if isinstance(item.get("description"), str) else None,
        "html_url": item.get("html_url") or f"https://github.com/{full_name}",
        "language": item.get("language") if isinstance(item.get("language"), str) else None,
        "category": category,
        "stars": _coerce_to_int(item.get("stargazers_count")),
        "forks": _coerce_to_int(item.get("forks_count")),
        "open_issues": _coerce_to_int(item.get("open_issues_count")),
        "topics_json": json.dumps([t for t in topics if isinstance(t, str)]),
        "pushed_at": _parse_iso(item.get("pushed_at")),
        "repo_created_at": _parse_iso(item.get("created_at")),
    }


async def _upsert_repo(
    session: AsyncSession,
    normalized: dict[str, Any],
) -> EcosystemRepo:
    """Insert or update a repo row, returning the persisted model."""
    result = await session.exec(
        select(EcosystemRepo).where(EcosystemRepo.full_name == normalized["full_name"])
    )
    existing = result.first()
    now = utcnow()
    if existing is None:
        repo = EcosystemRepo(
            full_name=normalized["full_name"],
            owner=normalized["owner"],
            name=normalized["name"],
            description=normalized["description"],
            html_url=normalized["html_url"],
            language=normalized["language"],
            category=normalized["category"],
            stars=normalized["stars"],
            forks=normalized["forks"],
            open_issues=normalized["open_issues"],
            topics_json=normalized["topics_json"],
            pushed_at=normalized["pushed_at"],
            repo_created_at=normalized["repo_created_at"],
            first_seen_at=now,
            last_synced_at=now,
        )
        session.add(repo)
        await session.flush()
        return repo

    # Preserve original `category` when the same repo shows up in a different
    # search bucket on later refreshes — e.g. don't overwrite "skills_ecosystem"
    # with "ai_ml" just because the AI/ML query is broader.
    existing.owner = normalized["owner"]
    existing.name = normalized["name"]
    existing.description = normalized["description"]
    existing.html_url = normalized["html_url"]
    existing.language = normalized["language"]
    existing.stars = normalized["stars"]
    existing.forks = normalized["forks"]
    existing.open_issues = normalized["open_issues"]
    existing.topics_json = normalized["topics_json"]
    existing.pushed_at = normalized["pushed_at"]
    existing.repo_created_at = normalized["repo_created_at"]
    if existing.category == "other":
        existing.category = normalized["category"]
    elif existing.category != "skills_ecosystem" and normalized["category"] == "skills_ecosystem":
        # Skills ecosystem promotion wins.
        existing.category = "skills_ecosystem"
    existing.last_synced_at = now
    session.add(existing)
    await session.flush()
    return existing


async def _record_snapshot(session: AsyncSession, repo: EcosystemRepo) -> None:
    snap = EcosystemSnapshot(
        repo_id=repo.id,
        captured_at=utcnow(),
        stars=repo.stars,
        forks=repo.forks,
    )
    session.add(snap)


async def refresh_ecosystem(session: AsyncSession) -> RefreshResult:
    """Run one full refresh cycle. Returns a summary.

    Errors during a single search call are logged and tolerated — the cycle
    still records snapshots for whatever was successfully fetched. A hard
    error (e.g., missing token, network down) is captured in `error`.
    """
    started = utcnow()
    if not settings.github_api_token:
        finished = utcnow()
        return RefreshResult(
            fetched=0,
            upserted=0,
            snapshots=0,
            started_at=started,
            finished_at=finished,
            error="GITHUB_API_TOKEN not configured",
        )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.github_api_token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "vantageclaw-ecosystem-intel/1.0",
    }

    fetched_items: list[tuple[str, dict[str, Any]]] = []
    error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            # Search queries
            for q in _build_search_queries():
                try:
                    items = await _fetch_search_page(client, q["q"], q["sort"])
                except httpx.HTTPError as exc:
                    logger.warning(
                        "ecosystem_intel.search_failed category=%s err=%s",
                        q["category"],
                        exc,
                    )
                    continue
                for item in items:
                    fetched_items.append((q["category"], item))

            # Pinned repos
            for owner, name in PINNED_REPOS:
                try:
                    item = await _fetch_repo_direct(client, owner, name)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "ecosystem_intel.pinned_failed repo=%s/%s err=%s",
                        owner,
                        name,
                        exc,
                    )
                    continue
                if item is not None:
                    fetched_items.append(("skills_ecosystem", item))
    except Exception as exc:  # noqa: BLE001
        # Do not silently swallow — log full traceback and surface in result.
        logger.exception("ecosystem_intel.refresh_aborted")
        error = str(exc)[:200]

    upserted = 0
    snapshots = 0
    seen_ids: set[str] = set()
    for category, item in fetched_items:
        normalized = _normalize_item(item, category)
        if normalized is None:
            continue
        if normalized["full_name"] in seen_ids:
            continue
        seen_ids.add(normalized["full_name"])
        repo = await _upsert_repo(session, normalized)
        await _record_snapshot(session, repo)
        upserted += 1
        snapshots += 1

    if upserted:
        await session.commit()

    finished = utcnow()
    return RefreshResult(
        fetched=len(fetched_items),
        upserted=upserted,
        snapshots=snapshots,
        started_at=started,
        finished_at=finished,
        error=error,
    )


async def get_growth_deltas(
    session: AsyncSession,
    repo_ids: Iterable[str],
    *,
    hours: int = 24,
) -> dict[str, int]:
    """Return star-count delta per repo over the last `hours` window.

    Looks up the most recent snapshot older than `hours` ago for each repo and
    returns `current_stars - older_stars`. Repos without a prior snapshot get 0.
    """
    from datetime import timedelta

    threshold = utcnow() - timedelta(hours=hours)
    repo_id_list = [rid for rid in repo_ids]
    if not repo_id_list:
        return {}

    # For each repo, find current stars and the latest snapshot before threshold.
    stmt = select(EcosystemRepo).where(EcosystemRepo.id.in_(repo_id_list))  # type: ignore[attr-defined]
    result = await session.exec(stmt)
    repos = {str(r.id): r for r in result.all()}

    deltas: dict[str, int] = {}
    for rid_str, repo in repos.items():
        snap_stmt = (
            select(EcosystemSnapshot)
            .where(EcosystemSnapshot.repo_id == repo.id)
            .where(EcosystemSnapshot.captured_at < threshold)
            .order_by(EcosystemSnapshot.captured_at.desc())  # type: ignore[attr-defined]
            .limit(1)
        )
        snap_result = await session.exec(snap_stmt)
        snap = snap_result.first()
        if snap is None:
            deltas[rid_str] = 0
        else:
            deltas[rid_str] = max(0, repo.stars - snap.stars)
    return deltas
