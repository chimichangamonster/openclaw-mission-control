"""TX audit record — persists transmission audit trail from the pentest bridge."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel


class TxAuditRecord(QueryModel, table=True):
    """Audit trail for every TX action on the pentest bridge.

    Mirrors the bridge-side JSONL audit log in PostgreSQL for durable
    storage, querying, and report generation.  Every transmission —
    whether allowed, blocked, or failed — gets a record.
    """

    __tablename__ = "tx_audit_records"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    # TX action metadata
    tx_mode: str = Field(index=True)  # passive, authorized, lab
    action: str = Field(index=True)  # wifi_deauth, replay, ble_write, etc.
    endpoint: str = Field(default="")  # bridge endpoint path
    parameters_json: str = Field(default="{}", sa_column=Column(JSON))
    rf_details_json: str = Field(
        default="{}", sa_column=Column(JSON)
    )  # frequency, power, modulation, duration
    target_json: str = Field(default="{}", sa_column=Column(JSON))  # device type, identifier, name

    # Authorization
    approval_id: UUID | None = Field(default=None, index=True)  # FK to approvals (authorized mode)
    approved_by: str | None = Field(default=None)  # email of approver
    justification: str | None = Field(default=None)  # agent's stated reason

    # Profile context
    profile_key: str | None = Field(default=None, index=True)  # active pentest profile
    roe_reference: str | None = Field(default=None)  # RoE document ID

    # Result
    result_status: str = Field(default="", index=True)  # success, failure, timeout, blocked
    result_detail: str = Field(default="")  # human-readable outcome

    # Cross-reference
    bridge_tx_id: str | None = Field(default=None, index=True)  # bridge-side audit ID
    agent_id: str | None = Field(default=None)  # which agent/skill initiated

    # MAC tracking (internal only — never exposed to LLMs)
    mac_real: str | None = Field(default=None)
    mac_spoofed: str | None = Field(default=None)

    # Timestamps
    captured_at: datetime = Field(default_factory=utcnow, index=True)  # when TX happened
    created_at: datetime = Field(default_factory=utcnow)  # when record persisted
