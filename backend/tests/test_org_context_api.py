# ruff: noqa: INP001
"""E2E tests for the /org-context CRUD API (Phase 1).

Covers feature-flag gating, admin-only mutation, member visibility scoping
(shared vs private), org isolation, and the staleness-relevant fields
(``has_embedding``, ``age_days``).

Phase 2 will replace the metadata-only POST with a multipart upload that
runs document_intake → redact → embed; the tests for that pipeline get
added when that endpoint lands.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    check_org_rate_limit,
    get_session,
    require_org_from_actor,
    require_org_member,
)
from app.api.org_context import router as org_context_router
from app.core.time import utcnow
from app.models.org_context import OrgContextFile
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.models.organizations import Organization
from app.models.users import User
from app.services.organizations import OrganizationContext

# Standard fake embedding used across tests (1536 floats — pgvector size).
# Value doesn't matter; we never assert on similarity rankings here.
FAKE_EMBEDDING = [0.0] * 1536


@pytest.fixture(autouse=True)
def _mock_intake_and_embedding(monkeypatch):
    """Replace the two upstream services that hit OpenRouter so the upload
    pipeline runs end-to-end deterministically without a network call.

    Mocks are installed at the call-site in ``app.api.org_context`` (where
    they're imported) — patching ``app.services.*`` doesn't override the
    already-imported names in the API module.
    """

    async def _fake_process(
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        org_id,
        db_session,
    ) -> dict[str, Any]:
        return {
            "filename": filename,
            "content_type": content_type,
            "extracted_text": file_bytes.decode("utf-8", errors="replace"),
            "classification": {"type": "other", "confidence": 0, "summary": ""},
            "page_count": 0,
        }

    async def _fake_embedding(content: str, org_id):
        return FAKE_EMBEDDING

    monkeypatch.setattr(
        "app.api.org_context.process_document", _fake_process
    )
    monkeypatch.setattr("app.api.org_context.get_embedding", _fake_embedding)
    yield

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


ORG_ID = uuid4()
OTHER_ORG_ID = uuid4()
ADMIN_USER_ID = uuid4()
MEMBER_USER_ID = uuid4()


async def _make_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _seed(
    session: AsyncSession,
    *,
    flag_on: bool = True,
    role: str = "admin",
) -> OrganizationContext:
    now = utcnow()
    org = Organization(
        id=ORG_ID,
        name="Test Org",
        slug="test-org",
        created_at=now,
        updated_at=now,
    )
    session.add(org)

    user = User(
        id=ADMIN_USER_ID if role == "admin" else MEMBER_USER_ID,
        clerk_user_id=f"oc-test-{role}",
        email=f"{role}@test.com",
        name=f"{role.title()} User",
        active_organization_id=ORG_ID,
    )
    session.add(user)

    member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=user.id,
        role=role,
        all_boards_read=True,
        all_boards_write=True,
        created_at=now,
        updated_at=now,
    )
    session.add(member)

    flags = dict(DEFAULT_FEATURE_FLAGS)
    flags["org_context"] = flag_on
    settings = OrganizationSettings(
        id=uuid4(),
        organization_id=ORG_ID,
        feature_flags_json=json.dumps(flags),
    )
    session.add(settings)
    await session.commit()
    return OrganizationContext(organization=org, member=member)


def _build_app(
    maker: async_sessionmaker[AsyncSession],
    ctx: OrganizationContext,
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(org_context_router)
    app.include_router(api_v1)

    async def _override_session():
        async with maker() as session:
            yield session

    async def _override_org() -> OrganizationContext:
        return ctx

    async def _override_rate_limit() -> None:
        return None

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_org_member] = _override_org
    app.dependency_overrides[require_org_from_actor] = _override_org
    app.dependency_overrides[check_org_rate_limit] = _override_rate_limit
    return app


@pytest_asyncio.fixture
async def env_admin():
    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        ctx = await _seed(session, role="admin")
    app = _build_app(maker, ctx)
    yield {"app": app, "maker": maker, "ctx": ctx}
    await engine.dispose()


@pytest_asyncio.fixture
async def env_member():
    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        ctx = await _seed(session, role="member")
    app = _build_app(maker, ctx)
    yield {"app": app, "maker": maker, "ctx": ctx}
    await engine.dispose()


@pytest_asyncio.fixture
async def env_flag_off():
    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        ctx = await _seed(session, role="admin", flag_on=False)
    app = _build_app(maker, ctx)
    yield {"app": app, "maker": maker, "ctx": ctx}
    await engine.dispose()


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_flag_off_returns_403(env_flag_off):
    async with AsyncClient(
        transport=ASGITransport(app=env_flag_off["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/org-context")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CRUD happy path (admin)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_upload_list_get_patch_delete(env_admin):
    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        # Upload (multipart) — runs the full pipeline (mocked extract + embed)
        create_resp = await client.post(
            "/api/v1/org-context",
            files={
                "file": (
                    "auto-vertical-icp.md",
                    b"ICP: dealerships >$5M revenue, multi-location.",
                    "text/markdown",
                ),
            },
            data={
                "category": "prospects",
                "source": "manually pasted by Henz",
                "is_living_data": "true",
                "visibility": "shared",
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        file_id = created["id"]
        assert created["filename"] == "auto-vertical-icp.md"
        assert created["category"] == "prospects"
        assert created["visibility"] == "shared"
        # has_embedding True now — Session 2's pipeline embeds before persist
        assert created["has_embedding"] is True
        assert created["age_days"] == 0

        # List
        list_resp = await client.get("/api/v1/org-context")
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert items[0]["id"] == file_id

        # Get detail (includes extracted_text)
        get_resp = await client.get(f"/api/v1/org-context/{file_id}")
        assert get_resp.status_code == 200
        detail = get_resp.json()
        assert detail["extracted_text"].startswith("ICP: dealerships")

        # Patch — change category + flip living-data
        patch_resp = await client.patch(
            f"/api/v1/org-context/{file_id}",
            json={"category": "customers", "is_living_data": False},
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched["category"] == "customers"
        assert patched["is_living_data"] is False

        # Stats
        stats_resp = await client.get("/api/v1/org-context/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total"] == 1
        assert any(c["category"] == "customers" for c in stats["by_category"])

        # Delete
        del_resp = await client.delete(f"/api/v1/org-context/{file_id}")
        assert del_resp.status_code == 204

        # Confirm 404 after delete
        gone = await client.get(f"/api/v1/org-context/{file_id}")
        assert gone.status_code == 404


# ---------------------------------------------------------------------------
# Member-role restrictions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_cannot_upload(env_member):
    async with AsyncClient(
        transport=ASGITransport(app=env_member["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("x.md", b"text", "text/markdown")},
            data={"category": "other"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_delete(env_member):
    # Seed a file directly via the maker
    file_id = uuid4()
    async with env_member["maker"]() as session:
        session.add(
            OrgContextFile(
                id=file_id,
                organization_id=ORG_ID,
                filename="x.md",
                category="other",
                visibility="shared",
            )
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=env_member["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.delete(f"/api/v1/org-context/{file_id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Visibility scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_cannot_see_private_file_uploaded_by_other_user(env_member):
    """A member should NOT see a private file uploaded by someone else."""
    other_user = uuid4()
    private_id = uuid4()
    shared_id = uuid4()
    async with env_member["maker"]() as session:
        session.add(
            OrgContextFile(
                id=private_id,
                organization_id=ORG_ID,
                filename="private.md",
                category="prospects",
                visibility="private",
                uploaded_by_user_id=other_user,
            )
        )
        session.add(
            OrgContextFile(
                id=shared_id,
                organization_id=ORG_ID,
                filename="shared.md",
                category="prospects",
                visibility="shared",
                uploaded_by_user_id=other_user,
            )
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=env_member["app"]),
        base_url="http://test",
    ) as client:
        list_resp = await client.get("/api/v1/org-context")
        assert list_resp.status_code == 200
        ids = [item["id"] for item in list_resp.json()]
        assert str(shared_id) in ids
        assert str(private_id) not in ids

        # Direct GET on private file should also 404 (not 403 — same shape
        # as the not-found case to avoid leaking existence)
        gone = await client.get(f"/api/v1/org-context/{private_id}")
        assert gone.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_see_all_visibility(env_admin):
    """Admins see everything regardless of visibility, including files
    uploaded by other users."""
    other_user = uuid4()
    private_id = uuid4()
    async with env_admin["maker"]() as session:
        session.add(
            OrgContextFile(
                id=private_id,
                organization_id=ORG_ID,
                filename="private.md",
                category="contracts",
                visibility="private",
                uploaded_by_user_id=other_user,
            )
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        list_resp = await client.get("/api/v1/org-context")
        assert list_resp.status_code == 200
        ids = [item["id"] for item in list_resp.json()]
        assert str(private_id) in ids

        get_resp = await client.get(f"/api/v1/org-context/{private_id}")
        assert get_resp.status_code == 200


# ---------------------------------------------------------------------------
# Org isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_other_org_files_invisible(env_admin):
    """Files belonging to another organization must NOT appear in this
    org's list, and a direct GET must 404."""
    foreign_id = uuid4()
    async with env_admin["maker"]() as session:
        # Foreign org row exists in fixtures-as-data; we just need a file
        # tagged with a different organization_id
        session.add(
            OrgContextFile(
                id=foreign_id,
                organization_id=OTHER_ORG_ID,
                filename="foreign.md",
                category="other",
                visibility="shared",
            )
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        list_resp = await client.get("/api/v1/org-context")
        assert list_resp.status_code == 200
        assert all(item["id"] != str(foreign_id) for item in list_resp.json())

        gone = await client.get(f"/api/v1/org-context/{foreign_id}")
        assert gone.status_code == 404


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_visibility_rejected(env_admin):
    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("x.md", b"text", "text/markdown")},
            data={"visibility": "team"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unsupported_content_type_rejected(env_admin):
    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("evil.exe", b"\x00\x01\x02", "application/octet-stream")},
        )
        assert resp.status_code == 415


@pytest.mark.asyncio
async def test_empty_extraction_returns_422(env_admin, monkeypatch):
    """A scanned PDF that yields no extractable text should 422 — we
    refuse to persist an unsearchable row."""

    async def _empty_intake(**kwargs):
        return {"extracted_text": "", "filename": "x", "content_type": "x"}

    monkeypatch.setattr("app.api.org_context.process_document", _empty_intake)

    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("scanned.pdf", b"%PDF-1.4 binary", "application/pdf")},
        )
        assert resp.status_code == 422
        assert "extract" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_embedding_failure_surfaces_502(env_admin, monkeypatch):
    """When OpenRouter is down or BYOK key is bad, the upload returns 502
    instead of silently storing a half-built row."""

    async def _bad_embedding(content, org_id):
        raise RuntimeError("upstream OpenRouter 401")

    monkeypatch.setattr("app.api.org_context.get_embedding", _bad_embedding)

    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("x.md", b"hello world", "text/markdown")},
        )
        assert resp.status_code == 502
        assert "embedding" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_redaction_level_routes_by_category(env_admin):
    """Per-category redaction policy (Option C). MODERATE-level categories
    (prospects, customers, deployments, pricing) must preserve PII like
    phones and in-body emails — that's the data the agent needs to
    ground recommendations. STRICT-level categories (regulations, brand,
    contracts, rules-of-engagement, other) strip them."""
    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        # Both files contain a phone number. Different category → different
        # redaction level → different outcome.
        body = "Joe Owner — call him at 780-555-1234 for next steps."

        # Prospects = MODERATE → phone survives (signal, not PII leak)
        prospects_resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("prospects.md", body.encode(), "text/markdown")},
            data={"category": "prospects"},
        )
        assert prospects_resp.status_code == 201, prospects_resp.text
        prospects_id = prospects_resp.json()["id"]

        # Contracts = STRICT → phone gets stripped (likely accidental)
        contracts_resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("contract.md", body.encode(), "text/markdown")},
            data={"category": "contracts"},
        )
        assert contracts_resp.status_code == 201, contracts_resp.text
        contracts_id = contracts_resp.json()["id"]

        prospects_body = (
            await client.get(f"/api/v1/org-context/{prospects_id}")
        ).json()["extracted_text"]
        contracts_body = (
            await client.get(f"/api/v1/org-context/{contracts_id}")
        ).json()["extracted_text"]

        # Prospects keeps the phone (MODERATE doesn't apply PII patterns)
        assert "780-555-1234" in prospects_body
        # Contracts strips the phone (STRICT does)
        assert "780-555-1234" not in contracts_body
        assert "[REDACTED_PHONE]" in contracts_body


@pytest.mark.asyncio
async def test_redaction_strips_credentials_before_persist(env_admin):
    """A file containing an API key should be persisted with the key
    redacted — agents and embeddings must never see the original. Tests
    the *wiring* of redact_sensitive into the upload pipeline, not the
    pattern coverage (which has its own tests in test_redaction.py)."""
    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        # AWS access key format — matched by `_CREDENTIAL_PATTERNS`
        # (`r"\bAKIA[0-9A-Z]{16}\b"`) which is one of the patterns
        # always-on at MODERATE level and above.
        secret = "AKIAIOSFODNN7EXAMPLE"
        leak_text = f"Our prod AWS key is {secret} — rotate quarterly."
        create_resp = await client.post(
            "/api/v1/org-context",
            files={"file": ("notes.md", leak_text.encode(), "text/markdown")},
        )
        assert create_resp.status_code == 201, create_resp.text
        file_id = create_resp.json()["id"]

        detail = await client.get(f"/api/v1/org-context/{file_id}")
        assert detail.status_code == 200
        body = detail.json()["extracted_text"]
        # Original token must not survive
        assert secret not in body
        # Redaction marker should be there
        assert "[REDACTED" in body


# ---------------------------------------------------------------------------
# Staleness shape
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Agent search endpoint
# ---------------------------------------------------------------------------


def _build_agent_app(
    maker: async_sessionmaker[AsyncSession],
    org_id: Any,
    *,
    flag_on: bool = True,
):
    """Build a FastAPI app for the agent search router with the agent
    auth + feature-flag check stubbed to a known-good org."""
    from dataclasses import dataclass
    from app.api.agent_org_context import router as agent_router
    from app.core.agent_auth import get_agent_auth_context

    @dataclass
    class _StubAgent:
        id: Any
        name: str
        board_id: Any

    @dataclass
    class _StubCtx:
        actor_type: str
        agent: Any

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(agent_router)
    app.include_router(api_v1)

    async def _override_session():
        async with maker() as session:
            yield session

    async def _override_agent_ctx() -> Any:
        return _StubCtx(
            actor_type="agent",
            agent=_StubAgent(id=uuid4(), name="test-agent", board_id=uuid4()),
        )

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_agent_auth_context] = _override_agent_ctx
    return app


async def _seed_agent_test_files(maker, org_id: Any) -> dict[str, Any]:
    """Seed a shared file (with embedding) and a private file (with
    embedding) on the same org. Used by agent-search visibility tests."""
    shared_id = uuid4()
    private_id = uuid4()
    async with maker() as session:
        session.add(
            OrgContextFile(
                id=shared_id,
                organization_id=org_id,
                filename="shared-icp.md",
                category="prospects",
                visibility="shared",
                extracted_text="ICP definition for auto dealers.",
                embedding=FAKE_EMBEDDING,
            )
        )
        session.add(
            OrgContextFile(
                id=private_id,
                organization_id=org_id,
                filename="private-confidential.md",
                category="contracts",
                visibility="private",
                extracted_text="Confidential pricing terms.",
                embedding=FAKE_EMBEDDING,
            )
        )
        await session.commit()
    return {"shared_id": shared_id, "private_id": private_id}


@pytest.mark.asyncio
async def test_agent_search_endpoint_passes_correct_args(env_admin, monkeypatch):
    """Validates the endpoint plumbing — auth, flag check, dispatch to
    the search service with ``include_private=False``. The pgvector
    cosine SQL is exercised against a real Postgres in integration tests
    (not in this SQLite unit-test suite).

    Specifically asserts:
    - The endpoint reaches the service layer with ``include_private=False``
      (so the visibility filter is applied — this is the security-critical
      contract the agent surface promises).
    - Each returned hit carries the staleness metadata (filename, age,
      is_living_data, snippet) the citing skill needs.
    """
    captured: dict[str, Any] = {}

    async def _fake_search(*, org_id, query, limit, category_filter, include_private):
        captured["org_id"] = org_id
        captured["query"] = query
        captured["limit"] = limit
        captured["category_filter"] = category_filter
        captured["include_private"] = include_private
        return [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "filename": "shared-icp.md",
                "category": "prospects",
                "source": None,
                "visibility": "shared",
                "is_living_data": True,
                "snippet": "ICP definition for auto dealers.",
                "uploaded_at": "2026-04-27T12:00:00",
                "last_updated": "2026-04-27T12:00:00",
                "similarity": 0.92,
            },
        ]

    # Patch at the module the endpoint imports from
    monkeypatch.setattr("app.services.embedding.search_org_context", _fake_search)

    from app.api import agent_org_context as agent_mod

    async def _stub_resolve(agent_ctx, session):
        return ORG_ID

    monkeypatch.setattr(agent_mod, "_resolve_org_id", _stub_resolve)

    app = _build_agent_app(env_admin["maker"], ORG_ID)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/agent/org-context/search",
            json={"query": "ICP for auto dealers", "limit": 10},
        )
        assert resp.status_code == 200, resp.text

    # Service was called with the security-critical kwargs
    assert captured["include_private"] is False, (
        "Agent endpoint must NEVER include private files in search results"
    )
    assert captured["query"] == "ICP for auto dealers"
    assert captured["limit"] == 10
    assert captured["org_id"] == ORG_ID

    # Response shape carries the staleness metadata
    hits = resp.json()
    assert len(hits) == 1
    hit = hits[0]
    for required in ("filename", "is_living_data", "uploaded_at", "snippet", "similarity"):
        assert required in hit


@pytest.mark.asyncio
async def test_agent_search_blocked_when_flag_off(env_flag_off, monkeypatch):
    """When org_context flag is off, agent search returns 403 — even with
    a valid agent token."""
    from app.api import agent_org_context as agent_mod

    async def _stub_resolve(agent_ctx, session):
        return ORG_ID

    monkeypatch.setattr(agent_mod, "_resolve_org_id", _stub_resolve)

    app = _build_agent_app(env_flag_off["maker"], ORG_ID)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/agent/org-context/search",
            json={"query": "anything"},
        )
        assert resp.status_code == 403
        assert "org_context" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Staleness shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_age_days_reflects_uploaded_at(env_admin):
    """A row uploaded 90 days ago should report age_days >= 90."""
    file_id = uuid4()
    backdated = utcnow() - timedelta(days=92)
    async with env_admin["maker"]() as session:
        session.add(
            OrgContextFile(
                id=file_id,
                organization_id=ORG_ID,
                filename="old.md",
                category="regulations",
                visibility="shared",
                uploaded_at=backdated,
                last_updated=backdated,
            )
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=env_admin["app"]),
        base_url="http://test",
    ) as client:
        resp = await client.get(f"/api/v1/org-context/{file_id}")
        assert resp.status_code == 200
        assert resp.json()["age_days"] >= 90
