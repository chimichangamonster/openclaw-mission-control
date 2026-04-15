"""Auto-generate chat session titles via the org's LLM endpoint.

Called from the gateway event listener when a chat session completes an
exchange and still has no custom label. Fire-and-forget — all errors are
swallowed and the session keeps its default label. Manual renames always win.
"""

from __future__ import annotations

from uuid import UUID

import httpx

from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.services.llm_routing import resolve_llm_endpoint

logger = get_logger(__name__)

TITLER_MODEL = "google/gemini-2.5-flash-lite"
TITLER_TIMEOUT_SECONDS = 10.0
TITLER_MAX_TOKENS = 16
TITLER_TEMPERATURE = 0.3
_MAX_TITLE_LENGTH = 80
_MSG_CLIP = 500

_SYSTEM_PROMPT = (
    "You are a chat title generator. Summarize the chat in 3-5 words. "
    "No quotes, no punctuation, no trailing period. "
    "Examples: Market update, Magnetik email draft, Proposal for Property Smart. "
    "Return only the title."
)

_STRIP_CHARS = "\"'`\u201c\u201d\u2018\u2019"
_TRAILING_PUNCT = ".,:;!?"


async def generate_title(
    org_id: UUID,
    user_msg: str,
    assistant_msg: str,
) -> str | None:
    """Ask the org's LLM for a 3-5 word title. Returns None on any failure."""
    user_msg = (user_msg or "").strip()
    assistant_msg = (assistant_msg or "").strip()
    if not user_msg:
        return None

    async with async_session_maker() as session:
        endpoint = await resolve_llm_endpoint(session, org_id)
    if not endpoint:
        logger.info("session_titler.no_endpoint org_id=%s", org_id)
        return None

    prompt = (
        f"User: {user_msg[:_MSG_CLIP]}\n\n"
        f"Assistant: {assistant_msg[:_MSG_CLIP]}\n\n"
        "Title:"
    )

    try:
        async with httpx.AsyncClient(timeout=TITLER_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{endpoint.api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {endpoint.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": TITLER_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": TITLER_MAX_TOKENS,
                    "temperature": TITLER_TEMPERATURE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.info("session_titler.http_error org_id=%s", org_id, exc_info=True)
        return None
    except Exception:
        logger.info("session_titler.unexpected_error org_id=%s", org_id, exc_info=True)
        return None

    title = _extract_title(data)
    if not title:
        logger.info("session_titler.empty_title_from_llm org_id=%s", org_id)
        return None

    try:
        from app.services.langfuse_client import trace_session_titling

        trace_session_titling(
            org_id=str(org_id),
            model=TITLER_MODEL,
            title=title,
            token_count=data.get("usage", {}).get("total_tokens"),
        )
    except Exception:
        logger.debug("session_titler.trace_failed", exc_info=True)

    return title


def _extract_title(data: dict) -> str | None:
    """Pull the title string out of a chat/completions response and sanitize it."""
    try:
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(raw, str):
        return None
    title = raw.strip().strip(_STRIP_CHARS).rstrip(_TRAILING_PUNCT).strip()
    if not title or len(title) > _MAX_TITLE_LENGTH:
        return None
    return title
