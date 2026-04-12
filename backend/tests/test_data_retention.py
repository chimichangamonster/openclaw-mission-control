# ruff: noqa: INP001
"""Tests for data retention service — cleanup logic, defaults, per-org overrides."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from app.core.time import utcnow  # noqa: E402

# Import all models we test so SQLModel.metadata.create_all creates their tables
from app.models.activity_events import ActivityEvent  # noqa: E402, F401
from app.models.audit_log import AuditLog  # noqa: E402, F401
from app.models.board_webhook_payloads import BoardWebhookPayload  # noqa: E402, F401
from app.models.budget import DailyAgentSpend  # noqa: E402, F401
from app.models.email_messages import EmailMessage  # noqa: E402, F401
from app.services.data_retention import (  # noqa: E402
    DEFAULT_RETENTION,
    _cleanup_table,
)

# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine):
    session_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session


# ---------------------------------------------------------------------------
# Default retention values
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_activity_retention(self):
        assert DEFAULT_RETENTION["activity_retention_days"] == 90

    def test_default_email_retention(self):
        assert DEFAULT_RETENTION["email_retention_days"] == 180

    def test_default_audit_retention(self):
        assert DEFAULT_RETENTION["audit_retention_days"] == 365

    def test_default_webhook_retention(self):
        assert DEFAULT_RETENTION["webhook_retention_days"] == 30

    def test_default_spend_retention(self):
        assert DEFAULT_RETENTION["spend_retention_days"] == 365


# ---------------------------------------------------------------------------
# Per-org retention in data_policy
# ---------------------------------------------------------------------------


class TestOrgRetentionPolicy:
    def test_retention_fields_in_data_policy(self):
        """Retention settings can be stored in data_policy_json."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        policy["email_retention_days"] = 90
        policy["audit_retention_days"] = 730
        settings.data_policy_json = json.dumps(policy)

        loaded = settings.data_policy
        assert loaded["email_retention_days"] == 90
        assert loaded["audit_retention_days"] == 730
        # Original fields preserved
        assert loaded["redaction_level"] == "moderate"

    def test_zero_retention_means_keep_forever(self):
        """Setting retention to 0 should keep data forever."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        policy["email_retention_days"] = 0
        settings.data_policy_json = json.dumps(policy)
        assert settings.data_policy["email_retention_days"] == 0


# ---------------------------------------------------------------------------
# Cleanup table function
# ---------------------------------------------------------------------------


class TestCleanupTable:
    @pytest.mark.asyncio()
    async def test_zero_cutoff_skips_cleanup(self, db_session):
        """cutoff_days=0 means no deletion (keep forever)."""
        deleted = await _cleanup_table(
            table_name="activity_events",
            timestamp_col="created_at",
            cutoff_days=0,
        )
        assert deleted == 0

    @pytest.mark.asyncio()
    async def test_deletes_old_activity_events(self, db_engine):
        """Rows older than cutoff are deleted."""
        test_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        old_time = utcnow() - timedelta(days=100)
        new_time = utcnow() - timedelta(days=10)

        async with test_maker() as session:
            for i in range(3):
                session.add(
                    ActivityEvent(
                        id=uuid4(),
                        event_type="test.old",
                        message=f"Old event {i}",
                        created_at=old_time,
                    )
                )
            for i in range(2):
                session.add(
                    ActivityEvent(
                        id=uuid4(),
                        event_type="test.new",
                        message=f"New event {i}",
                        created_at=new_time,
                    )
                )
            await session.commit()

        # Verify 5 total
        async with test_maker() as session:
            result = await session.execute(select(ActivityEvent))
            assert len(result.scalars().all()) == 5

        with patch("app.services.data_retention.async_session_maker", test_maker):
            deleted = await _cleanup_table(
                table_name="activity_events",
                timestamp_col="created_at",
                cutoff_days=90,
            )

        assert deleted == 3

        async with test_maker() as session:
            result = await session.execute(select(ActivityEvent))
            remaining = result.scalars().all()
            assert len(remaining) == 2
            assert all(e.event_type == "test.new" for e in remaining)

    @pytest.mark.asyncio()
    async def test_keeps_recent_rows(self, db_engine):
        """Rows within the retention window are kept."""
        test_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        recent_time = utcnow() - timedelta(days=5)

        async with test_maker() as session:
            for i in range(3):
                session.add(
                    ActivityEvent(
                        id=uuid4(),
                        event_type="test.recent",
                        message=f"Recent {i}",
                        created_at=recent_time,
                    )
                )
            await session.commit()

        with patch("app.services.data_retention.async_session_maker", test_maker):
            deleted = await _cleanup_table(
                table_name="activity_events",
                timestamp_col="created_at",
                cutoff_days=90,
            )

        assert deleted == 0

    @pytest.mark.asyncio()
    async def test_org_scoped_cleanup(self, db_engine):
        """Org-scoped cleanup only deletes rows for the specified org."""
        test_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        org_a = uuid4()
        org_b = uuid4()
        old_time = utcnow() - timedelta(days=400)

        async with test_maker() as session:
            session.add(
                AuditLog(
                    id=uuid4(),
                    organization_id=org_a,
                    action="test",
                    resource_type="test",
                    created_at=old_time,
                )
            )
            session.add(
                AuditLog(
                    id=uuid4(),
                    organization_id=org_b,
                    action="test",
                    resource_type="test",
                    created_at=old_time,
                )
            )
            await session.commit()

        with patch("app.services.data_retention.async_session_maker", test_maker):
            deleted = await _cleanup_table(
                table_name="audit_logs",
                timestamp_col="created_at",
                cutoff_days=365,
                org_filter="organization_id",
                org_id=str(org_a),
            )

        assert deleted == 1

        async with test_maker() as session:
            result = await session.execute(select(AuditLog))
            remaining = result.scalars().all()
            assert len(remaining) == 1
            assert remaining[0].organization_id == org_b


# ---------------------------------------------------------------------------
# DataPolicyUpdate schema validation
# ---------------------------------------------------------------------------


class TestDataPolicyUpdateSchema:
    def test_retention_fields_accepted(self):
        from app.api.organization_settings import DataPolicyUpdate

        policy = DataPolicyUpdate(
            activity_retention_days=60,
            email_retention_days=90,
            audit_retention_days=730,
            webhook_retention_days=14,
            spend_retention_days=180,
        )
        assert policy.activity_retention_days == 60
        assert policy.email_retention_days == 90

    def test_retention_fields_optional(self):
        from app.api.organization_settings import DataPolicyUpdate

        policy = DataPolicyUpdate()
        assert policy.activity_retention_days is None
        assert policy.email_retention_days is None

    def test_mixed_update(self):
        """Can update retention and redaction together."""
        from app.api.organization_settings import DataPolicyUpdate

        policy = DataPolicyUpdate(
            redaction_level="strict",
            email_retention_days=30,
        )
        assert policy.redaction_level == "strict"
        assert policy.email_retention_days == 30
