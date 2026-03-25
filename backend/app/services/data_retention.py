"""Data retention enforcement — periodic cleanup of old records.

Runs daily as a background task. Deletes expired rows in batches to avoid
long-running transactions and excessive WAL growth.

Default retention periods (used when orgs don't override):
- activity_events: 90 days
- email_messages + email_attachments: 180 days
- audit_logs: 365 days
- board_webhook_payloads: 30 days
- daily_agent_spends: 365 days
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select, text

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker

logger = get_logger(__name__)

# Platform defaults (days). Per-org overrides in data_policy_json.
DEFAULT_RETENTION = {
    "activity_retention_days": 90,
    "email_retention_days": 180,
    "audit_retention_days": 365,
    "webhook_retention_days": 30,
    "spend_retention_days": 365,
}

# Max rows to delete per batch to avoid long locks
BATCH_SIZE = 1000


async def _delete_batched(session, stmt, label: str) -> int:
    """Execute a DELETE statement in batches. Returns total rows deleted."""
    total = 0
    while True:
        result = await session.execute(stmt.limit(BATCH_SIZE))
        # For bulk deletes we need a different approach — use subquery
        break  # will use subquery pattern below
    return total


async def _cleanup_table(
    *,
    table_name: str,
    timestamp_col: str,
    cutoff_days: int,
    org_filter: str | None = None,
    org_id: str | None = None,
) -> int:
    """Delete rows older than cutoff_days from a table. Returns count deleted."""
    if cutoff_days <= 0:
        return 0

    cutoff = utcnow() - timedelta(days=cutoff_days)
    where_clause = f"{timestamp_col} < :cutoff"
    params: dict = {"cutoff": cutoff}

    if org_filter and org_id:
        # Normalize UUID: strip hyphens for SQLite compat (PostgreSQL handles both forms)
        normalized_id = org_id.replace("-", "")
        where_clause += f" AND REPLACE(CAST({org_filter} AS TEXT), '-', '') = :org_id"
        params["org_id"] = normalized_id

    total = 0
    async with async_session_maker() as session:
        while True:
            # Subquery to find IDs to delete in batches
            result = await session.execute(
                text(
                    f"DELETE FROM {table_name} WHERE id IN "
                    f"(SELECT id FROM {table_name} WHERE {where_clause} LIMIT :batch_size)"
                ),
                {**params, "batch_size": BATCH_SIZE},
            )
            deleted = result.rowcount
            total += deleted
            await session.commit()
            if deleted < BATCH_SIZE:
                break

    if total > 0:
        logger.info(
            "data_retention.cleaned",
            extra={"table": table_name, "deleted": total, "cutoff_days": cutoff_days},
        )
    return total


async def _get_org_retention_settings() -> dict[str, dict[str, int]]:
    """Load per-org retention overrides from organization_settings."""
    import json

    from app.models.organization_settings import OrganizationSettings

    async with async_session_maker() as session:
        result = await session.execute(select(OrganizationSettings))
        settings_list = result.scalars().all()

    org_settings: dict[str, dict[str, int]] = {}
    for s in settings_list:
        try:
            policy = json.loads(s.data_policy_json) if s.data_policy_json else {}
        except (json.JSONDecodeError, TypeError):
            policy = {}
        overrides = {}
        for key in DEFAULT_RETENTION:
            if key in policy and isinstance(policy[key], int) and policy[key] >= 0:
                overrides[key] = policy[key]
        if overrides:
            org_settings[str(s.organization_id)] = overrides
    return org_settings


async def run_retention_cleanup() -> dict[str, int]:
    """Run the full retention cleanup across all tables.

    Returns a dict mapping table names to the number of rows deleted.
    """
    results: dict[str, int] = {}

    # ── Platform-wide tables (not org-scoped) ───────────────────────
    # ActivityEvent — board-scoped, clean globally
    results["activity_events"] = await _cleanup_table(
        table_name="activity_events",
        timestamp_col="created_at",
        cutoff_days=DEFAULT_RETENTION["activity_retention_days"],
    )

    # BoardWebhookPayload — board-scoped, clean globally
    results["board_webhook_payloads"] = await _cleanup_table(
        table_name="board_webhook_payloads",
        timestamp_col="received_at",
        cutoff_days=DEFAULT_RETENTION["webhook_retention_days"],
    )

    # ── Org-scoped tables ───────────────────────────────────────────
    # For org-scoped tables, use per-org overrides or platform defaults
    org_settings = await _get_org_retention_settings()

    # Get all org IDs that have email messages, audit logs, or spend records
    async with async_session_maker() as session:
        org_ids_result = await session.execute(
            text(
                "SELECT DISTINCT organization_id FROM email_messages "
                "UNION SELECT DISTINCT organization_id FROM audit_logs "
                "UNION SELECT DISTINCT organization_id FROM daily_agent_spends"
            )
        )
        org_ids = [str(row[0]) for row in org_ids_result.fetchall()]

    email_total = 0
    audit_total = 0
    spend_total = 0

    for org_id in org_ids:
        overrides = org_settings.get(org_id, {})

        # Email messages (cascades to attachments via FK if configured, otherwise clean separately)
        email_days = overrides.get("email_retention_days", DEFAULT_RETENTION["email_retention_days"])
        email_total += await _cleanup_table(
            table_name="email_messages",
            timestamp_col="received_at",
            cutoff_days=email_days,
            org_filter="organization_id",
            org_id=org_id,
        )

        # Audit logs
        audit_days = overrides.get("audit_retention_days", DEFAULT_RETENTION["audit_retention_days"])
        audit_total += await _cleanup_table(
            table_name="audit_logs",
            timestamp_col="created_at",
            cutoff_days=audit_days,
            org_filter="organization_id",
            org_id=org_id,
        )

        # Daily agent spends
        spend_days = overrides.get("spend_retention_days", DEFAULT_RETENTION["spend_retention_days"])
        spend_total += await _cleanup_table(
            table_name="daily_agent_spends",
            timestamp_col="created_at",
            cutoff_days=spend_days,
            org_filter="organization_id",
            org_id=org_id,
        )

    results["email_messages"] = email_total
    results["audit_logs"] = audit_total
    results["daily_agent_spends"] = spend_total

    total_deleted = sum(results.values())
    if total_deleted > 0:
        logger.info(
            "data_retention.complete",
            extra={"total_deleted": total_deleted, "breakdown": results},
        )
    else:
        logger.info("data_retention.complete", extra={"total_deleted": 0})

    return results
