# ruff: noqa: INP001
"""Tests for sensitive data redaction — credentials, financial, PII, pentest patterns."""

from __future__ import annotations

import pytest

from app.core.redact import RedactionLevel, RedactionResult, RedactionVault, redact_email_content, redact_sensitive


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


class TestPentestRedaction:
    """Pentest-specific patterns in RedactionVault (reversible redaction)."""

    def test_ntlm_hash_pair(self):
        text = "Administrator:500:aad3b435b51404eeaad3b435b51404ee:fc525c9683e8fe067095ba2ddc971889:::"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "aad3b435b51404ee" not in redacted
        assert "fc525c9683e8fe067095ba2ddc971889" not in redacted
        assert vault.entry_count > 0
        rehydrated = vault.rehydrate(redacted)
        assert "aad3b435b51404ee" in rehydrated

    def test_netntlmv2_hash(self):
        text = "admin::WORKGROUP:1122334455667788:aabbccddaabbccddaabbccddaabbccdd:0011223344556677"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "1122334455667788" not in redacted
        assert vault.entry_count > 0

    def test_wifi_password(self):
        text = "WPA passphrase: MySecretWiFi123"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "MySecretWiFi123" not in redacted
        rehydrated = vault.rehydrate(redacted)
        assert "MySecretWiFi123" in rehydrated

    def test_wifi_psk(self):
        text = "PSK: SuperS3cretKey!"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "SuperS3cretKey!" not in redacted

    def test_ssh_private_key(self):
        text = """Found key:
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGcY5unA
-----END RSA PRIVATE KEY-----
at /home/admin/.ssh/id_rsa"""
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn" not in redacted
        assert "BEGIN RSA PRIVATE KEY" not in redacted
        rehydrated = vault.rehydrate(redacted)
        assert "BEGIN RSA PRIVATE KEY" in rehydrated

    def test_openssh_private_key(self):
        text = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "OPENSSH PRIVATE KEY" not in redacted

    def test_db_connection_string_postgres(self):
        text = "DATABASE_URL=postgres://admin:p4ssw0rd@10.0.0.5:5432/production"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "p4ssw0rd" not in redacted
        assert "admin" not in redacted or "DB_CONNECTION_STRING" in redacted

    def test_db_connection_string_mysql(self):
        text = "mysql://root:secret@db.internal:3306/app"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "secret" not in redacted

    def test_db_connection_string_mongodb(self):
        text = "mongodb://user:pass123@mongo.corp.local:27017/admin"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "pass123" not in redacted

    def test_aws_sts_key(self):
        text = "AWS_ACCESS_KEY_ID=ASIAIOSFODNN7EXAMPLE"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "ASIAIOSFODNN7EXAMPLE" not in redacted

    def test_credential_pair_in_context(self):
        text = "credential: admin/Password123!"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "Password123!" not in redacted

    def test_ip_address_redacted(self):
        text = "Target host 192.168.1.100 is vulnerable"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "192.168.1.100" not in redacted
        assert "[IP_ADDRESS_" in redacted
        rehydrated = vault.rehydrate(redacted)
        assert "192.168.1.100" in rehydrated

    def test_mac_address_redacted(self):
        text = "Device MAC AA:BB:CC:DD:EE:FF detected"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "AA:BB:CC:DD:EE:FF" not in redacted
        assert "[MAC_ADDRESS_" in redacted

    def test_internal_hostname_redacted(self):
        text = "Domain controller at dc01.corp.local"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "dc01.corp.local" not in redacted

    def test_domain_user_redacted(self):
        text = r"Compromised account: ACME\john.admin"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "ACME\\john.admin" not in redacted

    def test_ssid_redacted(self):
        text = "SSID: CorpWiFi-5G"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "CorpWiFi-5G" not in redacted

    def test_file_path_redacted(self):
        text = "Config found at /etc/shadow with weak permissions"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "/etc/shadow" not in redacted

    def test_hash_in_context(self):
        text = "Hash: 5f4dcc3b5aa765d61d8327deb882cf99aabbccddee112233"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "5f4dcc3b5aa765d61d8327deb882cf99" not in redacted

    def test_vault_serialization_roundtrip(self):
        """Vault can be serialized to dict and reconstructed."""
        vault = RedactionVault()
        text = "Host 192.168.1.1 has SSID: TestNet and MAC AA:BB:CC:DD:EE:FF"
        redacted = vault.redact(text)
        data = vault.to_dict()
        vault2 = RedactionVault.from_dict(data)
        rehydrated = vault2.rehydrate(redacted)
        assert "192.168.1.1" in rehydrated
        assert "TestNet" in rehydrated
        assert "AA:BB:CC:DD:EE:FF" in rehydrated

    def test_vault_deduplicates_same_value(self):
        """Same IP appearing twice gets the same tag."""
        vault = RedactionVault()
        text = "Scan 192.168.1.1 then rescan 192.168.1.1"
        redacted = vault.redact(text)
        # Should only have one entry for the IP
        ip_entries = [e for e in vault.entries if e["original"] == "192.168.1.1"]
        assert len(ip_entries) == 1

    def test_full_pentest_output(self):
        """Realistic pentest tool output gets fully redacted."""
        text = """Nmap scan results for 10.10.10.40:
PORT    STATE SERVICE
22/tcp  open  ssh
445/tcp open  microsoft-ds
Host: DC01.acme.internal
SSID: ACME-Corp-5G
WPA passphrase: Welcome2ACME!
Admin hash: aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0
Found SSH key at /home/admin/.ssh/id_rsa
Lateral: ACME\\svc.backup has access to file server"""
        vault = RedactionVault()
        redacted = vault.redact(text)
        # None of the sensitive data should remain
        assert "10.10.10.40" not in redacted
        assert "acme.internal" not in redacted
        assert "ACME-Corp-5G" not in redacted
        assert "Welcome2ACME!" not in redacted
        assert "aad3b435b51404ee" not in redacted
        assert "ACME\\svc.backup" not in redacted
        # But the structure should remain readable
        assert "PORT" in redacted
        assert "STATE" in redacted
        assert "ssh" in redacted
        # And it should be fully rehydratable
        rehydrated = vault.rehydrate(redacted)
        assert "10.10.10.40" in rehydrated
        assert "Welcome2ACME!" in rehydrated


class TestDataPolicy:
    """Per-org data policy defaults."""

    def test_default_data_policy(self):
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="fake")
        policy = settings.data_policy
        assert policy["redaction_level"] == "moderate"
        assert policy["allow_email_content_to_llm"] is True
        assert policy["log_llm_inputs"] is False
