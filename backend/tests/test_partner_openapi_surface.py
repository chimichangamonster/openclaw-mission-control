# ruff: noqa: INP001
"""Layer 2 surface-integrity tests for the public Partner OpenAPI spec.

The full ``GET /openapi.json`` would leak the entire MC backend surface. We
publish a subset at ``GET /api/v1/partner/openapi.json`` generated from the
partner router's routes only. These tests lock the invariants that make
that subset safe to publish:

* every operation path starts with ``/api/v1/partner``;
* no internal model references in ``components/schemas``;
* no internal operation tags (``admin``, ``agent``, ``internal``);
* the documented endpoints match the actual routes shipped by the partner
  router (bidirectional drift catch).

Pattern mirrors ``test_partner_me.py`` — build a minimal FastAPI app that
includes ONLY the partner router + the openapi exporter router, exercise
via httpx.AsyncClient. No DB or auth needed; the openapi endpoint is
unauthenticated.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.partner import router as partner_router
from app.api.partner_openapi import (
    PARTNER_OPENAPI_TITLE,
    PARTNER_OPENAPI_VERSION,
    reset_partner_openapi_cache,
)
from app.api.partner_openapi import router as partner_openapi_router

# Names that must never appear in the public partner OpenAPI schema list.
# These are admin-only / internal / sibling-domain shapes. If any one of
# them shows up in ``components/schemas``, it means an internal type leaked
# into the partner router's request/response graph — fix the leak, don't
# extend this list.
INTERNAL_ONLY_MODELS = (
    # Admin-only partner key shapes (sibling router, NOT for partner consumers)
    "PartnerApiKeyCreateRequest",
    "PartnerApiKeyCreateResponse",
    "PartnerApiKeyListItem",
    "PartnerApiKeyRevokeRequest",
    # Core MC ORM models
    "User",
    "Organization",
    "BkInvoice",
    "BkClient",
    "BkJob",
    "BkPayment",
    "EmailAccount",
    "EmailMessage",
    "MicrosoftConnection",
    "GoogleCalendarConnection",
    "OrganizationSettings",
    "AuditLog",
    "ActivityEvent",
    "Board",
    "Task",
    "CronJob",
    "PaperTrade",
    "PaperBet",
    "WatchlistItem",
    "VectorMemory",
    "OrgContextFile",
    "PartnerApiKey",
    "PartnerWebhookSubscription",
    "PartnerWebhookDelivery",
    # Personal bookkeeping shapes (Personal-org-only internal)
    "PersonalReconciliationMonth",
    "PersonalTransaction",
    "PersonalVendorRule",
    "PersonalStatementFile",
)

# Tags whose presence on any operation signals the spec leaked an
# internal-namespace endpoint. ``partner-v1`` is the ONLY allowed tag.
FORBIDDEN_TAGS = ("admin", "agent", "internal")

# Routes the public spec must intentionally exclude even though they live
# on the partner router itself (or could appear via include_in_schema).
# The openapi.json meta-endpoint is itself excluded via
# ``include_in_schema=False`` so the documented surface doesn't
# self-reference.
META_PATHS_EXCLUDED_FROM_SPEC = ("/api/v1/partner/openapi.json",)


def _build_test_app() -> FastAPI:
    """Build a stripped-down FastAPI app exposing only the partner spec endpoint.

    No auth dep overrides needed — the openapi route is unauthenticated.
    The partner router itself is included so its routes drive spec
    generation, but we never hit those routes in these tests.
    """
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(partner_router)
    api_v1.include_router(partner_openapi_router)
    app.include_router(api_v1)
    return app


@pytest.fixture(autouse=True)
def _clear_openapi_cache() -> None:
    """Reset the spec cache before each test so cases don't leak state."""
    reset_partner_openapi_cache()


@pytest.mark.asyncio
async def test_openapi_endpoint_is_unauthenticated_and_returns_200() -> None:
    """The spec endpoint is reachable without credentials (Mintlify reads it)."""
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/openapi.json")

    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == PARTNER_OPENAPI_TITLE
    assert spec["info"]["version"] == PARTNER_OPENAPI_VERSION
    assert spec["openapi"].startswith("3.")


@pytest.mark.asyncio
async def test_openapi_only_exposes_partner_namespace() -> None:
    """Every path in the spec must start with ``/api/v1/partner``.

    If a non-partner path appears, an internal route leaked into the
    partner router's route list — block before publishing.
    """
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/openapi.json")

    spec = resp.json()
    paths = list(spec.get("paths", {}).keys())
    assert paths, "spec must expose at least one partner endpoint"
    leaked = [p for p in paths if not p.startswith("/api/v1/partner")]
    assert not leaked, f"non-partner paths in public spec: {leaked}"


@pytest.mark.asyncio
async def test_openapi_no_internal_model_references() -> None:
    """No internal/admin/ORM model names may appear in ``components/schemas``.

    The partner subset is generated from the partner router's routes only,
    so internal models should never enter the reference graph. This test
    enforces the invariant — if it fails, an internal type was added to a
    partner request/response shape.
    """
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/openapi.json")

    spec = resp.json()
    schemas = spec.get("components", {}).get("schemas", {})
    leaked = sorted(name for name in INTERNAL_ONLY_MODELS if name in schemas)
    assert not leaked, (
        f"internal model names leaked into partner OpenAPI schemas: {leaked}"
    )


@pytest.mark.asyncio
async def test_openapi_no_internal_tags() -> None:
    """No operation may carry an internal tag (``admin``, ``agent``, etc.).

    Partner operations must carry only the ``partner-v1`` tag.
    """
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/openapi.json")

    spec = resp.json()
    paths = spec.get("paths", {})
    offenders: list[tuple[str, str, list[str]]] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags", []) or []
            bad = [t for t in tags if t in FORBIDDEN_TAGS]
            if bad:
                offenders.append((path, method.upper(), bad))
    assert not offenders, f"forbidden tags on partner operations: {offenders}"


@pytest.mark.asyncio
async def test_documented_endpoints_match_actual_routes() -> None:
    """Bidirectional drift catch: spec ↔ partner router route list.

    Every (path, method) pair the partner router exposes must appear in
    the spec, and vice versa — minus intentionally-excluded meta paths.
    Catches the "shipped a route but forgot to surface it" failure mode
    AND the "spec lists a route that doesn't exist" failure mode.
    """
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/openapi.json")

    spec = resp.json()
    spec_pairs: set[tuple[str, str]] = set()
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in path_item:
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                spec_pairs.add((path, method.upper()))

    # Walk the actual partner router routes. The router's own prefix is
    # ``/partner``; the include in this test app adds ``/api/v1`` on top,
    # so we reconstruct the full path here.
    actual_pairs: set[tuple[str, str]] = set()
    for route in partner_router.routes:
        path_attr = getattr(route, "path", None)
        methods_attr = getattr(route, "methods", None)
        include_in_schema = getattr(route, "include_in_schema", True)
        if not (path_attr and methods_attr and include_in_schema):
            continue
        full_path = f"/api/v1{path_attr}"
        if full_path in META_PATHS_EXCLUDED_FROM_SPEC:
            continue
        for method in methods_attr:
            if method.upper() == "HEAD":
                continue
            actual_pairs.add((full_path, method.upper()))

    missing_in_spec = sorted(actual_pairs - spec_pairs)
    extra_in_spec = sorted(spec_pairs - actual_pairs)
    assert not missing_in_spec, (
        f"partner routes shipped but not documented: {missing_in_spec}"
    )
    assert not extra_in_spec, (
        f"openapi spec documents routes that don't exist: {extra_in_spec}"
    )
