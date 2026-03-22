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

import re
from enum import Enum
from typing import NamedTuple

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
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
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
