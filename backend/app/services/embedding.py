"""Embedding service — semantic vector generation + vector memory CRUD.

Uses OpenRouter embeddings API (text-embedding-3-small) to generate vectors.
Resolves API key per org: BYOK OpenRouter > platform OpenRouter key.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlmodel import select

from app.core.config import settings
from app.core.encryption import decrypt_token
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.organization_settings import OrganizationSettings
from app.models.vector_memory import EMBEDDING_DIMENSIONS, VectorMemory

logger = get_logger(__name__)

OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
EMBEDDING_MODEL = "openai/text-embedding-3-small"


async def _resolve_api_key(org_id: UUID) -> str:
    """Resolve OpenRouter API key: BYOK > platform key."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        org_settings = result.scalars().first()

    if org_settings and org_settings.openrouter_api_key_encrypted:
        try:
            return decrypt_token(org_settings.openrouter_api_key_encrypted)
        except Exception:
            logger.warning("embedding.byok_key_decrypt_failed org_id=%s", org_id)

    if settings.openrouter_api_key:
        return settings.openrouter_api_key

    msg = f"No OpenRouter API key available for org {org_id}"
    raise ValueError(msg)


async def get_embedding(content: str, org_id: UUID) -> list[float]:
    """Generate an embedding vector for the given text via OpenRouter."""
    api_key = await _resolve_api_key(org_id)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENROUTER_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": EMBEDDING_MODEL, "input": content},
        )
        resp.raise_for_status()
        data = resp.json()

    embedding: list[float] = data["data"][0]["embedding"]
    if len(embedding) != EMBEDDING_DIMENSIONS:
        msg = f"Expected {EMBEDDING_DIMENSIONS} dimensions, got {len(embedding)}"
        raise ValueError(msg)

    # Trace to Langfuse if observability is configured
    from app.services.langfuse_client import trace_embedding as _trace

    _trace(
        org_id=str(org_id),
        model=EMBEDDING_MODEL,
        input_text=content,
        token_count=data.get("usage", {}).get("total_tokens"),
    )

    return embedding


async def store_memory(
    org_id: UUID,
    content: str,
    source: str,
    *,
    agent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ttl_days: int | None = None,
) -> VectorMemory:
    """Embed text and persist to vector_memories table."""
    embedding = await get_embedding(content, org_id)

    expires_at = None
    if ttl_days:
        expires_at = utcnow() + timedelta(days=ttl_days)

    memory = VectorMemory(
        organization_id=org_id,
        content=content,
        embedding=embedding,
        source=source,
        agent_id=agent_id,
        metadata_json=json.dumps(metadata or {}),
        expires_at=expires_at,
    )

    async with async_session_maker() as session:
        session.add(memory)
        await session.commit()
        await session.refresh(memory)

    logger.info(
        "embedding.stored org_id=%s source=%s id=%s",
        org_id,
        source,
        memory.id,
    )
    return memory


async def search_memory(
    org_id: UUID,
    query: str,
    *,
    limit: int = 5,
    source_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search: embed query, find nearest neighbors by cosine similarity."""
    query_embedding = await get_embedding(query, org_id)

    # Build the SQL with pgvector cosine distance operator (<=>)
    # Lower distance = more similar; similarity = 1 - distance
    where_clauses = ["organization_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id, "limit": limit}

    if source_filter:
        where_clauses.append("source LIKE :source_filter")
        params["source_filter"] = f"{source_filter}%"

    # Exclude expired memories
    where_clauses.append("(expires_at IS NULL OR expires_at > :now)")
    params["now"] = utcnow()

    where_sql = " AND ".join(where_clauses)

    # Use $N-style parameters to avoid conflict between SQLAlchemy's :param
    # syntax and PostgreSQL's ::type cast syntax
    sql = text(f"""
        SELECT id, content, source, agent_id, metadata_json, created_at,
               1 - (embedding <=> cast(:query_embedding AS vector)) AS similarity
        FROM vector_memories
        WHERE {where_sql}
        ORDER BY embedding <=> cast(:query_embedding AS vector)
        LIMIT :limit
    """)
    params["query_embedding"] = str(query_embedding)

    async with async_session_maker() as session:
        result = await session.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "content": row["content"],
            "source": row["source"],
            "agent_id": row["agent_id"],
            "metadata": json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            "similarity": float(row["similarity"]),
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


async def forget_memory(org_id: UUID, memory_id: UUID) -> bool:
    """Delete a specific memory by ID (org-scoped)."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(VectorMemory).where(
                VectorMemory.id == memory_id,
                VectorMemory.organization_id == org_id,
            )
        )
        memory = result.scalars().first()
        if not memory:
            return False
        await session.delete(memory)
        await session.commit()

    logger.info("embedding.forgot org_id=%s id=%s", org_id, memory_id)
    return True


async def forget_by_source(org_id: UUID, source: str) -> int:
    """Bulk delete memories by source prefix (org-scoped)."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(VectorMemory).where(
                VectorMemory.organization_id == org_id,
                VectorMemory.source.startswith(source),
            )
        )
        memories = result.scalars().all()
        count = len(memories)
        for m in memories:
            await session.delete(m)
        await session.commit()

    logger.info("embedding.forgot_by_source org_id=%s source=%s count=%d", org_id, source, count)
    return count
