"""Public OpenAPI subset exporter for the Partner API v1 namespace.

See `docs/business/partner-api-v1-scope.md` Step 8 (Session B) for design.

The full ``GET /openapi.json`` would leak the entire MC backend surface —
internal models, admin endpoints, agent routes, etc. — so we publish a
deliberately scoped subset generated from the partner router's routes
only. Mintlify ingests this subset to render the public API reference.

Key invariants (Layer 2 tests in ``tests/test_partner_openapi_surface.py``):

* every path starts with ``/api/v1/partner``;
* no internal model references in ``components/schemas`` (admin shapes,
  ORM models, sibling-domain schemas);
* no internal tags (``admin``, ``agent``, ``internal``) on operations.

The endpoint is unauthenticated — Mintlify (and any other doc reader)
fetches it anonymously. There is no sensitive content in the spec; it
is the public contract.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.openapi.utils import get_openapi

from app.api.partner import router as partner_router

# Public path prefix served in front of the partner router. The partner
# router itself declares ``prefix="/partner"``; the outer ``/api/v1`` is
# added by the includer in ``app/main.py``. We reconstruct the full path
# here so the generated spec documents the URLs partners actually call.
PARTNER_API_PATH_PREFIX = "/api/v1"

# Title + version + description served in the generated spec. Bumped
# alongside material partner-facing surface changes; see Step 9
# changelog.mdx in the docs repo.
PARTNER_OPENAPI_TITLE = "VantageClaw Partner API"
PARTNER_OPENAPI_VERSION = "1.0.0"
PARTNER_OPENAPI_DESCRIPTION = (
    "Public substrate-only API for VantageClaw partners.\n\n"
    "v1 surface: identity (`/me`) and webhook subscription management. "
    "Resource CRUD ships with the first resource family. See "
    "https://developers.vantageclaw.ai for conceptual docs."
)

# Module-level cache so repeated requests don't re-walk the route graph.
# Cleared lazily on import; tests build their own apps so this cache is
# scoped to the long-lived production process only.
_cached_spec: dict[str, Any] | None = None


def _build_partner_openapi() -> dict[str, Any]:
    """Generate the OpenAPI document from the partner router's routes only.

    ``get_openapi`` walks the ``routes`` list and includes every Pydantic
    model reachable from each operation's request/response shapes. Because
    we pass *only* the partner router's routes, internal models referenced
    elsewhere in the app (User, Organization, BkInvoice, etc.) never enter
    the reference graph and so never appear in ``components/schemas``.
    """
    global _cached_spec  # noqa: PLW0603 — single-process module cache
    if _cached_spec is not None:
        return _cached_spec

    # Wrap the partner router inside an outer router carrying the
    # ``/api/v1`` prefix so each route in the generated spec reports its
    # full public path (``/api/v1/partner/...``) rather than just the
    # partner router's inner ``/partner/...`` view. This matches the URL
    # partners actually call.
    wrapper = APIRouter(prefix=PARTNER_API_PATH_PREFIX)
    wrapper.include_router(partner_router)

    spec = get_openapi(
        title=PARTNER_OPENAPI_TITLE,
        version=PARTNER_OPENAPI_VERSION,
        openapi_version="3.1.0",
        description=PARTNER_OPENAPI_DESCRIPTION,
        routes=wrapper.routes,
    )
    _cached_spec = spec
    return spec


def reset_partner_openapi_cache() -> None:
    """Test hook — clear the in-memory cache so a fresh build runs.

    Production code never calls this; it exists so that surface-integrity
    tests can build the spec deterministically without leaking cache state
    between cases.
    """
    global _cached_spec  # noqa: PLW0603
    _cached_spec = None


router = APIRouter(prefix="/partner", tags=["partner-v1"])


@router.get(
    "/openapi.json",
    summary="Public OpenAPI spec for the Partner API v1 namespace",
    include_in_schema=False,
)
async def get_partner_openapi() -> dict[str, Any]:
    """Return the partner-subset OpenAPI document.

    Unauthenticated — Mintlify and other doc readers fetch this anonymously.
    The spec contains no sensitive information; it is the public contract.

    ``include_in_schema=False`` keeps this meta-endpoint out of the spec
    it generates (otherwise the documented surface would self-reference).
    """
    return _build_partner_openapi()
