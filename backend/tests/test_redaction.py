# ruff: noqa: INP001
"""Tests for sensitive data redaction — credentials, financial, PII patterns."""

from __future__ import annotations

import pytest

from app.core.redact import RedactionLevel, RedactionResult, redact_email_content, redact_sensitive


class TestCredentialRedaction:
    """Credential patterns are redacted in moderate+ mode."""

    def test_password_reset_link(self):
        text = "Click here to reset: https://example.com/reset-password?token=abc123"
        result = redact_sensitive(text)
        assert "[REDACTED_LINK]" in result.text
        assert "reset_link" in result.categories

    def test_api_key(self):
        text = "Your API key is sk-1234567890abcdefghij1234567890"
        result = redact_sensitive(text)
        assert "[REDACTED_API_KEY]" in result.text
        assert "api_key" in result.categories

    def test_aws_key(self):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = redact_sensitive(text)
        assert "[REDACTED_AWS_KEY]" in result.text
        assert "aws_key" in result.categories

    def test_jwt_token(self):
        text = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = redact_sensitive(text)
        assert "[REDACTED_JWT]" in result.text
        assert "jwt" in result.categories

    def test_password_in_email(self):
        text = "Your temporary password: Xk9$mP2qR!"
        result = redact_sensitive(text)
        assert "[REDACTED_PASSWORD]" in result.text
        assert "password" in result.categories

    def test_otp_code(self):
        text = "Your verification code: 847293"
        result = redact_sensitive(text)
        assert "[REDACTED_OTP]" in result.text
        assert "otp" in result.categories

    def test_hex_token(self):
        text = "Token: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6"
        result = redact_sensitive(text)
        assert "[REDACTED_TOKEN]" in result.text
        assert "hex_token" in result.categories


class TestFinancialRedaction:
    """Financial patterns redacted in moderate+ mode."""

    def test_credit_card_luhn_valid(self):
        # 4111111111111111 is a well-known Luhn-valid test card
        text = "Card: 4111 1111 1111 1111"
        result = redact_sensitive(text)
        assert "[REDACTED_CARD]" in result.text
        assert "credit_card" in result.categories

    def test_credit_card_luhn_invalid_not_redacted(self):
        # Random 16-digit number that fails Luhn
        text = "Reference: 1234 5678 9012 3456"
        result = redact_sensitive(text)
        # Should NOT be redacted because Luhn fails
        assert "[REDACTED_CARD]" not in result.text

    def test_bank_account_number(self):
        text = "Account number: 1234567890"
        result = redact_sensitive(text)
        assert "[REDACTED_ACCOUNT]" in result.text
        assert "bank_account" in result.categories

    def test_sin_number(self):
        text = "SIN: 123-456-789"
        result = redact_sensitive(text)
        assert "[REDACTED_ID_NUMBER]" in result.text
        assert "sin_ssn" in result.categories

    def test_ssn(self):
        text = "SSN: 123-45-6789"
        result = redact_sensitive(text)
        assert "[REDACTED_ID_NUMBER]" in result.text

    def test_sin_without_context_not_redacted(self):
        """Phone-like numbers without SIN/SSN context should not be redacted."""
        text = "Call 403-555-1234"
        result = redact_sensitive(text)
        assert "403-555-1234" in result.text


class TestPIIRedaction:
    """PII patterns only redacted in strict mode."""

    def test_phone_not_redacted_in_moderate(self):
        text = "Call me at 403-555-1234"
        result = redact_sensitive(text, level=RedactionLevel.MODERATE)
        assert "403-555-1234" in result.text

    def test_phone_redacted_in_strict(self):
        text = "Call me at 403-555-1234"
        result = redact_sensitive(text, level=RedactionLevel.STRICT)
        assert "[REDACTED_PHONE]" in result.text
        assert "phone" in result.categories

    def test_email_in_body_redacted_strict(self):
        text = "Forward this to john@example.com please"
        result = redact_sensitive(text, level=RedactionLevel.STRICT)
        assert "[REDACTED_EMAIL]" in result.text

    def test_email_in_body_not_redacted_moderate(self):
        text = "Forward this to john@example.com please"
        result = redact_sensitive(text, level=RedactionLevel.MODERATE)
        assert "john@example.com" in result.text

    def test_address_redacted_strict(self):
        text = "Ship to 123 Main St"
        result = redact_sensitive(text, level=RedactionLevel.STRICT)
        assert "[REDACTED_ADDRESS]" in result.text

    def test_dob_redacted_strict(self):
        text = "Date of birth: 03/15/1990"
        result = redact_sensitive(text, level=RedactionLevel.STRICT)
        assert "[REDACTED_DOB]" in result.text


class TestRedactionLevels:
    """Redaction level behavior."""

    def test_off_no_redaction(self):
        text = "Password: secret123 and SSN: 123-45-6789"
        result = redact_sensitive(text, level=RedactionLevel.OFF)
        assert result.text == text
        assert result.redaction_count == 0

    def test_moderate_redacts_credentials(self):
        text = "Your password: secret123"
        result = redact_sensitive(text, level=RedactionLevel.MODERATE)
        assert "[REDACTED_PASSWORD]" in result.text

    def test_none_input(self):
        result = redact_sensitive(None)
        assert result.text == ""
        assert result.redaction_count == 0


class TestEmailContentRedaction:
    """Full email content redaction helper."""

    def test_redacts_both_text_and_html(self):
        body_text = "Password: secret123"
        body_html = "<p>Password: secret123</p>"
        text, html, count, cats = redact_email_content(body_text, body_html)
        assert "[REDACTED_PASSWORD]" in text
        assert "[REDACTED_PASSWORD]" in html
        assert count >= 2
        assert "password" in cats

    def test_none_bodies(self):
        text, html, count, cats = redact_email_content(None, None)
        assert text is None
        assert html is None
        assert count == 0

    def test_mixed_none(self):
        text, html, count, cats = redact_email_content("Password: abc", None)
        assert "[REDACTED_PASSWORD]" in text
        assert html is None


class TestRedactionPreservesNormalContent:
    """Normal business emails should pass through unchanged."""

    def test_normal_email_unchanged(self):
        text = """Hi Henz,

Just following up on the Q1 report. Revenue was up 15% and we closed
3 new contracts this month. Let me know if you need the detailed breakdown.

Best,
Sarah"""
        result = redact_sensitive(text)
        assert result.redaction_count == 0
        assert result.text == text

    def test_invoice_email_mostly_unchanged(self):
        text = "Invoice #1234 for $5,000.00 is due March 30, 2026."
        result = redact_sensitive(text)
        # Dollar amounts and invoice numbers should NOT be redacted
        assert "$5,000.00" in result.text
        assert "#1234" in result.text


class TestDataPolicy:
    """Per-org data policy defaults."""

    def test_default_data_policy(self):
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="fake")
        policy = settings.data_policy
        assert policy["redaction_level"] == "moderate"
        assert policy["allow_email_content_to_llm"] is True
        assert policy["log_llm_inputs"] is False
