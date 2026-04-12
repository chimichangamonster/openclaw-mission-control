# ruff: noqa: INP001
"""Tests for terms of service — version tracking, acceptance model, legal content."""

from __future__ import annotations

from pathlib import Path


class TestTermsVersion:
    """Terms version constant and tracking."""

    def test_current_version_defined(self):
        from app.models.users import CURRENT_TERMS_VERSION

        assert CURRENT_TERMS_VERSION == "2026.1"

    def test_version_format(self):
        from app.models.users import CURRENT_TERMS_VERSION

        # Version should be in YYYY.N format
        parts = CURRENT_TERMS_VERSION.split(".")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert parts[1].isdigit()


class TestUserTermsFields:
    """User model has terms acceptance fields."""

    def test_user_has_terms_fields(self):
        from app.models.users import User

        user = User(clerk_user_id="test")
        assert user.terms_accepted_version is None
        assert user.terms_accepted_at is None
        assert user.privacy_accepted_at is None

    def test_terms_acceptance_tracking(self):
        from datetime import datetime, timezone

        from app.models.users import CURRENT_TERMS_VERSION, User

        user = User(clerk_user_id="test")
        now = datetime.now(timezone.utc)
        user.terms_accepted_version = CURRENT_TERMS_VERSION
        user.terms_accepted_at = now
        user.privacy_accepted_at = now

        assert user.terms_accepted_version == CURRENT_TERMS_VERSION
        assert user.terms_accepted_at == now

    def test_stale_terms_detection(self):
        """User with old version needs to re-accept."""
        from app.models.users import CURRENT_TERMS_VERSION, User

        user = User(clerk_user_id="test", terms_accepted_version="2025.1")
        assert user.terms_accepted_version != CURRENT_TERMS_VERSION


class TestLegalContent:
    """Legal document templates exist and contain required sections."""

    TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "legal"

    def test_terms_file_exists(self):
        assert (self.TEMPLATES_DIR / "terms-of-service.html").is_file()

    def test_privacy_file_exists(self):
        assert (self.TEMPLATES_DIR / "privacy-policy.html").is_file()

    def test_terms_contains_required_sections(self):
        content = (self.TEMPLATES_DIR / "terms-of-service.html").read_text()
        assert "Data Processing and AI Disclosure" in content
        assert "LLM Provider" in content
        assert "Data Sovereignty" in content or "cross-border" in content.lower()
        assert "Redaction" in content or "redaction" in content
        assert "DeepSeek" in content
        assert "China" in content
        assert "Alberta" in content
        assert "DRAFT" in content  # reminder that it needs legal review

    def test_privacy_contains_required_sections(self):
        content = (self.TEMPLATES_DIR / "privacy-policy.html").read_text()
        assert "Information We Collect" in content
        assert "LLM Provider" in content
        assert "Sensitive Data Redaction" in content
        assert "Your Rights" in content
        assert "PIPEDA" in content
        assert "PIPA" in content
        assert "Cross-Border" in content
        assert "DRAFT" in content

    def test_terms_lists_all_providers(self):
        content = (self.TEMPLATES_DIR / "terms-of-service.html").read_text()
        for provider in ["Anthropic", "DeepSeek", "xAI", "Google", "OpenAI"]:
            assert provider in content, f"Provider {provider} not listed in terms"

    def test_privacy_lists_all_providers(self):
        content = (self.TEMPLATES_DIR / "privacy-policy.html").read_text()
        for provider in ["Anthropic", "DeepSeek", "xAI", "Google", "OpenAI", "OpenRouter"]:
            assert provider in content, f"Provider {provider} not listed in privacy policy"


class TestDataPolicy:
    """Org data policy settings support redaction levels."""

    def test_redaction_levels_enum(self):
        from app.core.redact import RedactionLevel

        assert RedactionLevel.OFF.value == "off"
        assert RedactionLevel.MODERATE.value == "moderate"
        assert RedactionLevel.STRICT.value == "strict"

    def test_default_policy_moderate(self):
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="fake")
        policy = settings.data_policy
        assert policy["redaction_level"] == "moderate"
