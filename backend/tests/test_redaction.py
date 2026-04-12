# ruff: noqa: INP001
"""Tests for sensitive data redaction — credentials, financial, PII, pentest patterns."""

from __future__ import annotations

from app.core.redact import (
    RedactionLevel,
    RedactionVault,
    redact_email_content,
    redact_sensitive,
)


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
        text = (
            "Administrator:500:aad3b435b51404eeaad3b435b51404ee:fc525c9683e8fe067095ba2ddc971889:::"
        )
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
        vault.redact(text)
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


class TestGPSNotMatchedAsPhone:
    """Bug 1: GPS coordinates should not be matched as phone numbers."""

    def test_gps_longitude_not_phone(self):
        """GPS longitude like -113.5229053 should not become [REDACTED_PHONE]."""
        text = "Location: 53.590542, -113.522905"
        result = redact_sensitive(text, level=RedactionLevel.STRICT)
        assert "[REDACTED_PHONE]" not in result.text

    def test_gps_coordinates_redacted_in_vault(self):
        """GPS coordinate pairs should be caught by the vault's GPS pattern."""
        text = "GPS fix: 53.590542, -113.522905"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "53.590542" not in redacted
        assert "-113.522905" not in redacted
        assert "[GPS_COORDINATES_" in redacted
        rehydrated = vault.rehydrate(redacted)
        assert "53.590542" in rehydrated

    def test_gps_slash_separator(self):
        text = "Position: 53.590542/-113.522905"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "53.590542" not in redacted

    def test_real_phone_still_redacted(self):
        """Actual phone numbers should still be caught."""
        text = "Call 403-555-1234"
        result = redact_sensitive(text, level=RedactionLevel.STRICT)
        assert "[REDACTED_PHONE]" in result.text


class TestBSSIDNotCorrupted:
    """Bug 2: BSSID: should not be parsed as B + SSID:."""

    def test_bssid_not_split(self):
        """BSSID: AA:BB:CC:DD:EE:FF should redact the MAC, not the SSID."""
        text = "BSSID: AA:BB:CC:DD:EE:FF"
        vault = RedactionVault()
        redacted = vault.redact(text)
        # The MAC should be redacted
        assert "AA:BB:CC:DD:EE:FF" not in redacted
        # There should be no orphaned 'B' — BSSID label stays intact
        assert "B[SSID_" not in redacted
        assert "BSSID:" in redacted

    def test_ssid_still_redacted(self):
        """Regular SSID: patterns still work."""
        text = "SSID: MyHomeWiFi"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "MyHomeWiFi" not in redacted

    def test_essid_still_redacted(self):
        text = "ESSID: CorpNet-5G"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "CorpNet-5G" not in redacted

    def test_bssid_with_ssid_both_handled(self):
        """Line with both BSSID and SSID — no corruption."""
        text = "BSSID: AA:BB:CC:DD:EE:FF  SSID: CorpWiFi"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "AA:BB:CC:DD:EE:FF" not in redacted
        assert "CorpWiFi" not in redacted
        # No nested tag corruption
        assert "B[" not in redacted


class TestHostnameRedaction:
    """Bug 3: Generic hostnames should be caught."""

    def test_windows_hostname(self):
        """Windows machine names like W482CAD-LNWZ77E6BDD4FB0."""
        text = "Host: W482CAD-LNWZ77E6BDD4FB0"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "W482CAD-LNWZ77E6BDD4FB0" not in redacted

    def test_hostname_in_context(self):
        """Hostname: keyword provides context."""
        text = "Hostname: pi-pentest"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "pi-pentest" not in redacted

    def test_computer_name_context(self):
        text = "Computer Name: CORP-DC01"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "CORP-DC01" not in redacted

    def test_netbios_name_context(self):
        text = "NetBIOS Name: FILESERVER01"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "FILESERVER01" not in redacted

    def test_normal_words_not_caught(self):
        """Regular English words should not be caught by hostname patterns."""
        text = "The server was running normally"
        vault = RedactionVault()
        redacted = vault.redact(text)
        # "server" and "running" should not be redacted
        assert "server" in redacted
        assert "running" in redacted


class TestNestedTagCorruption:
    """Bug 4: Regex replacement should not corrupt earlier tags."""

    def test_no_nested_brackets(self):
        """Tags from earlier patterns should not be re-matched by later ones."""
        # BSSID + SSID on same line — the MAC tag should not be eaten by SSID regex
        text = "BSSID: AA:BB:CC:DD:EE:FF  SSID: TestNet"
        vault = RedactionVault()
        redacted = vault.redact(text)
        # No nested tags like [SSID_[MAC_ADDRESS_1]]
        import re as _re

        nested = _re.findall(r"\[[A-Z_]+\[", redacted)
        assert nested == [], f"Found nested tags: {nested}"

    def test_ip_in_ssid_context_no_corruption(self):
        """IP address followed by SSID context should produce clean tags."""
        text = "network: 192.168.1.0 SSID: HomeNet"
        vault = RedactionVault()
        redacted = vault.redact(text)
        # Both should be independently redacted
        assert "192.168.1.0" not in redacted
        assert "HomeNet" not in redacted
        # No null bytes left over
        assert "\x00" not in redacted

    def test_multiple_pattern_types_clean(self):
        """Mix of IPs, MACs, SSIDs, hostnames should produce clean output."""
        text = "Host dc01.corp.local (192.168.1.1) MAC AA:BB:CC:DD:EE:FF SSID: Corp"
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "\x00" not in redacted
        # All sensitive values gone
        assert "dc01.corp.local" not in redacted
        assert "192.168.1.1" not in redacted
        assert "AA:BB:CC:DD:EE:FF" not in redacted
        assert "Corp" not in redacted
        # Rehydration works
        rehydrated = vault.rehydrate(redacted)
        assert "192.168.1.1" in rehydrated
        assert "AA:BB:CC:DD:EE:FF" in rehydrated


class TestJSONAwareRedaction:
    """Bug 5: JSON scan results should be parsed and redacted field-by-field."""

    def test_json_string_input(self):
        """JSON string gets parsed, values redacted, re-serialized."""
        import json

        data = json.dumps(
            {
                "target": "192.168.1.100",
                "ssid": "SSID: CorpWiFi",
                "mac": "AA:BB:CC:DD:EE:FF",
                "port": 22,
                "open": True,
            }
        )
        vault = RedactionVault()
        result = vault.redact_json(data)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert "192.168.1.100" not in parsed["target"]
        assert "CorpWiFi" not in parsed["ssid"]
        assert "AA:BB:CC:DD:EE:FF" not in parsed["mac"]
        # Non-string values pass through
        assert parsed["port"] == 22
        assert parsed["open"] is True

    def test_json_dict_input(self):
        """Dict input gets walked directly (no parse step)."""
        data = {"host": "10.0.0.5", "info": "clean"}
        vault = RedactionVault()
        result = vault.redact_json(data)
        assert isinstance(result, dict)
        assert "10.0.0.5" not in result["host"]

    def test_json_nested_structure(self):
        """Deeply nested JSON structures get redacted recursively."""
        import json

        data = {
            "scan": {
                "hosts": [
                    {"ip": "192.168.1.1", "mac": "AA:BB:CC:DD:EE:FF"},
                    {"ip": "192.168.1.2", "mac": "11:22:33:44:55:66"},
                ],
                "metadata": {"location": "53.5905, -113.5229"},
            }
        }
        vault = RedactionVault()
        result = vault.redact_json(data)
        assert "192.168.1.1" not in json.dumps(result)
        assert "AA:BB:CC:DD:EE:FF" not in json.dumps(result)
        assert "192.168.1.2" not in json.dumps(result)
        # Rehydration via serialized form
        rehydrated = vault.rehydrate(json.dumps(result))
        assert "192.168.1.1" in rehydrated
        assert "AA:BB:CC:DD:EE:FF" in rehydrated

    def test_json_list_input(self):
        """List input gets walked."""
        data = [{"ip": "10.0.0.1"}, {"ip": "10.0.0.2"}]
        vault = RedactionVault()
        result = vault.redact_json(data)
        assert isinstance(result, list)
        assert "10.0.0.1" not in str(result)

    def test_invalid_json_falls_back(self):
        """Non-JSON string falls back to plain text redaction."""
        text = "Target: 192.168.1.100 is vulnerable"
        vault = RedactionVault()
        result = vault.redact_json(text)
        assert isinstance(result, str)
        assert "192.168.1.100" not in result

    def test_json_with_escaped_values(self):
        """JSON with escaped quotes in values still gets redacted."""
        import json

        data = json.dumps({"note": 'SSID: "CorpNet-5G" found'})
        vault = RedactionVault()
        result = vault.redact_json(data)
        parsed = json.loads(result)
        assert "CorpNet-5G" not in parsed["note"]


class TestRealisticScanOutput:
    """End-to-end tests against realistic pentest scan output."""

    def test_full_scan_no_false_positives(self):
        """Real bedroom scan data: GPS, BSSIDs, SSIDs, IPs — no corruption."""
        text = """WiFi scan results:
BSSID: AA:BB:CC:DD:EE:FF  SSID: HomeNet-5G  Signal: -45dBm
BSSID: 11:22:33:44:55:66  SSID: NeighborWiFi  Signal: -72dBm
GPS: 53.590542, -113.522905
Device: W482CAD-LNWZ77E6BDD4FB0
Hostname: pi-pentest
Gateway: 192.168.1.1
Client: 192.168.1.71"""
        vault = RedactionVault()
        redacted = vault.redact(text)
        # All sensitive data gone
        assert "AA:BB:CC:DD:EE:FF" not in redacted
        assert "HomeNet-5G" not in redacted
        assert "11:22:33:44:55:66" not in redacted
        assert "NeighborWiFi" not in redacted
        assert "53.590542" not in redacted
        assert "-113.522905" not in redacted
        assert "W482CAD-LNWZ77E6BDD4FB0" not in redacted
        assert "pi-pentest" not in redacted
        assert "192.168.1.1" not in redacted
        assert "192.168.1.71" not in redacted
        # No corruption
        assert "\x00" not in redacted
        assert "B[" not in redacted
        assert "[REDACTED_PHONE]" not in redacted
        # Structure preserved
        assert "WiFi scan results:" in redacted
        assert "Signal: -45dBm" in redacted
        # Full roundtrip
        rehydrated = vault.rehydrate(redacted)
        assert "AA:BB:CC:DD:EE:FF" in rehydrated
        assert "192.168.1.1" in rehydrated
        assert "53.590542" in rehydrated

    def test_nmap_output(self):
        """Nmap-style scan output gets properly redacted."""
        text = """Nmap scan report for 192.168.1.41
Host is up (0.0023s latency).
Hostname: W482CAD-LNWZ77E6BDD4FB0
MAC Address: AA:BB:CC:DD:EE:FF (Intel Corporate)
22/tcp   open  ssh
80/tcp   open  http
445/tcp  open  microsoft-ds
OS: Windows 10 Build 19041"""
        vault = RedactionVault()
        redacted = vault.redact(text)
        assert "192.168.1.41" not in redacted
        assert "W482CAD-LNWZ77E6BDD4FB0" not in redacted
        assert "AA:BB:CC:DD:EE:FF" not in redacted
        # Service info preserved
        assert "22/tcp" in redacted
        assert "ssh" in redacted
        assert "microsoft-ds" in redacted

    def test_json_scan_results(self):
        """JSON scan payload gets field-level redaction."""
        import json

        data = json.dumps(
            {
                "scan_type": "wifi",
                "results": [
                    {
                        "bssid": "AA:BB:CC:DD:EE:FF",
                        "ssid": "SSID: CorpWiFi-5G",
                        "signal": -45,
                        "channel": 36,
                    },
                    {
                        "bssid": "11:22:33:44:55:66",
                        "ssid": "ESSID: GuestNet",
                        "signal": -72,
                        "channel": 1,
                    },
                ],
                "gps": "53.590542, -113.522905",
                "target_ip": "192.168.1.1",
            }
        )
        vault = RedactionVault()
        result = vault.redact_json(data)
        parsed = json.loads(result)
        # MACs redacted
        assert "AA:BB:CC:DD:EE:FF" not in json.dumps(parsed)
        # SSIDs redacted (with keyword context in value)
        assert "CorpWiFi-5G" not in json.dumps(parsed)
        assert "GuestNet" not in json.dumps(parsed)
        # Numeric values preserved
        assert parsed["results"][0]["signal"] == -45
        assert parsed["results"][0]["channel"] == 36


class TestDataPolicy:
    """Per-org data policy defaults."""

    def test_default_data_policy(self):
        from app.models.organization_settings import OrganizationSettings

        settings = OrganizationSettings(organization_id="fake")
        policy = settings.data_policy
        assert policy["redaction_level"] == "moderate"
        assert policy["allow_email_content_to_llm"] is True
        assert policy["log_llm_inputs"] is False
