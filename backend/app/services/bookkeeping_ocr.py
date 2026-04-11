"""Receipt OCR service — vision model extracts structured data from receipt images.

Uses the org's resolved LLM endpoint (BYOK, custom, or platform OpenRouter).
Primary model: Claude Sonnet 4. Fallback: Gemini Flash.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID

import httpx

from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.services.llm_routing import resolve_llm_endpoint

logger = get_logger(__name__)

OCR_PRIMARY_MODEL = "anthropic/claude-sonnet-4-20250514"
OCR_FALLBACK_MODEL = "google/gemini-2.0-flash-001"

OCR_PROMPT = """You are a receipt OCR extraction system. Analyze this receipt image and extract structured data.

Return ONLY valid JSON with this exact structure:
{
  "vendor": "store/business name",
  "date": "YYYY-MM-DD",
  "subtotal": 0.00,
  "gst": 0.00,
  "total": 0.00,
  "items": [
    {"description": "item name", "quantity": 1, "unit_price": 0.00, "amount": 0.00}
  ],
  "payment_method": "cash|debit|credit|null",
  "category_suggestion": "materials|fuel|tools|ppe|food|vehicle|office|equipment|other"
}

Rules:
- All amounts in CAD
- GST is 5% in Alberta. If GST line is not visible, calculate from total: gst = total / 1.05 * 0.05
- If date is not readable, use null
- category_suggestion should be your best guess based on the vendor and items
- For construction supplies (Home Depot, lumber, concrete, etc.) use "materials"
- For gas stations use "fuel"
- Return ONLY the JSON, no markdown fences or explanation"""


def _detect_mime_type(data: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if len(data) < 2:
        return "image/jpeg"
    if data[0] == 0xFF and data[1] == 0xD8:
        return "image/jpeg"
    if data[0] == 0x89 and data[1] == 0x50:
        return "image/png"
    if data[0] == 0x47 and data[1] == 0x49:
        return "image/gif"
    if data[0] == 0x52 and data[1] == 0x49:
        return "image/webp"
    return "image/jpeg"


async def _call_vision_model(
    api_url: str,
    api_key: str,
    model: str,
    image_b64: str,
    mime_type: str,
) -> dict[str, Any]:
    """Call an OpenAI-compatible vision API to extract receipt data."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://openclaw-business-platform",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": OCR_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                            },
                        ],
                    },
                ],
                "temperature": 0,
                "max_tokens": 1000,
            },
        )
        resp.raise_for_status()

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("No content in LLM response")

    # Strip markdown fences if present
    json_str = (
        content.replace("```json\n", "")
        .replace("```json", "")
        .replace("```\n", "")
        .replace("```", "")
        .strip()
    )
    parsed = json.loads(json_str)

    if parsed.get("total") is None:
        raise ValueError("OCR failed to extract total amount")

    return parsed  # type: ignore[no-any-return]


async def process_receipt(image_bytes: bytes, org_id: UUID) -> dict[str, Any]:
    """Process a receipt image through the org's LLM endpoint.

    Tries primary model (Claude Sonnet), falls back to Gemini Flash.

    Args:
        image_bytes: Raw image file bytes.
        org_id: Organization ID for LLM endpoint resolution.

    Returns:
        Parsed receipt data dict with vendor, date, subtotal, gst, total, items, etc.

    Raises:
        ValueError: If both models fail to extract data.
    """
    async with async_session_maker() as session:
        endpoint = await resolve_llm_endpoint(session, org_id)

    if endpoint is None:
        raise ValueError(
            "No LLM endpoint configured for this organization. Add an OpenRouter API key in org settings."
        )

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime_type = _detect_mime_type(image_bytes)

    # Try primary model
    try:
        result = await _call_vision_model(
            endpoint.api_url, endpoint.api_key, OCR_PRIMARY_MODEL, image_b64, mime_type
        )
        logger.info("bookkeeping_ocr.success model=%s org_id=%s", OCR_PRIMARY_MODEL, org_id)
        return result
    except Exception as e:
        logger.warning(
            "bookkeeping_ocr.primary_failed model=%s error=%s", OCR_PRIMARY_MODEL, str(e)[:200]
        )

    # Fallback
    try:
        result = await _call_vision_model(
            endpoint.api_url, endpoint.api_key, OCR_FALLBACK_MODEL, image_b64, mime_type
        )
        logger.info(
            "bookkeeping_ocr.fallback_success model=%s org_id=%s", OCR_FALLBACK_MODEL, org_id
        )
        return result
    except Exception as e:
        logger.error("bookkeeping_ocr.both_failed org_id=%s error=%s", org_id, str(e)[:200])
        raise ValueError(f"Receipt OCR failed with both models: {e}") from e
