"""Sensitive data redaction for content before it reaches LLM providers.

Strips or masks PII, credentials, and financial data from text that will be
sent to language models. Complements sanitize.py (which handles prompt injection).

Pipeline: raw text → sanitize_text() (injection defense) → redact_sensitive() (PII/secrets)

Usage:
    from app.core.redact import redact_sensitive, redact_email_content
    clean = redact_sensitive(email_body)
    clean_email = redact_email_content(body_text, body_html, level="strict")
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, NamedTuple

from app.core.logging import get_logger

logger = get_logger(__name__)


class RedactionLevel(str, Enum):
    """How aggressively to redact sensitive data."""

    OFF = "off"  # No redaction (platform owner mode)
    MODERATE = "moderate"  # Redact credentials and financial data only
    STRICT = "strict"  # Redact all PII including names, phones, addresses


class RedactionResult(NamedTuple):
    """Result of redaction with metadata."""

    text: str
    redaction_count: int
    categories: set[str]


# ---------------------------------------------------------------------------
# Credential patterns (always redacted in moderate+)
# ---------------------------------------------------------------------------

_CREDENTIAL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Password reset / magic links
    (re.compile(r"https?://\S*(?:reset|password|verify|confirm|activate|token|magic[-_]?link)\S*", re.IGNORECASE),
     "[REDACTED_LINK]", "reset_link"),

    # API keys (common formats: sk-..., key-..., api_..., AKIA..., etc.)
    (re.compile(r"\b(?:sk|pk|api|key|token|secret|bearer)[-_]?[A-Za-z0-9]{20,}\b", re.IGNORECASE),
     "[REDACTED_API_KEY]", "api_key"),

    # AWS access keys
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     "[REDACTED_AWS_KEY]", "aws_key"),

    # Generic high-entropy strings that look like secrets (40+ hex chars)
    (re.compile(r"\b[0-9a-f]{40,}\b", re.IGNORECASE),
     "[REDACTED_TOKEN]", "hex_token"),

    # JWT tokens
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
     "[REDACTED_JWT]", "jwt"),

    # Passwords in common email formats
    (re.compile(r"(?:password|passwd|passcode|PIN|temporary password|new password|your password)\s*[:=]\s*\S+", re.IGNORECASE),
     "[REDACTED_PASSWORD]", "password"),

    # Verification/OTP codes (6-8 digit codes in context)
    (re.compile(r"(?:verification|confirm|auth|security|one[- ]?time)\s*(?:code|pin|number)\s*[:=]?\s*\d{4,8}", re.IGNORECASE),
     "[REDACTED_OTP]", "otp"),
]

# ---------------------------------------------------------------------------
# Financial patterns (redacted in moderate+)
# ---------------------------------------------------------------------------

_FINANCIAL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Credit card numbers (13-19 digits, possibly with spaces/dashes)
    (re.compile(r"\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b"),
     "[REDACTED_CARD]", "credit_card"),

    # Bank account / routing numbers in context
    (re.compile(r"(?:account|routing|transit|acct)\s*(?:number|no|#)?\s*[:=]?\s*\d{5,12}", re.IGNORECASE),
     "[REDACTED_ACCOUNT]", "bank_account"),

    # SIN / SSN (with context keywords to avoid matching phone numbers)
    (re.compile(r"(?:SIN|SSN|social\s+security|social\s+insurance)\s*(?:number|no|#)?\s*[:=]?\s*\d{3}[-\s]\d{2,3}[-\s]\d{3,4}", re.IGNORECASE),
     "[REDACTED_ID_NUMBER]", "sin_ssn"),
]

# ---------------------------------------------------------------------------
# PII patterns (only in strict mode)
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Phone numbers (North American + international)
    # Negative lookbehind for '.' prevents matching decimal numbers like GPS coords
    (re.compile(r"(?<!\d\.)(?<!\d)\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b(?!\.\d)"),
     "[REDACTED_PHONE]", "phone"),

    # Email addresses (within body text, not sender/recipient headers)
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
     "[REDACTED_EMAIL]", "email_in_body"),

    # Date of birth patterns
    (re.compile(r"(?:date of birth|DOB|born|birthday)\s*[:=]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", re.IGNORECASE),
     "[REDACTED_DOB]", "dob"),

    # Mailing addresses (basic pattern: number + street + city/province)
    (re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:St|Ave|Rd|Blvd|Dr|Ln|Ct|Way|Cres|Pl)\b\.?", re.IGNORECASE),
     "[REDACTED_ADDRESS]", "address"),
]


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def redact_sensitive(
    text: str | None,
    level: RedactionLevel = RedactionLevel.MODERATE,
) -> RedactionResult:
    """Redact sensitive data from text.

    Args:
        text: Input text to redact.
        level: How aggressively to redact.

    Returns:
        RedactionResult with cleaned text, count, and categories.
    """
    if text is None:
        return RedactionResult(text="", redaction_count=0, categories=set())

    if level == RedactionLevel.OFF:
        return RedactionResult(text=text, redaction_count=0, categories=set())

    count = 0
    categories: set[str] = set()

    # Always apply credential and financial patterns in moderate+
    for pattern, replacement, category in _CREDENTIAL_PATTERNS + _FINANCIAL_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            # Special handling for credit cards — only redact if Luhn-valid
            if category == "credit_card":
                for match in matches:
                    digits_only = re.sub(r"\D", "", match)
                    if _luhn_check(digits_only):
                        text = text.replace(match, replacement)
                        count += 1
                        categories.add(category)
            else:
                new_text = pattern.sub(replacement, text)
                if new_text != text:
                    count += len(matches)
                    categories.add(category)
                    text = new_text

    # PII patterns only in strict mode
    if level == RedactionLevel.STRICT:
        for pattern, replacement, category in _PII_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                new_text = pattern.sub(replacement, text)
                if new_text != text:
                    count += len(matches)
                    categories.add(category)
                    text = new_text

    if count > 0:
        logger.info(
            "redact.applied count=%d categories=%s level=%s",
            count, ",".join(sorted(categories)), level.value,
        )

    return RedactionResult(text=text, redaction_count=count, categories=categories)


# ---------------------------------------------------------------------------
# Reversible redaction for LLM workflows (redact → review → send → rehydrate)
# ---------------------------------------------------------------------------

# Patterns for pentest/security data that should never reach an LLM
_PENTEST_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # GPS coordinates — must come before IP/phone patterns to prevent false matches
    # Matches lat,lon pairs like "53.590542, -113.522905" or "53.590542/-113.522905"
    (re.compile(r"-?\d{1,3}\.\d{4,8}\s*[,/]\s*-?\d{1,3}\.\d{4,8}"),
     "gps_coordinates", "GPS coordinates"),

    # Database connection strings — must come before IP/hostname patterns
    # so the whole URL is redacted before IP regex strips the embedded address
    (re.compile(r"(?:mongodb|mysql|postgres(?:ql)?|mssql|redis|amqp)://[^\s\"']+@[^\s\"']+", re.IGNORECASE),
     "db_connection_string", "database connection string"),

    # MAC addresses — must come before IPv6 (MACs look like short IPv6)
    (re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),
     "mac_address", "MAC address"),

    # CIDR ranges — must come before bare IPv4
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b"),
     "cidr_range", "CIDR range"),

    # IPv4 addresses
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
     "ip_address", "IP address"),

    # IPv6 addresses (simplified — common formats)
    (re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"),
     "ipv6_address", "IPv6 address"),

    # Hostnames / FQDNs (conservative — requires at least 2 dots or common TLDs)
    (re.compile(r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.){2,}[a-zA-Z]{2,}\b"),
     "hostname", "hostname"),

    # Internal domain names (single-label .local, .internal, .corp, .lan)
    (re.compile(r"\b[a-zA-Z0-9-]+\.(?:local|internal|corp|lan|home|intranet)\b", re.IGNORECASE),
     "internal_host", "internal hostname"),

    # Hostnames in keyword context (Hostname: X, Computer Name: X, NetBIOS: X)
    (re.compile(r"(?:hostname|computer\s*name|netbios\s*name|device\s*name)\s*[:=]\s*[\"']?([A-Za-z0-9][A-Za-z0-9._-]{2,})[\"']?", re.IGNORECASE),
     "hostname_context", "hostname"),

    # Windows-style hostnames: uppercase + digits + hyphens, 8+ chars (e.g. W482CAD-LNWZ77E6BDD4FB0)
    # Only match when ALL-CAPS with digits mixed in (avoids false positives on normal words)
    (re.compile(r"\b[A-Z][A-Z0-9]{2,}-[A-Z0-9]{4,}\b"),
     "windows_hostname", "Windows hostname"),

    # SSIDs in common pentest output patterns
    # \b prefix prevents matching tail of "BSSID:" as "B" + "SSID:"
    (re.compile(r'\b(?:E?SSID|network)\s*[:=]\s*["\']?([^\s"\']+)["\']?', re.IGNORECASE),
     "ssid", "WiFi SSID"),

    # WiFi PSK / WPA passwords in tool output
    (re.compile(r'(?:PSK|WPA\s*(?:passphrase|password|key)|pre[- ]?shared[- ]?key|wifi[- ]?pass(?:word)?)\s*[:=]\s*["\']?(\S+)["\']?', re.IGNORECASE),
     "wifi_password", "WiFi password"),

    # NTLM hashes (LM:NT format from secretsdump, or standalone 32-char hex)
    (re.compile(r"\b[0-9a-fA-F]{32}:[0-9a-fA-F]{32}\b"),
     "ntlm_hash", "NTLM hash pair"),

    # NetNTLMv2 hashes (user::domain:challenge:response format from Responder)
    (re.compile(r"\b\S+::\S+:[0-9a-fA-F]{16}:[0-9a-fA-F]{32}:[0-9a-fA-F]+\b"),
     "netntlmv2_hash", "NetNTLMv2 hash"),

    # Standalone password hashes in tool output (hashcat/john context)
    (re.compile(r'(?:hash|Hash|HASH)\s*[:=]\s*["\']?([0-9a-fA-F]{32,128})["\']?'),
     "password_hash", "password hash"),

    # SSH private keys (PEM blocks)
    (re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |ED25519 |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |OPENSSH |EC |ED25519 |DSA )?PRIVATE KEY-----"),
     "ssh_private_key", "SSH private key"),

    # Kerberos ticket blobs (krb5 base64, typically from klist or ticket exports)
    (re.compile(r"\bkrb(?:tgt|5cc|5_)\S{20,}\b", re.IGNORECASE),
     "kerberos_ticket", "Kerberos ticket"),

    # AWS temporary session tokens (STS)
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"),
     "aws_sts_key", "AWS STS key"),

    # Credential pairs in pentest tool output (user:pass, user/pass patterns in context)
    (re.compile(r'(?:credential|cred|login|logon|username/password|user/pass)\s*[:=]\s*["\']?(\S+\s*[:/]\s*\S+)["\']?', re.IGNORECASE),
     "credential_pair", "credential pair"),

    # Windows domain\user patterns
    (re.compile(r"\b[A-Z][A-Z0-9_-]{1,15}\\[a-zA-Z0-9._-]+\b"),
     "domain_user", "domain\\user"),

    # File paths that may reveal internal structure
    (re.compile(r"(?:/(?:home|opt|var|etc|usr|root)/[^\s]{3,}|[A-Z]:\\[^\s]{3,})"),
     "file_path", "file path"),
]


class RedactionVault:
    """Stores original values keyed by placeholder tags for later rehydration.

    Usage:
        vault = RedactionVault()
        redacted = vault.redact(raw_text)
        # User reviews `redacted` text and `vault.entries` before approving
        # After LLM generates report text using placeholders:
        final = vault.rehydrate(llm_output)
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}  # tag -> original value
        self._labels: dict[str, str] = {}  # tag -> human-readable label
        self._counter: int = 0

    @property
    def entries(self) -> list[dict[str, str]]:
        """Return all redacted entries for human review.

        Returns list of {tag, original, label} dicts.
        """
        return [
            {"tag": tag, "original": self._store[tag], "label": self._labels[tag]}
            for tag in sorted(self._store)
        ]

    @property
    def entry_count(self) -> int:
        return len(self._store)

    def _next_tag(self, category: str) -> str:
        self._counter += 1
        return f"[{category.upper()}_{self._counter}]"

    def redact(self, text: str) -> str:
        """Redact pentest-sensitive data from text, storing originals for rehydration.

        Applies both standard credential/financial patterns (one-way, not rehydratable)
        and pentest-specific patterns (reversible via rehydrate()).

        Uses null-byte placeholders (\x00TAG\x00) during replacement to prevent
        later regex patterns from matching inside earlier replacement tags.
        """
        if not text:
            return text

        # First pass: apply standard one-way redaction (credentials, financial)
        result = redact_sensitive(text, RedactionLevel.STRICT)
        text = result.text

        # Second pass: reversible redaction of pentest-specific data
        # Use \x00-delimited placeholders to prevent nested tag corruption
        for pattern, category, label in _PENTEST_PATTERNS:
            for match in pattern.finditer(text):
                original = match.group(0)
                # Skip if already redacted by first pass or contains a placeholder
                if original.startswith("[REDACTED") or "\x00" in original:
                    continue
                # Reuse existing tag if we've seen this exact value before
                existing_tag = None
                for tag, val in self._store.items():
                    if val == original:
                        existing_tag = tag
                        break
                tag = existing_tag or self._next_tag(category)
                if not existing_tag:
                    self._store[tag] = original
                    self._labels[tag] = label
                # Use null-byte wrapper so subsequent regexes skip placeholders
                text = text.replace(original, f"\x00{tag}\x00")

        # Final pass: strip null-byte wrappers to produce clean [TAG_N] output
        text = text.replace("\x00", "")

        return text

    def redact_json(self, data: str | dict | list) -> str | dict | list:
        """Redact pentest-sensitive data from JSON structures.

        Parses JSON (if string), recursively walks all string values,
        redacts each individually, then returns the same structure.
        Avoids regex issues with JSON escaping and structural context.

        Args:
            data: JSON string, dict, or list to redact.

        Returns:
            Same type as input with string values redacted.
        """
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                # Not valid JSON — fall back to plain text redaction
                return self.redact(data)
            result = self._walk_and_redact(parsed)
            return json.dumps(result)
        return self._walk_and_redact(data)

    def _walk_and_redact(self, obj: Any) -> Any:
        """Recursively walk a parsed JSON structure, redacting string values."""
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {k: self._walk_and_redact(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._walk_and_redact(item) for item in obj]
        # Numbers, bools, None — pass through unchanged
        return obj

    def rehydrate(self, text: str) -> str:
        """Replace placeholder tags with original values in LLM-generated text."""
        for tag, original in self._store.items():
            text = text.replace(tag, original)
        return text

    def to_dict(self) -> dict:
        """Serialize vault for API transport / storage."""
        return {
            "entries": self.entries,
            "store": dict(self._store),
            "labels": dict(self._labels),
            "counter": self._counter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RedactionVault":
        """Reconstruct vault from serialized dict."""
        vault = cls()
        vault._store = dict(data.get("store", {}))
        vault._labels = dict(data.get("labels", {}))
        vault._counter = data.get("counter", 0)
        return vault


def redact_email_content(
    body_text: str | None,
    body_html: str | None,
    level: RedactionLevel = RedactionLevel.MODERATE,
) -> tuple[str | None, str | None, int, set[str]]:
    """Redact sensitive data from email body text and HTML.

    Returns:
        (redacted_text, redacted_html, total_redaction_count, categories)
    """
    total_count = 0
    all_categories: set[str] = set()

    redacted_text = body_text
    if body_text:
        result = redact_sensitive(body_text, level)
        redacted_text = result.text
        total_count += result.redaction_count
        all_categories |= result.categories

    redacted_html = body_html
    if body_html:
        result = redact_sensitive(body_html, level)
        redacted_html = result.text
        total_count += result.redaction_count
        all_categories |= result.categories

    return redacted_text, redacted_html, total_count, all_categories
