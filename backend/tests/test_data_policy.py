# ruff: noqa: INP001
"""Tests for data policy defaults and model behavior."""

from __future__ import annotations

import json


class TestDataPolicyDefaults:
    """Organization settings data policy defaults."""

    def test_default_policy(self):
        """Default data policy has moderate redaction."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        assert policy["redaction_level"] == "moderate"
        assert policy["allow_email_content_to_llm"] is True
        assert policy["log_llm_inputs"] is False

    def test_data_policy_json_roundtrip(self):
        """Data policy serializes and deserializes correctly."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        new_policy = {
            "redaction_level": "strict",
            "allow_email_content_to_llm": False,
            "log_llm_inputs": True,
        }
        settings.data_policy_json = json.dumps(new_policy)
        assert settings.data_policy == new_policy

    def test_strict_redaction(self):
        """Strict redaction level can be set."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        policy["redaction_level"] = "strict"
        settings.data_policy_json = json.dumps(policy)
        assert settings.data_policy["redaction_level"] == "strict"

    def test_off_redaction(self):
        """Off redaction level can be set."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        policy["redaction_level"] = "off"
        settings.data_policy_json = json.dumps(policy)
        assert settings.data_policy["redaction_level"] == "off"

    def test_disable_email_to_llm(self):
        """Email content can be disabled from reaching LLMs."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        policy["allow_email_content_to_llm"] = False
        settings.data_policy_json = json.dumps(policy)
        assert settings.data_policy["allow_email_content_to_llm"] is False

    def test_enable_llm_input_logging(self):
        """LLM input logging can be enabled."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        policy["log_llm_inputs"] = True
        settings.data_policy_json = json.dumps(policy)
        assert settings.data_policy["log_llm_inputs"] is True

    def test_partial_policy_update_preserves_defaults(self):
        """Updating one field preserves the others."""
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="00000000-0000-0000-0000-000000000001")
        policy = settings.data_policy
        policy["redaction_level"] = "strict"
        settings.data_policy_json = json.dumps(policy)
        result = settings.data_policy
        assert result["redaction_level"] == "strict"
        assert result["allow_email_content_to_llm"] is True  # preserved
        assert result["log_llm_inputs"] is False  # preserved
