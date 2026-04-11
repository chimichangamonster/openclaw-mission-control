# ruff: noqa: INP001
"""Unit tests for Field Ops Orchestrator Phase 2 — TX audit, profile schema, validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# TxAuditRecord model
# ---------------------------------------------------------------------------


class TestTxAuditRecordModel:
    """Verify TxAuditRecord model instantiation and defaults."""

    def test_create_minimal(self) -> None:
        from app.models.tx_audit_records import TxAuditRecord

        record = TxAuditRecord(
            organization_id=uuid4(),
            tx_mode="passive",
            action="wifi_deauth",
        )
        assert record.tx_mode == "passive"
        assert record.action == "wifi_deauth"
        assert record.endpoint == ""
        assert record.result_status == ""
        assert record.approval_id is None
        assert record.mac_real is None
        assert record.mac_spoofed is None
        assert record.id is not None

    def test_create_full(self) -> None:
        from app.models.tx_audit_records import TxAuditRecord

        approval_id = uuid4()
        record = TxAuditRecord(
            organization_id=uuid4(),
            tx_mode="authorized",
            action="ble_write",
            endpoint="/ble/write",
            parameters_json=json.dumps({"mac": "AA:BB:CC:DD:EE:FF"}),
            rf_details_json=json.dumps({"frequency_mhz": 2402}),
            target_json=json.dumps({"type": "ble_device", "identifier": "AA:BB:CC:DD:EE:FF"}),
            approval_id=approval_id,
            approved_by="henz@vantagesolutions.ca",
            justification="Testing BLE pairing — RoE section 5.1",
            profile_key="acme-hq-2026",
            roe_reference="VS-ROE-2026-003",
            result_status="success",
            result_detail="Write confirmed",
            bridge_tx_id="tx_1712000000_abcdef",
            agent_id="the-claw",
            mac_real="11:22:33:44:55:66",
            mac_spoofed="AA:BB:CC:DD:EE:FF",
        )
        assert record.approval_id == approval_id
        assert record.roe_reference == "VS-ROE-2026-003"
        assert record.result_status == "success"

    def test_tablename(self) -> None:
        from app.models.tx_audit_records import TxAuditRecord

        assert TxAuditRecord.__tablename__ == "tx_audit_records"


# ---------------------------------------------------------------------------
# Profile schema extension — new fields
# ---------------------------------------------------------------------------


class TestProfileSchemaExtension:
    """Verify ProfileCreate/ProfileUpdate accept Phase 2 fields."""

    def test_profile_create_defaults(self) -> None:
        from app.api.pentest import ProfileCreate

        p = ProfileCreate(key="test-site", name="Test Site")
        assert p.profile_type == "pentest"
        assert p.tx_mode == "passive"
        assert p.engagement_type == "combined"
        assert p.environment_tags == []
        assert p.roe_reference == ""
        assert p.authorized_aps == []

    def test_profile_create_full(self) -> None:
        from app.api.pentest import AuthorizedAP, ProfileCreate

        p = ProfileCreate(
            key="acme-hq",
            name="ACME HQ Assessment",
            location="123 Main St",
            profile_type="pentest",
            tx_mode="authorized",
            engagement_type="wireless",
            environment_tags=["wifi", "iot", "office"],
            roe_reference="VS-ROE-2026-003",
            authorized_aps=[
                AuthorizedAP(
                    mac="AA:BB:CC:DD:EE:FF",
                    vendor="Cisco",
                    ssid="CorpWiFi-5G",
                    location="Floor 2",
                ),
            ],
        )
        assert p.profile_type == "pentest"
        assert p.tx_mode == "authorized"
        assert len(p.authorized_aps) == 1
        assert p.authorized_aps[0].mac == "AA:BB:CC:DD:EE:FF"

    def test_profile_update_partial(self) -> None:
        from app.api.pentest import ProfileUpdate

        p = ProfileUpdate(tx_mode="lab", environment_tags=["healthcare"])
        assert p.tx_mode == "lab"
        assert p.environment_tags == ["healthcare"]
        # Unset fields should be None
        assert p.profile_type is None
        assert p.roe_reference is None
        assert p.authorized_aps is None

    def test_authorized_ap_model(self) -> None:
        from app.api.pentest import AuthorizedAP

        ap = AuthorizedAP(mac="AA:BB:CC:DD:EE:FF")
        assert ap.vendor == ""
        assert ap.ssid == ""
        assert ap.location == ""


# ---------------------------------------------------------------------------
# Profile validation rules
# ---------------------------------------------------------------------------


class TestProfileValidation:
    """Validate profile_type / tx_mode / engagement_type constraints."""

    def test_rf_survey_forces_passive(self) -> None:
        from fastapi import HTTPException

        from app.api.pentest import _validate_profile_fields

        with pytest.raises(HTTPException) as exc_info:
            _validate_profile_fields(
                profile_type="rf_survey",
                tx_mode="authorized",
                engagement_type="combined",
                environment_tags=[],
                roe_reference="some-roe",
            )
        assert exc_info.value.status_code == 422
        assert "rf_survey" in str(exc_info.value.detail)
        assert "passive" in str(exc_info.value.detail)

    def test_tscm_forces_passive(self) -> None:
        from fastapi import HTTPException

        from app.api.pentest import _validate_profile_fields

        with pytest.raises(HTTPException) as exc_info:
            _validate_profile_fields(
                profile_type="tscm",
                tx_mode="lab",
                engagement_type="combined",
                environment_tags=[],
                roe_reference="",
            )
        assert exc_info.value.status_code == 422
        assert "tscm" in str(exc_info.value.detail)

    def test_rf_survey_passive_ok(self) -> None:
        from app.api.pentest import _validate_profile_fields

        # Should not raise
        _validate_profile_fields(
            profile_type="rf_survey",
            tx_mode="passive",
            engagement_type="wireless",
            environment_tags=["office"],
            roe_reference="",
        )

    def test_tscm_passive_ok(self) -> None:
        from app.api.pentest import _validate_profile_fields

        _validate_profile_fields(
            profile_type="tscm",
            tx_mode="passive",
            engagement_type="physical",
            environment_tags=["datacenter"],
            roe_reference="",
        )

    def test_authorized_requires_roe(self) -> None:
        from fastapi import HTTPException

        from app.api.pentest import _validate_profile_fields

        with pytest.raises(HTTPException) as exc_info:
            _validate_profile_fields(
                profile_type="pentest",
                tx_mode="authorized",
                engagement_type="combined",
                environment_tags=[],
                roe_reference="",
            )
        assert exc_info.value.status_code == 422
        assert "roe_reference" in str(exc_info.value.detail)

    def test_authorized_with_roe_ok(self) -> None:
        from app.api.pentest import _validate_profile_fields

        _validate_profile_fields(
            profile_type="pentest",
            tx_mode="authorized",
            engagement_type="combined",
            environment_tags=[],
            roe_reference="VS-ROE-2026-003",
        )

    def test_lab_mode_no_roe_ok(self) -> None:
        from app.api.pentest import _validate_profile_fields

        _validate_profile_fields(
            profile_type="pentest",
            tx_mode="lab",
            engagement_type="combined",
            environment_tags=[],
            roe_reference="",
        )

    def test_invalid_profile_type(self) -> None:
        from fastapi import HTTPException

        from app.api.pentest import _validate_profile_fields

        with pytest.raises(HTTPException) as exc_info:
            _validate_profile_fields(
                profile_type="invalid_type",
                tx_mode="passive",
                engagement_type="combined",
                environment_tags=[],
                roe_reference="",
            )
        assert exc_info.value.status_code == 422

    def test_invalid_tx_mode(self) -> None:
        from fastapi import HTTPException

        from app.api.pentest import _validate_profile_fields

        with pytest.raises(HTTPException) as exc_info:
            _validate_profile_fields(
                profile_type="pentest",
                tx_mode="yolo",
                engagement_type="combined",
                environment_tags=[],
                roe_reference="",
            )
        assert exc_info.value.status_code == 422

    def test_invalid_engagement_type(self) -> None:
        from fastapi import HTTPException

        from app.api.pentest import _validate_profile_fields

        with pytest.raises(HTTPException) as exc_info:
            _validate_profile_fields(
                profile_type="pentest",
                tx_mode="passive",
                engagement_type="social_engineering",
                environment_tags=[],
                roe_reference="",
            )
        assert exc_info.value.status_code == 422

    def test_invalid_environment_tag(self) -> None:
        from fastapi import HTTPException

        from app.api.pentest import _validate_profile_fields

        with pytest.raises(HTTPException) as exc_info:
            _validate_profile_fields(
                profile_type="pentest",
                tx_mode="passive",
                engagement_type="combined",
                environment_tags=["space_station"],
                roe_reference="",
            )
        assert exc_info.value.status_code == 422

    def test_none_fields_skip_validation(self) -> None:
        """None values should be silently accepted (partial update)."""
        from app.api.pentest import _validate_profile_fields

        _validate_profile_fields(
            profile_type=None,
            tx_mode=None,
            engagement_type=None,
            environment_tags=None,
            roe_reference=None,
        )


# ---------------------------------------------------------------------------
# TX Audit request model
# ---------------------------------------------------------------------------


class TestTxAuditCreateModel:
    """Verify TxAuditCreate request model validation."""

    def test_minimal(self) -> None:
        from app.api.pentest import TxAuditCreate

        req = TxAuditCreate(tx_mode="passive", action="wifi_deauth")
        assert req.tx_mode == "passive"
        assert req.action == "wifi_deauth"
        assert req.parameters == {}
        assert req.approval_id is None

    def test_full(self) -> None:
        from app.api.pentest import TxAuditCreate

        req = TxAuditCreate(
            tx_mode="authorized",
            action="replay",
            endpoint="/replay",
            parameters={"signal_id": "sig-001"},
            rf_details={"frequency_mhz": 433.92},
            target={"type": "garage_door", "identifier": "sig-001"},
            approval_id="550e8400-e29b-41d4-a716-446655440000",
            approved_by="henz@vantagesolutions.ca",
            justification="Testing replay — RoE 4.2",
            profile_key="acme-hq-2026",
            roe_reference="VS-ROE-2026-003",
            result_status="success",
            result_detail="Signal replayed",
            bridge_tx_id="tx_1712000000_abcdef",
            agent_id="the-claw",
            captured_at="2026-04-01T14:30:00Z",
        )
        assert req.result_status == "success"
        assert req.captured_at == "2026-04-01T14:30:00Z"


# ---------------------------------------------------------------------------
# TX record serializer
# ---------------------------------------------------------------------------


class TestTxRecordSerializer:
    """Verify _tx_record_to_dict serialization."""

    def test_serialize_record(self) -> None:
        from app.api.pentest import _tx_record_to_dict
        from app.models.tx_audit_records import TxAuditRecord

        now = datetime.now(timezone.utc)
        record = TxAuditRecord(
            organization_id=uuid4(),
            tx_mode="lab",
            action="wifi_deauth",
            endpoint="/wifi/deauth",
            parameters_json={"bssid": "AA:BB:CC:DD:EE:FF"},
            rf_details_json={"frequency_mhz": 2437},
            target_json={"type": "wifi_ap"},
            result_status="success",
            result_detail="5 deauth packets sent",
            captured_at=now,
            created_at=now,
        )
        d = _tx_record_to_dict(record)
        assert d["tx_mode"] == "lab"
        assert d["action"] == "wifi_deauth"
        assert d["parameters"] == {"bssid": "AA:BB:CC:DD:EE:FF"}
        assert d["result_status"] == "success"
        assert d["captured_at"] == now.isoformat()
        assert d["approval_id"] is None


# ---------------------------------------------------------------------------
# Params hash for approval token
# ---------------------------------------------------------------------------


class TestParamsHash:
    """Verify deterministic hashing of bridge payloads."""

    def test_deterministic(self) -> None:
        from app.services.pentest.hooks import _params_hash

        params = {"bssid": "AA:BB:CC:DD:EE:FF", "count": 5}
        h1 = _params_hash(params)
        h2 = _params_hash(params)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_order_independent(self) -> None:
        from app.services.pentest.hooks import _params_hash

        h1 = _params_hash({"a": 1, "b": 2})
        h2 = _params_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_params(self) -> None:
        from app.services.pentest.hooks import _params_hash

        h1 = _params_hash({"bssid": "AA:BB:CC:DD:EE:FF"})
        h2 = _params_hash({"bssid": "11:22:33:44:55:66"})
        assert h1 != h2


# ---------------------------------------------------------------------------
# Pentest TX approval hook
# ---------------------------------------------------------------------------


class TestPentestTxHook:
    """Verify the pentest_tx approval hook creates audit records."""

    @pytest.mark.asyncio
    async def test_approved_creates_audit_record(self) -> None:
        """Approved pentest_tx should call bridge and create a success audit record."""
        from app.services.pentest.hooks import handle_pentest_tx_approval_resolution

        org_id = uuid4()
        approval_id = uuid4()

        # Mock approval
        approval = MagicMock()
        approval.id = approval_id
        approval.organization_id = org_id
        approval.status = "approved"
        approval.agent_id = "the-claw"
        approval.payload = {
            "bridge_endpoint": "/wifi/deauth",
            "bridge_payload": {"bssid": "AA:BB:CC:DD:EE:FF", "count": 5},
            "target": {"type": "wifi_ap", "identifier": "AA:BB:CC:DD:EE:FF"},
            "rf_details": {"frequency_mhz": 2437},
            "reason": "Deauth for handshake capture — RoE 4.2",
            "profile_key": "acme-hq-2026",
            "roe_reference": "VS-ROE-2026-003",
        }

        # Mock session
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        # Mock bridge call
        with (
            patch(
                "app.services.pentest.hooks._get_bridge_urls",
                new_callable=AsyncMock,
                return_value=("http://pi:8888", "api-key", "mgmt-key"),
            ),
            patch(
                "app.services.pentest.hooks._call_bridge_tx",
                new_callable=AsyncMock,
                return_value={
                    "status": "success",
                    "detail": "5 deauth packets sent",
                    "scan_id": "deauth_123",
                },
            ),
        ):
            await handle_pentest_tx_approval_resolution(
                session=session,
                approval=approval,
            )

        # Verify audit record was added
        assert session.add.call_count == 1
        record = session.add.call_args[0][0]
        assert record.tx_mode == "authorized"
        assert record.action == "wifi_deauth"
        assert record.result_status == "success"
        assert record.approval_id == approval_id
        assert record.profile_key == "acme-hq-2026"
        assert record.roe_reference == "VS-ROE-2026-003"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejected_creates_blocked_record(self) -> None:
        """Rejected pentest_tx should create a blocked audit record without calling bridge."""
        from app.services.pentest.hooks import handle_pentest_tx_approval_resolution

        approval = MagicMock()
        approval.id = uuid4()
        approval.organization_id = uuid4()
        approval.status = "rejected"
        approval.agent_id = "the-claw"
        approval.payload = {
            "bridge_endpoint": "/wifi/deauth",
            "bridge_payload": {"bssid": "AA:BB:CC:DD:EE:FF"},
            "target": {},
            "rf_details": {},
            "reason": "Deauth test",
            "profile_key": "test-profile",
            "roe_reference": "VS-ROE-2026-001",
        }

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        # Should NOT call bridge
        with patch(
            "app.services.pentest.hooks._call_bridge_tx",
            new_callable=AsyncMock,
        ) as mock_bridge:
            await handle_pentest_tx_approval_resolution(
                session=session,
                approval=approval,
            )
            mock_bridge.assert_not_awaited()

        # Should create a blocked record
        assert session.add.call_count == 1
        record = session.add.call_args[0][0]
        assert record.result_status == "blocked"
        assert "rejected" in record.result_detail.lower()

    @pytest.mark.asyncio
    async def test_pending_does_nothing(self) -> None:
        """Pending approval should not create any audit record."""
        from app.services.pentest.hooks import handle_pentest_tx_approval_resolution

        approval = MagicMock()
        approval.id = uuid4()
        approval.organization_id = uuid4()
        approval.status = "pending"
        approval.payload = {
            "bridge_endpoint": "/wifi/deauth",
            "bridge_payload": {},
        }

        session = AsyncMock()
        session.add = MagicMock()

        await handle_pentest_tx_approval_resolution(
            session=session,
            approval=approval,
        )
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_bridge_failure_logged(self) -> None:
        """Bridge failure should still create a failure audit record."""
        from app.services.pentest.hooks import handle_pentest_tx_approval_resolution

        approval = MagicMock()
        approval.id = uuid4()
        approval.organization_id = uuid4()
        approval.status = "approved"
        approval.agent_id = "the-claw"
        approval.payload = {
            "bridge_endpoint": "/wifi/deauth",
            "bridge_payload": {"bssid": "AA:BB:CC:DD:EE:FF"},
            "target": {},
            "rf_details": {},
            "reason": "Test",
            "profile_key": "test",
        }

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        with patch(
            "app.services.pentest.hooks._get_bridge_urls",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Bridge config not found"),
        ):
            await handle_pentest_tx_approval_resolution(
                session=session,
                approval=approval,
            )

        record = session.add.call_args[0][0]
        assert record.result_status == "failure"


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify Phase 2 constants are properly defined."""

    def test_valid_profile_types(self) -> None:
        from app.api.pentest import VALID_PROFILE_TYPES

        assert "pentest" in VALID_PROFILE_TYPES
        assert "rf_survey" in VALID_PROFILE_TYPES
        assert "tscm" in VALID_PROFILE_TYPES

    def test_valid_tx_modes(self) -> None:
        from app.api.pentest import VALID_TX_MODES

        assert "passive" in VALID_TX_MODES
        assert "authorized" in VALID_TX_MODES
        assert "lab" in VALID_TX_MODES

    def test_valid_engagement_types(self) -> None:
        from app.api.pentest import VALID_ENGAGEMENT_TYPES

        assert "network" in VALID_ENGAGEMENT_TYPES
        assert "wireless" in VALID_ENGAGEMENT_TYPES
        assert "physical" in VALID_ENGAGEMENT_TYPES
        assert "combined" in VALID_ENGAGEMENT_TYPES

    def test_passive_only_profiles(self) -> None:
        from app.api.pentest import PASSIVE_ONLY_PROFILES

        assert "rf_survey" in PASSIVE_ONLY_PROFILES
        assert "tscm" in PASSIVE_ONLY_PROFILES
        assert "pentest" not in PASSIVE_ONLY_PROFILES

    def test_valid_environment_tags(self) -> None:
        from app.api.pentest import VALID_ENVIRONMENT_TAGS

        expected = {
            "iot",
            "wifi",
            "office",
            "industrial",
            "healthcare",
            "datacenter",
            "retail",
            "vehicle",
        }
        assert set(VALID_ENVIRONMENT_TAGS) == expected


# ---------------------------------------------------------------------------
# Migration revision chain
# ---------------------------------------------------------------------------


class TestMigration:
    """Verify migration metadata."""

    def test_revision_chain(self) -> None:
        from migrations.versions.w7q8r9s0t1u2_add_tx_audit_records import (
            down_revision,
            revision,
        )

        assert revision == "w7q8r9s0t1u2"
        assert down_revision == "v6p7q8r9s0t1"


# ---------------------------------------------------------------------------
# Model registration
# ---------------------------------------------------------------------------


class TestModelRegistration:
    """Verify TxAuditRecord is exported in models __init__."""

    def test_exported(self) -> None:
        from app.models import TxAuditRecord

        assert TxAuditRecord.__tablename__ == "tx_audit_records"
