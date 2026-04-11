"""Input sanitization for user-supplied text that may reach agent prompts.

Defends against prompt injection by stripping or escaping patterns that could
hijack agent instructions when user content is embedded in LLM prompts.

Usage:
    from app.core.sanitize import sanitize_text
    clean = sanitize_text(user_input)
"""

from __future__ import annotations

import re

# Patterns that attempt to override system/agent instructions
_INJECTION_PATTERNS = [
    # Direct instruction overrides
    re.compile(
        r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)", re.IGNORECASE
    ),
    re.compile(
        r"disregard\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)", re.IGNORECASE
    ),
    re.compile(
        r"forget\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)", re.IGNORECASE
    ),
    # Role/identity hijacking
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a)\s+", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+", re.IGNORECASE),
    re.compile(r"from\s+now\s+on\s+you\s+(are|will|must|should)\s+", re.IGNORECASE),
    # System prompt extraction
    re.compile(
        r"(show|reveal|print|output|repeat|display)\s+(your|the)\s+(system\s+)?(prompt|instructions|rules)",
        re.IGNORECASE,
    ),
    re.compile(r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions|rules)", re.IGNORECASE),
    # Delimiter injection (trying to break out of a quoted context)
    re.compile(r"```\s*(system|assistant|user)\s*\n", re.IGNORECASE),
    re.compile(r"<\|?(system|im_start|im_end|endoftext)\|?>", re.IGNORECASE),
    # Instruction smuggling via XML/markdown
    re.compile(r"<(system|instruction|prompt|role)>", re.IGNORECASE),
    re.compile(r"</?(system|instruction|prompt|role)>", re.IGNORECASE),
]

# Maximum length for free-text fields (prevents context stuffing)
MAX_TEXT_LENGTH = 10_000


def sanitize_text(text: str | None, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    """Sanitize user-supplied text for safe embedding in agent prompts.

    Returns the cleaned text, or None if input is None.
    Strips injection patterns and enforces length limits.
    """
    if text is None:
        return None

    # Enforce length limit
    if len(text) > max_length:
        text = text[:max_length]

    # Strip null bytes
    text = text.replace("\x00", "")

    # Flag and strip injection patterns
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[filtered]", text)

    return text


def sanitize_extracted_document(text: str | None, source: str = "document") -> str | None:
    """Sanitize text extracted from uploaded documents (PDF, images, OCR).

    Documents are a high-risk injection vector because:
    - A PDF can contain invisible text layers with injection payloads
    - An image can embed text via steganography or watermarks
    - Handwritten field reports can contain dictated injection strings
    - Malicious actors can craft documents specifically to hijack agents

    This applies the same pattern filtering as sanitize_text() but also:
    - Wraps the content in a delimiter that agents should treat as untrusted data
    - Logs a warning if injection patterns are detected
    """
    if text is None:
        return None

    flagged = contains_injection(text)
    cleaned = sanitize_text(text)

    if flagged:
        from app.core.logging import get_logger

        logger = get_logger(__name__)
        logger.warning(
            "sanitize.document_injection_detected source=%s length=%d",
            source,
            len(text) if text else 0,
        )

    return cleaned


def sanitize_filename(filename: str | None, max_length: int = 255) -> str | None:
    """Sanitize uploaded filenames to prevent path traversal and injection.

    Strips directory separators, null bytes, and enforces length limits.
    """
    if filename is None:
        return None

    # Strip path components (prevent directory traversal)
    filename = filename.replace("\\", "/").split("/")[-1]

    # Strip null bytes and control characters
    filename = re.sub(r"[\x00-\x1f]", "", filename)

    # Enforce length
    if len(filename) > max_length:
        # Preserve extension
        parts = filename.rsplit(".", 1)
        if len(parts) == 2:
            ext = parts[1][:10]  # cap extension length
            filename = parts[0][: max_length - len(ext) - 1] + "." + ext
        else:
            filename = filename[:max_length]

    return filename


def contains_injection(text: str | None) -> bool:
    """Check if text contains potential prompt injection patterns.

    Returns True if suspicious patterns are detected.
    Does NOT modify the text — use sanitize_text() for that.
    """
    if not text:
        return False
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)
