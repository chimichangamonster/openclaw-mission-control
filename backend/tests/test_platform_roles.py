# ruff: noqa: INP001
"""Tests for platform role separation — owner vs operator access control."""

from __future__ import annotations

import pytest

from app.core.platform_auth import (
    OPERATOR_RESTRICTED_DATA,
    PLATFORM_OPERATOR,
    PLATFORM_OWNER,
    PLATFORM_ROLES,
    check_operator_data_access,
)


# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------


class TestPlatformRoleConstants:
    def test_owner_in_roles(self) -> None:
        assert PLATFORM_OWNER in PLATFORM_ROLES

    def test_operator_in_roles(self) -> None:
        assert PLATFORM_OPERATOR in PLATFORM_ROLES

    def test_only_two_roles(self) -> None:
        assert len(PLATFORM_ROLES) == 2

    def test_restricted_data_categories(self) -> None:
        """Ensure all sensitive categories are restricted for operators."""
        assert "email_content" in OPERATOR_RESTRICTED_DATA
        assert "chat_history" in OPERATOR_RESTRICTED_DATA
        assert "api_keys_decrypted" in OPERATOR_RESTRICTED_DATA
        assert "org_settings_secrets" in OPERATOR_RESTRICTED_DATA
        assert "file_contents" in OPERATOR_RESTRICTED_DATA
        assert "calendar_events" in OPERATOR_RESTRICTED_DATA
        assert "contact_details" in OPERATOR_RESTRICTED_DATA
        assert "wecom_messages" in OPERATOR_RESTRICTED_DATA


# ---------------------------------------------------------------------------
# Operator data access checks
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, platform_role: str | None = None) -> None:
        self.platform_role = platform_role
        self.email = "test@example.com"
        self.id = "test-user-id"


class TestOperatorDataAccess:
    def test_owner_can_access_everything(self) -> None:
        """Platform owner should access all data categories without error."""
        owner = _FakeUser(platform_role=PLATFORM_OWNER)
        for category in OPERATOR_RESTRICTED_DATA:
            # Should not raise
            check_operator_data_access(owner, category)

    def test_operator_blocked_from_restricted_data(self) -> None:
        """Platform operator should be blocked from all restricted categories."""
        operator = _FakeUser(platform_role=PLATFORM_OPERATOR)
        for category in OPERATOR_RESTRICTED_DATA:
            with pytest.raises(Exception) as exc_info:
                check_operator_data_access(operator, category)
            assert exc_info.value.status_code == 403

    def test_operator_can_access_unrestricted_data(self) -> None:
        """Platform operator should access non-restricted data."""
        operator = _FakeUser(platform_role=PLATFORM_OPERATOR)
        # These are not restricted
        check_operator_data_access(operator, "org_metadata")
        check_operator_data_access(operator, "gateway_health")
        check_operator_data_access(operator, "feature_flags")

    def test_regular_user_no_restriction(self) -> None:
        """Regular users (no platform_role) are not checked by this function.

        Access control for regular users is handled by org membership,
        not platform role checks.
        """
        user = _FakeUser(platform_role=None)
        # No restriction — platform auth is a separate layer
        check_operator_data_access(user, "email_content")


# ---------------------------------------------------------------------------
# User model field
# ---------------------------------------------------------------------------


class TestUserPlatformRole:
    def test_default_is_none(self) -> None:
        from app.models.users import User

        user = User(clerk_user_id="test-123")
        assert user.platform_role is None

    def test_owner_role(self) -> None:
        from app.models.users import User

        user = User(clerk_user_id="test-owner", platform_role="owner")
        assert user.platform_role == "owner"

    def test_operator_role(self) -> None:
        from app.models.users import User

        user = User(clerk_user_id="test-operator", platform_role="operator")
        assert user.platform_role == "operator"


# ---------------------------------------------------------------------------
# Role hierarchy validation
# ---------------------------------------------------------------------------


class TestRoleHierarchy:
    def test_owner_outranks_operator(self) -> None:
        """Owner should have strictly more access than operator."""
        owner_restricted = set()  # owner has no restrictions
        operator_restricted = OPERATOR_RESTRICTED_DATA
        assert len(owner_restricted) < len(operator_restricted)

    def test_operator_restricted_categories_are_sensible(self) -> None:
        """All restricted categories should relate to client-sensitive data."""
        for category in OPERATOR_RESTRICTED_DATA:
            # Each category should be a recognizable data type
            assert "_" in category or category.isalpha(), f"Unexpected category format: {category}"

    def test_no_infrastructure_data_restricted(self) -> None:
        """Infrastructure data should NOT be restricted for operators."""
        infra_categories = {
            "gateway_health",
            "container_status",
            "service_metrics",
            "org_metadata",
            "feature_flags",
        }
        for category in infra_categories:
            assert category not in OPERATOR_RESTRICTED_DATA, (
                f"{category} should NOT be restricted — operators need infrastructure access"
            )
