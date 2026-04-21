# ruff: noqa: INP001
"""E2E tests for the /personal-bookkeeping API.

Covers feature flag + slug gating, month CRUD + lock, statement upload
(encrypted at rest, idempotent re-import), transaction edit + totals
recompute, promote-to-rule, vendor-rule CRUD, and org isolation.

Follows the in-memory SQLite + dependency-override harness from
test_e2e_feature_flows.py.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    check_org_rate_limit,
    get_session,
    require_org_from_actor,
    require_org_member,
)
from app.api.personal_bookkeeping import require_personal_org, router as pbk_router
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.models.organizations import Organization
from app.models.personal_bookkeeping import (
    PersonalReconciliationMonth,
    PersonalTransaction,
    PersonalVendorRule,
)
from app.models.users import User
from app.services.organizations import OrganizationContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PERSONAL_ORG_ID = uuid4()
OTHER_ORG_ID = uuid4()
USER_ID = uuid4()


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
    session: AsyncSession, *, personal_flag_on: bool = True, slug: str = "personal"
) -> OrganizationContext:
    from app.core.time import utcnow

    now = utcnow()
    org = Organization(
        id=PERSONAL_ORG_ID,
        name="Personal" if slug == "personal" else "Other Org",
        slug=slug,
        created_at=now,
        updated_at=now,
    )
    session.add(org)

    user = User(
        id=USER_ID,
        clerk_user_id="pbk-test-clerk",
        email="pbk@test.com",
        name="PBK Tester",
        active_organization_id=PERSONAL_ORG_ID,
    )
    session.add(user)

    member = OrganizationMember(
        id=uuid4(),
        organization_id=PERSONAL_ORG_ID,
        user_id=USER_ID,
        role="owner",
        all_boards_read=True,
        all_boards_write=True,
        created_at=now,
        updated_at=now,
    )
    session.add(member)

    flags = dict(DEFAULT_FEATURE_FLAGS)
    flags["personal_bookkeeping"] = personal_flag_on
    settings = OrganizationSettings(
        id=uuid4(),
        organization_id=PERSONAL_ORG_ID,
        feature_flags_json=json.dumps(flags),
    )
    session.add(settings)
    await session.commit()
    return OrganizationContext(organization=org, member=member)


def _build_app(
    maker: async_sessionmaker[AsyncSession],
    org_ctx: OrganizationContext,
    *,
    slug_check_enabled: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(pbk_router)
    app.include_router(api_v1)

    async def _override_session():
        async with maker() as session:
            yield session

    async def _override_org() -> OrganizationContext:
        return org_ctx

    async def _override_rate_limit() -> None:
        return None

    async def _override_slug() -> OrganizationContext:
        if slug_check_enabled and org_ctx.organization.slug != "personal":
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Personal only.")
        return org_ctx

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_org_member] = _override_org
    app.dependency_overrides[require_org_from_actor] = _override_org
    app.dependency_overrides[check_org_rate_limit] = _override_rate_limit
    app.dependency_overrides[require_personal_org] = _override_slug
    return app


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch):
    # Point statement storage at a tmpdir and give encryption a test key
    monkeypatch.setenv("ENCRYPTION_KEY", "test-master-key-for-personal-bookkeeping-x")
    from app.core.config import settings as app_settings
    from app.core import encryption as enc_module

    app_settings.personal_bookkeeping_statements_root = str(tmp_path)
    app_settings.encryption_key = "test-master-key-for-personal-bookkeeping-x"
    enc_module.reset_cache()

    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        ctx = await _seed(session)

    app = _build_app(maker, ctx)

    yield {
        "app": app,
        "maker": maker,
        "ctx": ctx,
        "tmp_path": tmp_path,
    }

    await engine.dispose()
    enc_module.reset_cache()


# ---------------------------------------------------------------------------
# Sample statement payloads
# ---------------------------------------------------------------------------


TD_CSV = (
    '"2026-05-03","VERCEL INC","29.00","","1000.00"\n'
    '"2026-05-05","E-TRANSFER ***abc","","500.00","1500.00"\n'
    '"2026-05-10","UBER EATS","45.12","","1454.88"\n'
)

TD_CSV_OVERLAP = TD_CSV + '"2026-05-15","OPENROUTER","15.00","","1439.88"\n'




# ===========================================================================
# Gating tests
# ===========================================================================


class TestFeatureFlagGating:
    @pytest.mark.asyncio
    async def test_flag_off_returns_403(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "test-key-x")
        from app.core.config import settings as app_settings
        from app.core import encryption as enc_module

        app_settings.personal_bookkeeping_statements_root = str(tmp_path)
        app_settings.encryption_key = "test-key-x"
        enc_module.reset_cache()

        engine = await _make_engine()
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            ctx = await _seed(session, personal_flag_on=False)

        app = _build_app(maker, ctx)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.get("/api/v1/personal-bookkeeping/months")
            assert resp.status_code == 403
            assert "personal_bookkeeping" in resp.json()["detail"]
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_wrong_slug_returns_403(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "test-key-x")
        from app.core.config import settings as app_settings
        from app.core import encryption as enc_module

        app_settings.personal_bookkeeping_statements_root = str(tmp_path)
        app_settings.encryption_key = "test-key-x"
        enc_module.reset_cache()

        engine = await _make_engine()
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            ctx = await _seed(session, slug="waste-gurus")

        app = _build_app(maker, ctx)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            resp = await c.get("/api/v1/personal-bookkeeping/months")
            assert resp.status_code == 403
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_flag_on_and_personal_slug_returns_200(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            resp = await c.get("/api/v1/personal-bookkeeping/months")
            assert resp.status_code == 200
            assert resp.json() == []


# ===========================================================================
# Month CRUD + lock
# ===========================================================================


class TestMonths:
    @pytest.mark.asyncio
    async def test_create_is_idempotent(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            r1 = await c.post(
                "/api/v1/personal-bookkeeping/months", json={"period": "2026-05"}
            )
            r2 = await c.post(
                "/api/v1/personal-bookkeeping/months", json={"period": "2026-05"}
            )
            assert r1.status_code == 201
            assert r2.status_code == 201
            assert r1.json()["id"] == r2.json()["id"]

    @pytest.mark.asyncio
    async def test_invalid_period_rejected(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/api/v1/personal-bookkeeping/months", json={"period": "bad"}
            )
            assert resp.status_code == 422  # pydantic pattern mismatch

    @pytest.mark.asyncio
    async def test_lock_rejects_when_flagged(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            # Upload TD statement which produces 1 income_pending (E-TRANSFER)
            files = {"file": ("td.csv", TD_CSV.encode(), "text/csv")}
            up = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files=files,
            )
            assert up.status_code == 201, up.text
            # At least one flagged line — E-TRANSFER → income_pending
            lock = await c.post("/api/v1/personal-bookkeeping/months/2026-05/lock")
            assert lock.status_code == 409
            assert "flagged" in lock.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_lock_then_double_lock_conflicts(self, env):
        # Create empty month → lock succeeds (zero flagged), second lock 409
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/months", json={"period": "2026-06"}
            )
            r1 = await c.post("/api/v1/personal-bookkeeping/months/2026-06/lock")
            assert r1.status_code == 200
            assert r1.json()["status"] == "locked"

            r2 = await c.post("/api/v1/personal-bookkeeping/months/2026-06/lock")
            assert r2.status_code == 409


# ===========================================================================
# Statement upload + import
# ===========================================================================


class TestStatementUpload:
    @pytest.mark.asyncio
    async def test_td_upload_classifies_and_persists(self, env, tmp_path):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            files = {"file": ("td.csv", TD_CSV.encode(), "text/csv")}
            resp = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files=files,
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["inserted_count"] == 3
            assert body["skipped_count"] == 0
            # VERCEL → business, E-TRANSFER incoming → income_pending, UBER EATS → personal
            assert body["classification_summary"].get("business", 0) >= 1
            assert body["classification_summary"].get("income_pending", 0) >= 1

            # Verify encrypted-on-disk: raw bytes should NOT appear literally
            org_dir = env["tmp_path"] / str(env["ctx"].organization.id)
            files_on_disk = list(org_dir.glob("*.enc"))
            assert len(files_on_disk) == 1
            encrypted = files_on_disk[0].read_bytes()
            assert b"VERCEL" not in encrypted
            assert b"UBER EATS" not in encrypted

            # Decryption round-trips
            from app.core.encryption import decrypt_bytes

            assert b"VERCEL" in decrypt_bytes(encrypted)

    @pytest.mark.asyncio
    async def test_same_file_twice_returns_409(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            files = {"file": ("td.csv", TD_CSV.encode(), "text/csv")}
            r1 = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files=files,
            )
            assert r1.status_code == 201

            files2 = {"file": ("td.csv", TD_CSV.encode(), "text/csv")}
            r2 = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files=files2,
            )
            assert r2.status_code == 409

    @pytest.mark.asyncio
    async def test_overlapping_file_dedups_by_row_hash(self, env):
        """Upload TD_CSV, then a superset — overlap rows get skipped, new row inserted."""
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            r1 = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("td.csv", TD_CSV.encode(), "text/csv")},
            )
            assert r1.json()["inserted_count"] == 3

            r2 = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("td2.csv", TD_CSV_OVERLAP.encode(), "text/csv")},
            )
            assert r2.status_code == 201
            body = r2.json()
            assert body["inserted_count"] == 1  # Only the new OPENROUTER row
            assert body["skipped_count"] == 3

    @pytest.mark.asyncio
    async def test_retention_date_is_tax_year_plus_6(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("td.csv", TD_CSV.encode(), "text/csv")},
            )
            stmts = await c.get("/api/v1/personal-bookkeeping/months/2026-05/statements")
            assert stmts.json()[0]["retention_until"] == "2032-12-31"

    @pytest.mark.asyncio
    async def test_upload_into_locked_month_rejected(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/months", json={"period": "2026-07"}
            )
            await c.post("/api/v1/personal-bookkeeping/months/2026-07/lock")
            resp = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-07/statements",
                data={"source": "TD"},
                files={"file": ("td.csv", TD_CSV.encode(), "text/csv")},
            )
            assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_source_rejected(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "CIBC"},
                files={"file": ("x.csv", b"irrelevant", "text/csv")},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_file_rejected(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("empty.csv", b"", "text/csv")},
            )
            assert resp.status_code == 400


# ===========================================================================
# Transactions + promote-to-rule
# ===========================================================================


class TestTransactions:
    @pytest.mark.asyncio
    async def test_patch_updates_classified_by_and_totals(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("td.csv", TD_CSV.encode(), "text/csv")},
            )
            list_resp = await c.get(
                "/api/v1/personal-bookkeeping/months/2026-05/transactions"
            )
            # Grab the income_pending row
            txns = list_resp.json()
            pending = [t for t in txns if t["bucket"] == "income_pending"]
            assert len(pending) == 1
            txn_id = pending[0]["id"]

            # Reclassify income_pending → business (consulting income)
            patch = await c.patch(
                f"/api/v1/personal-bookkeeping/transactions/{txn_id}",
                json={"bucket": "business", "user_note": "Consulting"},
            )
            assert patch.status_code == 200
            assert patch.json()["bucket"] == "business"
            assert patch.json()["classified_by"] == "user"

            # Month totals should reflect the change: flagged count drops, income rises
            month = await c.get("/api/v1/personal-bookkeeping/months/2026-05")
            mbody = month.json()
            assert mbody["flagged_line_count"] == 0
            assert mbody["business_income"] == 500.0
            # GST informational = 500 / 1.05 * 0.05 ≈ 23.81
            assert abs(mbody["gst_collected_informational"] - 23.81) < 0.01

    @pytest.mark.asyncio
    async def test_patch_rejects_on_locked_month(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("td.csv", TD_CSV.encode(), "text/csv")},
            )
            # Resolve the income_pending so we can lock
            list_resp = await c.get(
                "/api/v1/personal-bookkeeping/months/2026-05/transactions"
            )
            pending_id = [
                t for t in list_resp.json() if t["bucket"] == "income_pending"
            ][0]["id"]
            await c.patch(
                f"/api/v1/personal-bookkeeping/transactions/{pending_id}",
                json={"bucket": "gift"},
            )
            lock = await c.post("/api/v1/personal-bookkeeping/months/2026-05/lock")
            assert lock.status_code == 200

            # Any txn PATCH now rejected
            any_id = list_resp.json()[0]["id"]
            patch = await c.patch(
                f"/api/v1/personal-bookkeeping/transactions/{any_id}",
                json={"user_note": "too late"},
            )
            assert patch.status_code == 409

    @pytest.mark.asyncio
    async def test_promote_to_rule_creates_escaped_pattern(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("td.csv", TD_CSV.encode(), "text/csv")},
            )
            txns = (
                await c.get("/api/v1/personal-bookkeeping/months/2026-05/transactions")
            ).json()
            # Pick the VERCEL txn (already business — promote to cement it)
            vercel = [t for t in txns if "VERCEL" in t["description"]][0]
            resp = await c.post(
                f"/api/v1/personal-bookkeeping/transactions/{vercel['id']}/promote-to-rule",
                json={},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["bucket"] == "business"
            assert body["source_month"] == "2026-05"
            # Pattern should be escaped-literal of VERCEL INC (upper-cased)
            assert "VERCEL\\ INC" in body["pattern"] or "VERCEL INC" in body["pattern"]


# ===========================================================================
# Vendor rules
# ===========================================================================


class TestVendorRules:
    @pytest.mark.asyncio
    async def test_rule_crud_roundtrip(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            # Create
            create = await c.post(
                "/api/v1/personal-bookkeeping/vendor-rules",
                json={
                    "pattern": r"STRIPE",
                    "bucket": "business",
                    "t2125_line": "8871",
                    "category": "Mgmt/Admin",
                    "needs_receipt": True,
                },
            )
            assert create.status_code == 201
            rule_id = create.json()["id"]

            # List
            lst = await c.get("/api/v1/personal-bookkeeping/vendor-rules")
            assert any(r["id"] == rule_id for r in lst.json())

            # Deactivate
            patch = await c.patch(
                f"/api/v1/personal-bookkeeping/vendor-rules/{rule_id}",
                json={"active": False},
            )
            assert patch.status_code == 200
            assert patch.json()["active"] is False

            # Filter active=True no longer returns it
            active_lst = await c.get(
                "/api/v1/personal-bookkeeping/vendor-rules?active=true"
            )
            assert not any(r["id"] == rule_id for r in active_lst.json())

    @pytest.mark.asyncio
    async def test_rule_bad_regex_rejected(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/api/v1/personal-bookkeeping/vendor-rules",
                json={"pattern": "[unclosed", "bucket": "business"},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_rule_bad_bucket_rejected(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            resp = await c.post(
                "/api/v1/personal-bookkeeping/vendor-rules",
                json={"pattern": "FOO", "bucket": "not-a-bucket"},
            )
            assert resp.status_code == 400


# ===========================================================================
# Org isolation (direct DB check — no second-org HTTP surface in these tests)
# ===========================================================================


class TestOrgIsolation:
    @pytest.mark.asyncio
    async def test_personal_data_scoped_to_org(self, env):
        """Rows inserted for the personal org must carry its organization_id."""
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/months/2026-05/statements",
                data={"source": "TD"},
                files={"file": ("td.csv", TD_CSV.encode(), "text/csv")},
            )

        async with env["maker"]() as session:
            months = (
                await session.execute(select(PersonalReconciliationMonth))
            ).scalars().all()
            txns = (
                await session.execute(select(PersonalTransaction))
            ).scalars().all()
            for m in months:
                assert m.organization_id == PERSONAL_ORG_ID
            for t in txns:
                assert t.organization_id == PERSONAL_ORG_ID

    @pytest.mark.asyncio
    async def test_vendor_rule_scoped_to_org(self, env):
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://t"
        ) as c:
            await c.post(
                "/api/v1/personal-bookkeeping/vendor-rules",
                json={"pattern": "STRIPE", "bucket": "business"},
            )

        async with env["maker"]() as session:
            rules = (
                await session.execute(select(PersonalVendorRule))
            ).scalars().all()
            assert len(rules) == 1
            assert rules[0].organization_id == PERSONAL_ORG_ID
