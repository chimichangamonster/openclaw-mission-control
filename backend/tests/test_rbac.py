# ruff: noqa: INP001
"""Tests for role-based access control (RBAC) — role hierarchy, permissions, gating."""

from __future__ import annotations

import pytest


class TestRoleHierarchy:
    """Role rank ordering and constants."""

    def test_role_ranks(self):
        from app.services.organizations import ROLE_RANK

        assert ROLE_RANK["viewer"] < ROLE_RANK["member"]
        assert ROLE_RANK["member"] < ROLE_RANK["operator"]
        assert ROLE_RANK["operator"] < ROLE_RANK["admin"]
        assert ROLE_RANK["admin"] < ROLE_RANK["owner"]

    def test_valid_roles(self):
        from app.services.organizations import VALID_ROLES

        assert VALID_ROLES == {"viewer", "member", "operator", "admin", "owner"}

    def test_admin_roles(self):
        from app.services.organizations import ADMIN_ROLES

        assert "owner" in ADMIN_ROLES
        assert "admin" in ADMIN_ROLES
        assert "operator" not in ADMIN_ROLES
        assert "member" not in ADMIN_ROLES
        assert "viewer" not in ADMIN_ROLES

    def test_operator_roles(self):
        from app.services.organizations import OPERATOR_ROLES

        assert "owner" in OPERATOR_ROLES
        assert "admin" in OPERATOR_ROLES
        assert "operator" in OPERATOR_ROLES
        assert "member" not in OPERATOR_ROLES
        assert "viewer" not in OPERATOR_ROLES


class TestIsOrgAdmin:
    """is_org_admin helper function."""

    def test_owner_is_admin(self):
        from unittest.mock import MagicMock

        from app.services.organizations import is_org_admin

        member = MagicMock()
        member.role = "owner"
        assert is_org_admin(member) is True

    def test_admin_is_admin(self):
        from unittest.mock import MagicMock

        from app.services.organizations import is_org_admin

        member = MagicMock()
        member.role = "admin"
        assert is_org_admin(member) is True

    def test_operator_is_not_admin(self):
        from unittest.mock import MagicMock

        from app.services.organizations import is_org_admin

        member = MagicMock()
        member.role = "operator"
        assert is_org_admin(member) is False

    def test_member_is_not_admin(self):
        from unittest.mock import MagicMock

        from app.services.organizations import is_org_admin

        member = MagicMock()
        member.role = "member"
        assert is_org_admin(member) is False

    def test_viewer_is_not_admin(self):
        from unittest.mock import MagicMock

        from app.services.organizations import is_org_admin

        member = MagicMock()
        member.role = "viewer"
        assert is_org_admin(member) is False


class TestRoleRankComparison:
    """Role rank comparison for require_org_role factory."""

    def test_operator_can_access_member_endpoints(self):
        from app.services.organizations import ROLE_RANK

        assert ROLE_RANK["operator"] >= ROLE_RANK["member"]

    def test_viewer_cannot_access_operator_endpoints(self):
        from app.services.organizations import ROLE_RANK

        assert ROLE_RANK["viewer"] < ROLE_RANK["operator"]

    def test_admin_can_access_operator_endpoints(self):
        from app.services.organizations import ROLE_RANK

        assert ROLE_RANK["admin"] >= ROLE_RANK["operator"]

    def test_member_cannot_access_admin_endpoints(self):
        from app.services.organizations import ROLE_RANK

        assert ROLE_RANK["member"] < ROLE_RANK["admin"]

    def test_owner_can_access_everything(self):
        from app.services.organizations import ROLE_RANK

        max_rank = max(ROLE_RANK.values())
        assert ROLE_RANK["owner"] == max_rank


class TestPermissionMatrix:
    """Verify the intended permission matrix is correct."""

    def _can_access(self, user_role: str, required_role: str) -> bool:
        from app.services.organizations import ROLE_RANK

        return ROLE_RANK.get(user_role, 0) >= ROLE_RANK.get(required_role, 0)

    def test_viewer_permissions(self):
        assert self._can_access("viewer", "viewer")
        assert not self._can_access("viewer", "member")
        assert not self._can_access("viewer", "operator")
        assert not self._can_access("viewer", "admin")
        assert not self._can_access("viewer", "owner")

    def test_member_permissions(self):
        assert self._can_access("member", "viewer")
        assert self._can_access("member", "member")
        assert not self._can_access("member", "operator")
        assert not self._can_access("member", "admin")

    def test_operator_permissions(self):
        assert self._can_access("operator", "viewer")
        assert self._can_access("operator", "member")
        assert self._can_access("operator", "operator")
        assert not self._can_access("operator", "admin")

    def test_admin_permissions(self):
        assert self._can_access("admin", "viewer")
        assert self._can_access("admin", "member")
        assert self._can_access("admin", "operator")
        assert self._can_access("admin", "admin")
        assert not self._can_access("admin", "owner")

    def test_owner_permissions(self):
        assert self._can_access("owner", "viewer")
        assert self._can_access("owner", "member")
        assert self._can_access("owner", "operator")
        assert self._can_access("owner", "admin")
        assert self._can_access("owner", "owner")


class TestFeatureFlagDefaults:
    """Feature flag defaults include new flags."""

    def test_microsoft_graph_default_off(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert DEFAULT_FEATURE_FLAGS["microsoft_graph"] is False

    def test_document_generation_default_on(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert DEFAULT_FEATURE_FLAGS["document_generation"] is True

    def test_all_original_flags_preserved(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert DEFAULT_FEATURE_FLAGS["paper_trading"] is True
        assert DEFAULT_FEATURE_FLAGS["paper_bets"] is True
        assert DEFAULT_FEATURE_FLAGS["email"] is True
        assert DEFAULT_FEATURE_FLAGS["watchlist"] is True
        assert DEFAULT_FEATURE_FLAGS["cost_tracker"] is True
        assert DEFAULT_FEATURE_FLAGS["cron_jobs"] is True
        assert DEFAULT_FEATURE_FLAGS["approvals"] is True
