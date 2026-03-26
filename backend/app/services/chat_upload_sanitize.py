"""Sanitize uploaded chat files before the agent can read them.

Extracts text from text-extractable file types (PDF, plain text, CSV, JSON,
Markdown), runs it through the prompt-injection sanitizer and PII redactor,
and returns the cleaned text.  Images and unsupported types return ``None``
so the agent falls back to vision or raw file reading.
"""

from __future__ import annotations

import io
import logging

from app.core.redact import RedactionLevel, redact_sensitive
from app.core.sanitize import sanitize_extracted_document

logger = logging.getLogger(__name__)

# File types we can extract text from at upload time.
TEXT_EXTRACTABLE_TYPES = frozenset({
    "application/pdf",
    "text/plain",
    "text/csv",
    "text/markdown",
    "application/json",
})


async def extract_and_sanitize_upload(
    data: bytes,
    content_type: str,
    filename: str,
    redaction_level: str = "moderate",
) -> str | None:
    """Extract text from an uploaded file, sanitize, and redact PII.

    Returns the cleaned text, or ``None`` if text extraction is not possible
    (images, scanned PDFs, unsupported types).  Never raises — failures are
    logged and result in ``None`` so the upload flow is not interrupted.
    """
    if content_type not in TEXT_EXTRACTABLE_TYPES:
        return None

    try:
        text = _extract_text(data, content_type)
    except Exception:
        logger.warning(
            "chat_upload_sanitize: text extraction failed for %s (%s)",
            filename,
            content_type,
            exc_info=True,
        )
        return None

    if not text or not text.strip():
        return None

    # Step 1: sanitize for prompt injection
    text = sanitize_extracted_document(text, source=filename) or ""
    if not text.strip():
        return None

    # Step 2: redact PII based on org's redaction level
    try:
        level = RedactionLevel(redaction_level)
    except ValueError:
        level = RedactionLevel.MODERATE

    if level != RedactionLevel.OFF:
        result = redact_sensitive(text, level=level)
        text = result.text

    return text


def _extract_text(data: bytes, content_type: str) -> str:
    """Synchronous text extraction by content type."""
    if content_type == "application/pdf":
        return _extract_pdf(data)
    # All other text-extractable types: decode as UTF-8
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    """Extract native text from a PDF via pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)
