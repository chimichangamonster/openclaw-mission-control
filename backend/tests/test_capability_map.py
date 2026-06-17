# ruff: noqa: INP001
"""Tests for the per-org capability map service (items 144 + 145).

Two layers:
1. Pure-helper tests — schedule formatting, agent-role extraction, client
   capability-label mapping, trust-posture derivation. No DB.
2. Integration tests of build_capability_map against in-memory SQLite with a
   monkeypatched cron RPC — the redaction contract (item 145 never leaks skills
   / infra detail / model IDs) and cross-org isolation.

The redaction contract is the load-bearing assertion: the client-facing
(redacted) view must NOT carry a skills section, raw feature-flag map, or
per-integration infra detail (addresses), and MUST carry friendly capability
labels + a trust-posture block.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.services.capability_map as cm
from app.models.agents import Agent
from app.models.email_accounts import EmailAccount
from app.models.gateways import Gateway
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization
from app.services.capability_map import (
    _agent_role,
    _client_capabilities,
    _format_schedule,
    _trust_posture,
    build_capability_map,
)

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestFormatSchedule:
    def test_cron_with_expr_and_tz(self) -> None:
        out = _format_schedule({"kind": "cron", "expr": "0 9 * * 1", "tz": "America/Edmonton"})
        assert out == "0 9 * * 1 (America/Edmonton)"

    def test_cron_expr_no_tz(self) -> None:
        assert _format_schedule({"kind": "cron", "expr": "0 9 * * 1"}) == "0 9 * * 1"

    def test_non_cron_kind(self) -> None:
        assert _format_schedule({"kind": "interval"}) == "interval"

    def test_none_and_garbage(self) -> None:
        assert _format_schedule(None) is None
        assert _format_schedule("nope") is None
        assert _format_schedule({}) is None


class TestAgentRole:
    def test_extracts_first_present_key(self) -> None:
        agent = Agent(gateway_id=uuid4(), name="Scout", identity_profile={"role": "Market Scout"})
        assert _agent_role(agent) == "Market Scout"

    def test_falls_through_to_summary(self) -> None:
        agent = Agent(gateway_id=uuid4(), name="X", identity_profile={"summary": "Does things"})
        assert _agent_role(agent) == "Does things"

    def test_no_profile_returns_none(self) -> None:
        assert _agent_role(Agent(gateway_id=uuid4(), name="X")) is None

    def test_blank_value_skipped(self) -> None:
        agent = Agent(gateway_id=uuid4(), name="X", identity_profile={"role": "   "})
        assert _agent_role(agent) is None


class TestClientCapabilities:
    def test_only_enabled_client_relevant_flags_surface(self) -> None:
        flags = {
            "email": True,
            "document_generation": True,
            "paper_trading": True,  # internal — must NOT surface
            "pentest": True,  # internal — must NOT surface
            "wechat": False,  # disabled — must NOT surface
        }
        caps = _client_capabilities(flags)
        labels = {c["label"] for c in caps}
        assert "Email management" in labels
        assert "Document generation" in labels
        # Internal/dev flags never become client-facing capabilities.
        assert not any("trading" in label.lower() for label in labels)
        assert not any("pentest" in label.lower() for label in labels)
        # Disabled flags excluded.
        assert not any("wecom" in label.lower() or "wechat" in label.lower() for label in labels)

    def test_each_capability_has_label_and_description(self) -> None:
        caps = _client_capabilities({"email": True})
        assert caps and all(c["label"] and c["description"] for c in caps)


class TestTrustPosture:
    def test_always_asserts_hitl_and_autopost_never(self) -> None:
        posture = _trust_posture({}, {})
        joined = " ".join(posture["human_approval"]).lower()
        assert "human approval" in joined
        assert "auto-published" in joined or "never auto" in joined

    def test_tenant_isolation_in_boundaries(self) -> None:
        posture = _trust_posture({}, {})
        assert any("never shared across tenants" in b.lower() for b in posture["boundaries"])

    def test_redaction_level_reflected(self) -> None:
        posture = _trust_posture({}, {"redaction_level": "strict"})
        assert any("strict" in d for d in posture["data_protection"])

    def test_approvals_flag_adds_workflow_line(self) -> None:
        with_flag = _trust_posture({"approvals": True}, {})
        without = _trust_posture({"approvals": False}, {})
        assert len(with_flag["human_approval"]) > len(without["human_approval"])


# ---------------------------------------------------------------------------
# Integration — redaction contract + org isolation
# ---------------------------------------------------------------------------

ORG_A = uuid4()
ORG_B = uuid4()
GW_A = uuid4()
GW_B = uuid4()


@pytest_asyncio.fixture
async def session() -> AsyncSession:  # type: ignore[misc]
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = AsyncSession(engine)
    async with maker as s:
        s.add(Organization(id=ORG_A, name="Org A", slug="org-a"))
        s.add(Organization(id=ORG_B, name="Org B", slug="org-b"))
        s.add(
            OrganizationSettings(
                organization_id=ORG_A,
                feature_flags_json='{"email": true, "document_generation": true, "approvals": true}',
                industry_template_id="construction",
            )
        )
        s.add(Gateway(id=GW_A, organization_id=ORG_A, name="gw-a", url="ws://a", workspace_root="/a"))
        s.add(Gateway(id=GW_B, organization_id=ORG_B, name="gw-b", url="ws://b", workspace_root="/b"))
        s.add(Agent(gateway_id=GW_A, name="The Claw", status="active", is_board_lead=True))
        s.add(Agent(gateway_id=GW_B, name="Other Org Agent", status="active"))
        s.add(
            EmailAccount(
                organization_id=ORG_A,
                user_id=uuid4(),
                provider="microsoft",
                email_address="henry@example.com",
                sync_enabled=True,
                visibility="private",
                agent_access="enabled",
            )
        )
        s.add(
            EmailAccount(
                organization_id=ORG_B,
                user_id=uuid4(),
                provider="zoho",
                email_address="other@example.com",
                sync_enabled=True,
            )
        )
        await s.commit()
        yield s


@pytest.fixture(autouse=True)
def _stub_cron_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the cron RPC return a deterministic job list without a real gateway."""

    monkeypatch.setattr(cm, "optional_gateway_client_config", lambda gw: object())

    async def fake_call(method, params, *, config, org_id):  # noqa: ANN001, ANN202
        assert method == "cron.list"
        return {
            "jobs": [
                {
                    "name": "competitor-scan",
                    "enabled": True,
                    "schedule": {"kind": "cron", "expr": "0 9 * * 1", "tz": "America/Edmonton"},
                    "state": {"lastRunStatus": "error"},
                }
            ]
        }

    monkeypatch.setattr(cm, "openclaw_call", fake_call)


def _org(org_id):  # noqa: ANN001, ANN202
    org = Organization(name="x", slug="org-a" if org_id == ORG_A else "org-b")
    org.id = org_id
    return org


@pytest.mark.asyncio
class TestRedactionContract:
    async def test_full_view_includes_skills_and_flags(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=False)
        assert "skills" in result  # full view renders registry skills section
        assert "feature_flags" in result
        assert "capabilities" not in result
        assert "trust_posture" not in result

    async def test_redacted_view_omits_skills_and_flags(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=True)
        # Load-bearing: skills are the proprietary layer — never on the client surface.
        assert "skills" not in result
        assert "feature_flags" not in result
        assert "capabilities" in result
        assert "trust_posture" in result

    async def test_redacted_integrations_omit_addresses(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=True)
        assert result["integrations"], "expected at least one integration"
        for integ in result["integrations"]:
            assert "address" not in integ
            assert "visibility" not in integ
            assert integ.keys() <= {"type", "provider", "connected", "label"}

    async def test_full_integrations_include_detail(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=False)
        email = next(i for i in result["integrations"] if i["type"] == "email")
        assert email["address"] == "henry@example.com"
        assert email["visibility"] == "private"
        assert email["agent_access"] == "enabled"

    async def test_redacted_crons_omit_last_status(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=True)
        assert result["crons"]["jobs"]
        for job in result["crons"]["jobs"]:
            assert "last_status" not in job  # stale error badge erodes client trust
            assert job["schedule"] == "0 9 * * 1 (America/Edmonton)"

    async def test_full_crons_include_last_status(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=False)
        assert result["crons"]["jobs"][0]["last_status"] == "error"


@pytest.mark.asyncio
class TestOrgIsolation:
    async def test_agents_scoped_to_org(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=False)
        names = {a["name"] for a in result["agents"]}
        assert names == {"The Claw"}
        assert "Other Org Agent" not in names

    async def test_integrations_scoped_to_org(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=False)
        addrs = {i.get("address") for i in result["integrations"]}
        assert "henry@example.com" in addrs
        assert "other@example.com" not in addrs

    async def test_template_resolved(self, session: AsyncSession) -> None:
        result = await build_capability_map(session, _org(ORG_A), redacted=False)
        assert result["industry_template"]["id"] == "construction"
        assert result["industry_template"]["name"]


@pytest.mark.asyncio
async def test_no_gateway_degrades_gracefully(session: AsyncSession) -> None:
    """An org with no gateway returns reachable=false crons, not a 500."""
    org = Organization(name="Fresh", slug="fresh")
    org.id = uuid4()
    result = await build_capability_map(session, org, redacted=True)
    assert result["crons"] == {"reachable": False, "jobs": []}
    assert result["agents"] == []
