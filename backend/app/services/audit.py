"""Audit logging for security-sensitive operations.

Dual-write: persists to PostgreSQL (primary) and emits structured JSON to
stdout (picked up by Promtail → Loki as a tamper-independent second copy).
"""


from __future__ import annotations

from typing import Any

import json
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.audit_log import AuditLog

logger = get_logger(__name__)

# Dedicated logger for audit stream — Promtail labels by logger name
_audit_stream = get_logger("audit.stream")


def _emit_audit_to_log(
    entry_id: UUID,
    org_id: UUID,
    action: str,
    user_id: UUID | None,
    resource_type: str,
    resource_id: UUID | None,
    details: dict[str, Any] | None,
    ip_address: str | None,
) -> None:
    """Emit audit event as structured log for Loki ingestion."""
    _audit_stream.info(
        "audit.event %s org=%s",
        action,
        str(org_id)[:8],
        extra={
            "log_type": "audit",
            "audit_id": str(entry_id),
            "org_id": str(org_id),
            "user_id": str(user_id) if user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "details": details or {},
            "ip_address": ip_address,
        },
    )


async def log_audit(
    org_id: UUID,
    action: str,
    *,
    user_id: UUID | None = None,
    resource_type: str = "",
    resource_id: UUID | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist an audit log entry. Fire-and-forget — never raises.

    Writes to both PostgreSQL and stdout (Loki via Promtail).
    """
    entry_id = uuid4()

    # Always emit to log stream regardless of DB success
    _emit_audit_to_log(
        entry_id, org_id, action, user_id, resource_type, resource_id, details, ip_address
    )

    try:
        async with async_session_maker() as session:
            entry = AuditLog(
                id=entry_id,
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
