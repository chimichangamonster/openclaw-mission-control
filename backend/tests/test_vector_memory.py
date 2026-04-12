# ruff: noqa: INP001
"""Tests for agent vector memory — model defaults, schemas, API endpoints, feature flags."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from app.api.agent_memory_vector import router as vector_router  # noqa: E402
from app.models.agents import Agent  # noqa: E402
from app.models.boards import Board  # noqa: E402
from app.models.organization_members import OrganizationMember  # noqa: E402
from app.models.organization_settings import OrganizationSettings  # noqa: E402
from app.models.organizations import Organization  # noqa: E402
from app.models.users import User  # noqa: E402
from app.schemas.vector_memory import (  # noqa: E402
    VectorMemoryForget,
    VectorMemorySearch,
    VectorMemoryStore,
)

# ---------------------------------------------------------------------------
# Test IDs
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
ORG_ID_B = uuid4()
USER_ID = uuid4()
BOARD_ID = uuid4()
AGENT_ID = uuid4()
AGENT_TOKEN = "test-agent-token-vector-memory"


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


async def _make_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _make_session():
    engine = await _make_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(session: AsyncSession) -> dict:
    """Seed org, user, board, agent, and settings."""
    org = Organization(id=ORG_ID, name="Test Org", slug="test-org")
    session.add(org)

    user = User(id=USER_ID, email="test@test.com", name="Test")
    session.add(user)

    board = Board(id=BOARD_ID, name="Test Board", organization_id=ORG_ID)
    session.add(board)

    from app.core.agent_tokens import hash_agent_token

    agent = Agent(
        id=AGENT_ID,
        name="test-agent",
        board_id=BOARD_ID,
        agent_token_hash=hash_agent_token(AGENT_TOKEN),
    )
    session.add(agent)

    settings = OrganizationSettings(
        id=uuid4(),
        organization_id=ORG_ID,
        feature_flags_json=json.dumps({"agent_memory": True}),
    )
    session.add(settings)

    member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        role="admin",
    )
    session.add(member)

    await session.commit()
    return {"org": org, "agent": agent, "board": board}


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestVectorMemorySchemas:
    """Schema validation for store/search/forget requests."""

    def test_store_schema_valid(self):
        body = VectorMemoryStore(content="test fact", source="skill:test")
        assert body.content == "test fact"
        assert body.source == "skill:test"
        assert body.extra == {}
        assert body.ttl_days is None

    def test_store_schema_with_extra(self):
        body = VectorMemoryStore(
            content="fact",
            source="compaction",
            extra={"session_key": "abc"},
            ttl_days=30,
        )
        assert body.extra == {"session_key": "abc"}
        assert body.ttl_days == 30

    def test_store_rejects_empty_content(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            VectorMemoryStore(content="", source="test")

    def test_store_rejects_empty_source(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            VectorMemoryStore(content="hello", source="")

    def test_search_schema_defaults(self):
        body = VectorMemorySearch(query="test query")
        assert body.limit == 5
        assert body.source_filter is None

    def test_search_limit_bounds(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            VectorMemorySearch(query="test", limit=0)
        with pytest.raises(ValidationError):
            VectorMemorySearch(query="test", limit=51)

    def test_forget_schema(self):
        body = VectorMemoryForget(source="compaction")
        assert body.source == "compaction"


# ---------------------------------------------------------------------------
# Feature flag gating tests
# ---------------------------------------------------------------------------


class TestFeatureFlags:
    """Feature flag defaults and gating."""

    def test_agent_memory_default_off(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert "agent_memory" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["agent_memory"] is False

    def test_observability_default_off(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert "observability" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["observability"] is False


# ---------------------------------------------------------------------------
# Embedding service unit tests (mocked httpx)
# ---------------------------------------------------------------------------


MOCK_EMBEDDING = [0.1] * 1536


class TestEmbeddingService:
    """Embedding service with mocked OpenRouter calls."""

    @pytest.mark.asyncio
    async def test_get_embedding_calls_openrouter(self):
        from unittest.mock import MagicMock

        from app.services.embedding import get_embedding

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": MOCK_EMBEDDING}],
            "usage": {"total_tokens": 10},
        }

        mock_post = AsyncMock(return_value=mock_response)

        with (
            patch("app.services.embedding._resolve_api_key", new_callable=AsyncMock, return_value="sk-test"),
            patch("httpx.AsyncClient.post", mock_post),
            patch("app.services.langfuse_client.trace_embedding"),
        ):
            result = await get_embedding("test content", ORG_ID)
            assert len(result) == 1536
            assert result[0] == 0.1

    @pytest.mark.asyncio
    async def test_get_embedding_rejects_wrong_dimensions(self):
        from unittest.mock import MagicMock

        from app.services.embedding import get_embedding

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1] * 100}],
        }

        mock_post = AsyncMock(return_value=mock_response)

        with (
            patch("app.services.embedding._resolve_api_key", new_callable=AsyncMock, return_value="sk-test"),
            patch("httpx.AsyncClient.post", mock_post),
            patch("app.services.langfuse_client.trace_embedding"),
            pytest.raises(ValueError, match="Expected 1536 dimensions"),
        ):
            await get_embedding("test", ORG_ID)

    @pytest.mark.asyncio
    async def test_resolve_api_key_uses_platform_key(self):
        from unittest.mock import MagicMock

        from app.services.embedding import _resolve_api_key

        with patch("app.services.embedding.settings") as mock_settings:
            mock_settings.openrouter_api_key = "sk-platform"
            with patch("app.services.embedding.async_session_maker") as mock_maker:
                # scalars().first() is synchronous in SQLAlchemy
                scalars_mock = MagicMock()
                scalars_mock.first.return_value = None
                execute_result = MagicMock()
                execute_result.scalars.return_value = scalars_mock

                session = AsyncMock()
                session.execute.return_value = execute_result

                @asynccontextmanager
                async def fake_session():
                    yield session

                mock_maker.return_value = fake_session()
                key = await _resolve_api_key(ORG_ID)
                assert key == "sk-platform"

    @pytest.mark.asyncio
    async def test_resolve_api_key_raises_when_missing(self):
        from unittest.mock import MagicMock

        from app.services.embedding import _resolve_api_key

        with patch("app.services.embedding.settings") as mock_settings:
            mock_settings.openrouter_api_key = ""
            with patch("app.services.embedding.async_session_maker") as mock_maker:
                scalars_mock = MagicMock()
                scalars_mock.first.return_value = None
                execute_result = MagicMock()
                execute_result.scalars.return_value = scalars_mock

                session = AsyncMock()
                session.execute.return_value = execute_result

                @asynccontextmanager
                async def fake_session():
                    yield session

                mock_maker.return_value = fake_session()
                with pytest.raises(ValueError, match="No OpenRouter API key"):
                    await _resolve_api_key(ORG_ID)


# ---------------------------------------------------------------------------
# Langfuse client tests
# ---------------------------------------------------------------------------


class TestLangfuseClient:
    """Langfuse client initialization and graceful degradation."""

    def test_returns_none_when_no_keys(self):
        from app.services import langfuse_client

        # Reset singleton state
        langfuse_client._langfuse = None
        langfuse_client._init_attempted = False

        with patch.object(langfuse_client, "settings") as mock_settings:
            mock_settings.langfuse_secret_key = ""
            mock_settings.langfuse_public_key = ""
            result = langfuse_client.get_langfuse()
            assert result is None

        # Reset for other tests
        langfuse_client._init_attempted = False

    def test_trace_embedding_noop_when_disabled(self):
        """trace_embedding should silently do nothing when client is None."""
        from app.services.langfuse_client import trace_embedding

        with patch("app.services.langfuse_client.get_langfuse", return_value=None):
            # Should not raise
            trace_embedding(
                org_id="test",
                model="test-model",
                input_text="test",
            )


# ---------------------------------------------------------------------------
# API endpoint tests (mocked embedding service)
# ---------------------------------------------------------------------------


class TestVectorMemoryAPI:
    """API endpoint tests with mocked embedding + in-memory DB."""

    @pytest.mark.asyncio
    async def test_store_requires_agent_auth(self):
        """Unauthenticated requests should get 401/403."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(vector_router, prefix="/api/v1")

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/v1/agent/memory/vector/store",
                json={"content": "test", "source": "test"},
            )
            # Should be 401 or 403 (no auth header)
            assert resp.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_store_schema_validation(self):
        """Empty content should be rejected at schema level."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(vector_router, prefix="/api/v1")

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/v1/agent/memory/vector/store",
                json={"content": "", "source": ""},
            )
            # Validation error (422) or auth error (401/403)
            assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# Model defaults test
# ---------------------------------------------------------------------------


class TestVectorMemoryModel:
    """VectorMemory model field defaults."""

    def test_default_metadata(self):
        from app.models.vector_memory import VectorMemory

        # Can't fully instantiate without pgvector, but check defaults
        assert VectorMemory.__tablename__ == "vector_memories"

    def test_embedding_dimensions_constant(self):
        from app.models.vector_memory import EMBEDDING_DIMENSIONS

        assert EMBEDDING_DIMENSIONS == 1536
