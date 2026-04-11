"""Document intake pipeline: extract text + classify documents via LLM.

Processes uploaded documents (PDF, images, text) through:
1. Text extraction (native PDF text, vision OCR for images/scanned PDFs)
2. Sanitization (prompt injection defense)
3. LLM-based classification into document types
"""


from __future__ import annotations

from typing import Any
from uuid import UUID

import base64
import io
import json
import logging
from enum import Enum

from pypdf import PdfReader

from app.core.logging import get_logger
from app.core.sanitize import sanitize_extracted_document

logger = get_logger(__name__)


class DocumentType(str, Enum):
    INVOICE = "invoice"
    RECEIPT = "receipt"
    CONTRACT = "contract"
    REPORT = "report"
    FIELD_REPORT = "field_report"
    PURCHASE_ORDER = "purchase_order"
    TIMESHEET = "timesheet"
    SAFETY_REPORT = "safety_report"
    PERMIT = "permit"
    CORRESPONDENCE = "correspondence"
    OTHER = "other"


CLASSIFICATION_PROMPT = """Classify this document into exactly one category. Return JSON only.

Categories:
- invoice: billing document with line items and total
- receipt: proof of purchase/payment
- contract: legal agreement with terms and signatures
- report: business/technical report or analysis
- field_report: on-site construction/inspection report
- purchase_order: order for goods/services
- timesheet: hours worked record
- safety_report: safety inspection or incident report
- permit: government permit or license
- correspondence: letter, memo, or email printout
- other: does not fit any category

Document text (first 3000 chars):
---
{text}
---

Return: {{"type": "<category>", "confidence": <0-100>, "summary": "<one sentence>"}}"""


async def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n---PAGE BREAK---\n\n".join(pages)


async def extract_text_from_image(
    file_bytes: bytes,
    content_type: str,
    org_id: UUID,
    db_session: Any,
) -> str:
    """Extract text from an image using LLM vision API."""
    import httpx

    from app.services.llm_routing import resolve_llm_endpoint

    endpoint = await resolve_llm_endpoint(db_session, org_id)
    if not endpoint:
        raise ValueError("No LLM endpoint configured for this organization")

    b64 = base64.b64encode(file_bytes).decode()
    media_type = content_type or "image/jpeg"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{endpoint.api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {endpoint.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-2.0-flash-001",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{b64}"},
                            },
                            {
                                "type": "text",
                                "text": "Extract ALL text from this document image. Preserve structure, headings, tables, and line breaks. Return only the extracted text.",
                            },
                        ],
                    }
                ],
                "max_tokens": 4096,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]  # type: ignore[no-any-return]


async def classify_document(
    text: str,
    org_id: UUID,
    db_session: Any,
) -> dict[str, Any]:
    """Classify a document using LLM based on extracted text."""
    import httpx

    from app.services.llm_routing import resolve_llm_endpoint

    endpoint = await resolve_llm_endpoint(db_session, org_id)
    if not endpoint:
        return {"type": "other", "confidence": 0, "summary": "No LLM endpoint configured"}

    prompt = CLASSIFICATION_PROMPT.format(text=text[:3000])

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{endpoint.api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {endpoint.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-2.0-flash-001",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        # Parse JSON from response (handle markdown code blocks)
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            content = content.rsplit("```", 1)[0]

        result = json.loads(content.strip())
        # Validate type
        try:
            DocumentType(result["type"])
        except ValueError:
            result["type"] = "other"
        return result  # type: ignore[no-any-return]


async def process_document(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    org_id: UUID,
    db_session: Any,
) -> dict[str, Any]:
    """Full intake pipeline: extract text, sanitize, classify.

    Args:
        file_bytes: Raw file content.
        filename: Original filename.
        content_type: MIME type of the file.
        org_id: Organization UUID for LLM endpoint resolution.
        db_session: AsyncSession for database queries.

    Returns:
        Dict with filename, content_type, extracted_text, classification, page_count.
    """
    # 1. Extract text based on content type
    if content_type == "application/pdf":
        text = await extract_text_from_pdf(file_bytes)
        # If PDF has no extractable text (scanned), fall back to image OCR
        if not text.strip():
            logger.info("document_intake.pdf_no_text falling_back=vision_ocr filename=%s", filename)
            text = await extract_text_from_image(file_bytes, content_type, org_id, db_session)
    elif content_type.startswith("image/"):
        text = await extract_text_from_image(file_bytes, content_type, org_id, db_session)
    elif content_type in (
        "text/plain",
        "text/csv",
        "text/markdown",
        "application/json",
    ):
        text = file_bytes.decode("utf-8", errors="replace")
    else:
        return {
            "filename": filename,
            "content_type": content_type,
            "extracted_text": "",
            "classification": {
                "type": "other",
                "confidence": 0,
                "summary": f"Unsupported content type: {content_type}",
            },
            "page_count": 0,
        }

    # 2. Sanitize extracted text
    text = sanitize_extracted_document(text) or ""

    # 3. Classify
    classification = await classify_document(text, org_id, db_session)

    # 4. Count pages (for PDFs)
    page_count = 0
    if content_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            page_count = len(reader.pages)
        except Exception:
            pass

    return {
        "filename": filename,
        "content_type": content_type,
        "extracted_text": text,
        "classification": classification,
        "page_count": page_count,
    }
