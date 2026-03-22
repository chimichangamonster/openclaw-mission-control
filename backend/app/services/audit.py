"""Audit logging for security-sensitive operations."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.audit_log import AuditLog

logger = get_logger(__name__)


async def log_audit(
    org_id: UUID,
    action: str,
    *,
    user_id: UUID | None = None,
    resource_type: str = "",
    resource_id: UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist an audit log entry. Fire-and-forget — never raises."""
    try:
        async with async_session_maker() as session:
            entry = AuditLog(
                id=uuid4(),
                organization_id=org_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details_json=json.dumps(details or {}),
                ip_address=ip_address,
                created_at=utcnow(),
            )
            session.add(entry)
            await session.commit()
    except Exception:
        logger.warning("audit.log_failed action=%s org=%s", action, org_id)
