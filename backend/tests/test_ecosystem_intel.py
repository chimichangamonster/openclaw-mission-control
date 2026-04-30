# ruff: noqa: INP001
"""Tests for ecosystem intelligence — fetcher normalization, upsert, growth delta.

Networking is patched out — all GitHub calls return canned fixtures, so these
tests stay deterministic and fast. Real network behavior (rate limits, 422s)
is exercised via the resilience branches in `_fetch_search_page`.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.time import utcnow
from app.models.ecosystem_repos import EcosystemRepo, EcosystemSnapshot
from app.services import ecosystem_intel as svc


async def _make_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker()


def _fake_item(
    *,
    full_name: str,
    stars: int = 100,
    forks: int = 10,
    language: str = "Python",
    topics: list[str] | None = None,
    description: str = "Sample repo",
) -> dict[str, Any]:
    owner, name = full_name.split("/", 1)
    return {
        "full_name": full_name,
        "name": name,
        "owner": {"login": owner},
        "description": description,
        "html_url": f"https://github.com/{full_name}",
        "language": language,
        "stargazers_count": stars,
        "forks_count": forks,
        "open_issues_count": 5,
        "topics": topics or ["ai", "agent"],
        "pushed_at": "2026-04-29T12:00:00Z",
        "created_at": "2024-01-01T00:00:00Z",
    }


def test_normalize_item_returns_full_field_set() -> None:
    item = _fake_item(full_name="anthropics/claude-code", stars=12345)
    out = svc._normalize_item(item, "ai_ml")
    assert out is not None
    assert out["full_name"] == "anthropics/claude-code"
    assert out["owner"] == "anthropics"
    assert out["name"] == "claude-code"
    assert out["stars"] == 12345
    assert out["category"] == "ai_ml"
    assert json.loads(out["topics_json"]) == ["ai", "agent"]
    assert out["pushed_at"] is not None
    assert out["repo_created_at"] is not None


def test_normalize_item_skips_malformed() -> None:
    assert svc._normalize_item({}, "ai_ml") is None
    assert svc._normalize_item({"full_name": "no-slash"}, "ai_ml") is None


def test_normalize_item_handles_missing_owner_and_topics() -> None:
    item = {
        "full_name": "fallback/repo",
        "name": "repo",
        "html_url": "https://github.com/fallback/repo",
        "description": None,
        "stargazers_count": "not-a-number",
        "topics": "not-a-list",
    }
    out = svc._normalize_item(item, "swe")
    assert out is not None
    assert out["owner"] == "fallback"  # derived from full_name
    assert out["stars"] == 0  # coerce-to-int fallback
    assert out["topics_json"] == "[]"


@pytest.mark.asyncio
async def test_upsert_creates_then_updates() -> None:
    session = await _make_session()

    normalized = svc._normalize_item(_fake_item(full_name="a/b", stars=10), "ai_ml")
    assert normalized is not None
    repo = await svc._upsert_repo(session, normalized)
    assert repo.id is not None
    assert repo.stars == 10

    # Update — same full_name, new stars
    normalized2 = svc._normalize_item(_fake_item(full_name="a/b", stars=25), "ai_ml")
    assert normalized2 is not None
    repo2 = await svc._upsert_repo(session, normalized2)
    assert repo2.id == repo.id  # same row
    assert repo2.stars == 25


@pytest.mark.asyncio
async def test_upsert_preserves_skills_ecosystem_category() -> None:
    """A repo first seen in skills_ecosystem should not be downgraded to ai_ml."""
    session = await _make_session()

    skills_item = svc._normalize_item(
        _fake_item(full_name="x/y"), "skills_ecosystem"
    )
    assert skills_item is not None
    await svc._upsert_repo(session, skills_item)

    # Same repo seen later in the broader AI/ML query — should stay as skills_ecosystem
    ai_item = svc._normalize_item(_fake_item(full_name="x/y"), "ai_ml")
    assert ai_item is not None
    repo = await svc._upsert_repo(session, ai_item)
    assert repo.category == "skills_ecosystem"


@pytest.mark.asyncio
async def test_upsert_promotes_other_to_skills_ecosystem() -> None:
    session = await _make_session()
    other = svc._normalize_item(_fake_item(full_name="m/n"), "other")
    assert other is not None
    await svc._upsert_repo(session, other)

    skills = svc._normalize_item(_fake_item(full_name="m/n"), "skills_ecosystem")
    assert skills is not None
    repo = await svc._upsert_repo(session, skills)
    assert repo.category == "skills_ecosystem"


@pytest.mark.asyncio
async def test_growth_delta_returns_zero_without_prior_snapshot() -> None:
    session = await _make_session()
    repo = EcosystemRepo(
        full_name="solo/repo",
        owner="solo",
        name="repo",
        html_url="https://github.com/solo/repo",
        category="ai_ml",
        stars=500,
        forks=10,
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)

    deltas = await svc.get_growth_deltas(session, [repo.id], hours=24)
    assert deltas[str(repo.id)] == 0


@pytest.mark.asyncio
async def test_growth_delta_computes_24h_difference() -> None:
    session = await _make_session()
    repo = EcosystemRepo(
        full_name="growth/repo",
        owner="growth",
        name="repo",
        html_url="https://github.com/growth/repo",
        category="ai_ml",
        stars=1000,
        forks=10,
    )
    session.add(repo)
    await session.flush()

    # Older snapshot from 36h ago — should be the one used
    old_snap = EcosystemSnapshot(
        repo_id=repo.id,
        captured_at=utcnow() - timedelta(hours=36),
        stars=850,
        forks=8,
    )
    # Recent snapshot from 12h ago — should be ignored (newer than 24h window)
    recent_snap = EcosystemSnapshot(
        repo_id=repo.id,
        captured_at=utcnow() - timedelta(hours=12),
        stars=975,
        forks=9,
    )
    session.add(old_snap)
    session.add(recent_snap)
    await session.commit()

    deltas = await svc.get_growth_deltas(session, [repo.id], hours=24)
    assert deltas[str(repo.id)] == 150  # 1000 - 850


@pytest.mark.asyncio
async def test_growth_delta_clamps_negative_to_zero() -> None:
    """If a repo loses stars (e.g. data correction), report 0 not negative."""
    session = await _make_session()
    repo = EcosystemRepo(
        full_name="shrink/repo",
        owner="shrink",
        name="repo",
        html_url="https://github.com/shrink/repo",
        category="ai_ml",
        stars=400,
        forks=10,
    )
    session.add(repo)
    await session.flush()
    session.add(
        EcosystemSnapshot(
            repo_id=repo.id,
            captured_at=utcnow() - timedelta(hours=48),
            stars=500,
            forks=10,
        )
    )
    await session.commit()

    deltas = await svc.get_growth_deltas(session, [repo.id], hours=24)
    assert deltas[str(repo.id)] == 0


@pytest.mark.asyncio
async def test_refresh_short_circuits_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc.settings, "github_api_token", "")
    session = await _make_session()
    result = await svc.refresh_ecosystem(session)
    assert result.error == "GITHUB_API_TOKEN not configured"
    assert result.fetched == 0
    assert result.upserted == 0


@pytest.mark.asyncio
async def test_refresh_persists_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: fake fetchers return items → repos + snapshots persisted."""
    monkeypatch.setattr(svc.settings, "github_api_token", "fake-token")

    async def fake_search(client: Any, query: str, sort: str, per_page: int = 100) -> list[Any]:
        # Return one item per call so the seen_ids dedup gets exercised across queries.
        return [_fake_item(full_name=f"search/{sort}-{query[:5]}", stars=100)]

    async def fake_direct(client: Any, owner: str, name: str) -> Any:
        return _fake_item(full_name=f"{owner}/{name}", stars=500)

    monkeypatch.setattr(svc, "_fetch_search_page", fake_search)
    monkeypatch.setattr(svc, "_fetch_repo_direct", fake_direct)

    session = await _make_session()
    result = await svc.refresh_ecosystem(session)
    assert result.error is None
    assert result.upserted > 0
    assert result.snapshots == result.upserted

    persisted = (await session.exec(select(EcosystemRepo))).all()
    assert len(persisted) == result.upserted

    snaps = (await session.exec(select(EcosystemSnapshot))).all()
    assert len(snaps) == result.snapshots


@pytest.mark.asyncio
async def test_refresh_dedup_across_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    """A repo returned by both AI/ML and SWE searches should only be upserted once per cycle."""
    monkeypatch.setattr(svc.settings, "github_api_token", "fake-token")

    async def fake_search(client: Any, query: str, sort: str, per_page: int = 100) -> list[Any]:
        return [_fake_item(full_name="dup/repo", stars=200)]

    async def fake_direct(client: Any, owner: str, name: str) -> Any:
        return None  # skip pinned for this test

    monkeypatch.setattr(svc, "_fetch_search_page", fake_search)
    monkeypatch.setattr(svc, "_fetch_repo_direct", fake_direct)

    session = await _make_session()
    result = await svc.refresh_ecosystem(session)
    assert result.upserted == 1  # deduped despite 5 search calls returning the same repo

    # And only one row + one snapshot per cycle
    repos = (await session.exec(select(EcosystemRepo))).all()
    assert len(repos) == 1
    snaps = (await session.exec(select(EcosystemSnapshot))).all()
    assert len(snaps) == 1


def test_trending_threshold_is_recent() -> None:
    threshold = svc._trending_pushed_threshold()
    # Format YYYY-MM-DD
    assert len(threshold) == 10
    assert threshold[4] == "-" and threshold[7] == "-"


def test_build_search_queries_substitutes_threshold() -> None:
    queries = svc._build_search_queries()
    fresh = svc._trending_pushed_threshold()
    for q in queries:
        if "_trending" in q["category"]:
            assert fresh in q["q"]
    # Non-trending queries are unchanged
    non_trending = [q for q in queries if "_trending" not in q["category"]]
    assert non_trending, "Expected at least one non-trending search query"
    assert all("pushed:>" not in q["q"] for q in non_trending)


def test_parse_iso_round_trip() -> None:
    out = svc._parse_iso("2026-04-29T12:00:00Z")
    assert out is not None
    assert out.year == 2026 and out.month == 4 and out.day == 29
    assert svc._parse_iso(None) is None
    assert svc._parse_iso("garbage") is None


def test_coerce_to_int_handles_garbage() -> None:
    assert svc._coerce_to_int(42) == 42
    assert svc._coerce_to_int(3.7) == 3
    assert svc._coerce_to_int(True) == 1
    assert svc._coerce_to_int("nope") == 0
    assert svc._coerce_to_int(None) == 0


@pytest.mark.asyncio
async def test_growth_delta_empty_input() -> None:
    session = await _make_session()
    assert await svc.get_growth_deltas(session, [], hours=24) == {}


@pytest.mark.asyncio
async def test_growth_delta_unknown_repo_id_excluded() -> None:
    """get_growth_deltas should silently exclude IDs that don't exist."""
    session = await _make_session()
    fake_id = uuid4()
    deltas = await svc.get_growth_deltas(session, [fake_id], hours=24)
    assert str(fake_id) not in deltas
