"""Partner-API key authentication for the `/api/v1/partner/*` namespace.

See `docs/business/partner-api-v1-scope.md` (Auth model section) for design.

Auth flow on every partner-API request:

1. ``Authorization: Bearer vck_<key_id>_<secret>`` header parsed
2. Brute-force limiter checks the source IP (mirrors ``agent_auth_limiter``)
3. ``key_id`` looked up in ``partner_api_keys`` (indexed, O(1))
4. ``secret`` half PBKDF2-verified against ``key_hash``
5. ``revoked_at`` checked — None required
6. Caller-required scopes intersected with key's granted scopes
7. ``last_used_at`` touched (best-effort, throttled)

On any failure: 401 with no detail leakage about which step failed. Logs
include only the token *prefix* (first 6 chars) for debugging — never the
full secret.

Per-org rate limit (600 req/min default, overridable via
``PartnerApiKey.rate_limit_override``) is a separate dep: see
``check_partner_rate_limit`` further below.

Per ``feedback_capture_factory_deps_for_test_override.md`` — every route
uses the **module-level captures** below (``require_partner_webhooks_manage``,
``require_partner_identity_read``). Inline ``Depends(_require_partner_key([...]))``
calls produce fresh callables that pytest cannot override; module-level
capture once + reuse in routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Awaitable, Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import select

from app.core.client_ip import get_client_ip
from app.core.logging import get_logger
from app.core.partner_tokens import (
    parse_partner_token,
    verify_partner_secret,
)
from app.core.rate_limit import RateLimiter, create_rate_limiter
from app.core.time import utcnow
from app.db.session import get_session
from app.models.organizations import Organization
from app.models.partner_api_key import PartnerApiKey

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)

SESSION_DEP = Depends(get_session)

# Throttle last_used_at writes to once per 30s per key (matches agent_auth).
_LAST_USED_TOUCH_INTERVAL = timedelta(seconds=30)

# Brute-force defense on the auth path: 20 attempts per 60s per IP.
partner_auth_limiter = create_rate_limiter(
    namespace="partner_auth",
    max_requests=20,
    window_seconds=60.0,
)


@dataclass
class PartnerAuthContext:
    """Authenticated partner payload, attached to ``request.state`` for downstream deps."""

    api_key: PartnerApiKey
    organization: Organization


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Return the raw token after a ``Bearer `` prefix, or None."""
    if not authorization:
        return None
    value = authorization.strip()
    if not value.lower().startswith("bearer "):
        return None
    token = value.split(" ", 1)[1].strip()
    return token or None


async def _touch_last_used(session: AsyncSession, api_key: PartnerApiKey) -> None:
    """Best-effort throttled update of ``last_used_at``. Mirrors agent_auth pattern."""
    now = utcnow()
    if (
        api_key.last_used_at is not None
        and now - api_key.last_used_at < _LAST_USED_TOUCH_INTERVAL
    ):
        return
    api_key.last_used_at = now
    session.add(api_key)


async def _resolve_partner_auth(
    request: Request,
    authorization: str | None,
    session: AsyncSession,
) -> PartnerAuthContext:
    """Parse, validate, and resolve a partner API token to (key, org) context.

    Raises ``HTTPException(401)`` on any failure, without leaking which step
    failed. Logs the token prefix (first 6 chars) for debugging.
    """
    client_ip = get_client_ip(request)
    if not await partner_auth_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    token = _extract_bearer_token(authorization)
    if not token:
        logger.warning(
            "partner auth missing token path=%s",
            request.url.path,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    parsed = parse_partner_token(token)
    if parsed is None:
        logger.warning(
            "partner auth malformed token path=%s token_prefix=%s",
            request.url.path,
            token[:6],
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    key_id, secret = parsed

    api_key = (
        await session.exec(
            select(PartnerApiKey).where(PartnerApiKey.key_id == key_id),
        )
    ).first()
    if api_key is None:
        logger.warning(
            "partner auth unknown key_id path=%s token_prefix=%s",
            request.url.path,
            token[:6],
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if not verify_partner_secret(secret, api_key.key_hash):
        logger.warning(
            "partner auth bad secret path=%s key_id=%s",
            request.url.path,
            key_id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if api_key.revoked_at is not None:
        logger.warning(
            "partner auth revoked key path=%s key_id=%s revoked_at=%s",
            request.url.path,
            key_id,
            api_key.revoked_at.isoformat(),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    organization = await session.get(Organization, api_key.organization_id)
    if organization is None:
        # Shouldn't happen — FK enforces it — but defend against orphan keys.
        logger.error(
            "partner auth orphan key path=%s key_id=%s missing_org=%s",
            request.url.path,
            key_id,
            api_key.organization_id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    await _touch_last_used(session, api_key)

    ctx = PartnerAuthContext(api_key=api_key, organization=organization)
    # Stash on request.state so per-org-rate-limit dep can read the override
    # without re-resolving the key.
    request.state.partner_auth = ctx
    return ctx


def _require_partner_key(
    required_scopes: list[str],
) -> Callable[..., Awaitable[PartnerAuthContext]]:
    """Factory returning a FastAPI dependency that enforces ``required_scopes``.

    Per ``feedback_capture_factory_deps_for_test_override.md`` — assign the
    returned callable to a module-level name and use that in routes.
    """

    async def dep(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        session: AsyncSession = SESSION_DEP,
    ) -> PartnerAuthContext:
        ctx = await _resolve_partner_auth(request, authorization, session)

        # ``identity:read`` is always granted (per scope doc: always granted,
        # non-revocable) — short-circuit if that's all that's required.
        if required_scopes == ["identity:read"]:
            return ctx

        granted = set(ctx.api_key.scopes)
        missing = [s for s in required_scopes if s not in granted]
        if missing:
            logger.warning(
                "partner auth scope mismatch path=%s key_id=%s missing=%s",
                request.url.path,
                ctx.api_key.key_id,
                missing,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return ctx

    return dep


# === Module-level dep captures (use these in routes) ======================
# Per feedback_capture_factory_deps_for_test_override.md: inline factory calls
# produce un-overridable callables. Define once, reuse everywhere.

require_partner_webhooks_manage = _require_partner_key(["webhooks:manage"])
require_partner_identity_read = _require_partner_key(["identity:read"])


# === Per-org rate limit (with key-level override) =========================

# Cache of per-key custom-ceiling limiters, keyed by (key_id, override_value).
# Without this cache the in-memory backend would lose state because each
# request would build a fresh limiter; the Redis backend would also leak
# connections per request. Re-tied to ``override`` so changing the override
# value invalidates the cached entry naturally.
_partner_override_limiters: dict[tuple[str, int], RateLimiter] = {}


def _get_override_limiter(key_id: str, override: int) -> RateLimiter:
    cache_key = (key_id, override)
    limiter = _partner_override_limiters.get(cache_key)
    if limiter is None:
        limiter = create_rate_limiter(
            namespace=f"partner_key_{key_id}",
            max_requests=override,
            window_seconds=60.0,
        )
        _partner_override_limiters[cache_key] = limiter
    return limiter


async def check_partner_rate_limit(
    request: Request,
) -> None:
    """Enforce per-org request rate limit, honoring per-key override.

    Reads the resolved ``PartnerAuthContext`` from ``request.state``; depend
    on this AFTER one of the ``require_partner_*`` deps so the context exists.

    Default ceiling: 600 req/min per org (matches ``org_api_limiter``).
    ``PartnerApiKey.rate_limit_override`` raises (or lowers) the ceiling on
    a per-key basis.
    """
    ctx: PartnerAuthContext | None = getattr(request.state, "partner_auth", None)
    if ctx is None:
        # Defensive — should never happen if dep ordering is correct.
        logger.error(
            "partner rate-limit dep ran before auth dep path=%s",
            request.url.path,
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    override = ctx.api_key.rate_limit_override
    if override is not None and override > 0:
        limiter = _get_override_limiter(ctx.api_key.key_id, override)
        key = ctx.api_key.key_id
    else:
        from app.core.rate_limit import org_api_limiter

        limiter = org_api_limiter
        key = str(ctx.organization.id)

    if not await limiter.is_allowed(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again shortly.",
            headers={"Retry-After": "60"},
        )


PARTNER_RATE_LIMIT_DEP = Depends(check_partner_rate_limit)
