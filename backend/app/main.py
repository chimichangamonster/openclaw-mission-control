"""FastAPI application entrypoint and router wiring for the backend."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi_pagination import add_pagination

from app.api.activity import router as activity_router
from app.api.agent import router as agent_router
from app.api.agent_contacts import router as agent_contacts_router
from app.api.agent_email import router as agent_email_router
from app.api.agent_memory_vector import router as agent_memory_vector_router
from app.api.memory_vector import router as memory_vector_router
from app.api.agent_polymarket import router as agent_polymarket_router
from app.api.agents import router as agents_router
from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.board_group_memory import router as board_group_memory_router
from app.api.board_groups import router as board_groups_router
from app.api.board_memory import router as board_memory_router
from app.api.board_onboarding import router as board_onboarding_router
from app.api.board_webhooks import router as board_webhooks_router
from app.api.boards import router as boards_router
from app.api.bookkeeping import router as bookkeeping_router
from app.api.chat_projects import router as chat_projects_router
from app.api.contacts import router as contacts_router
from app.api.cost_tracker import router as cost_tracker_router
from app.api.cron_jobs import router as cron_jobs_router
from app.api.crypto_trading import router as crypto_trading_router
from app.api.document_gen import router as document_gen_router
from app.api.document_intake import router as document_intake_router
from app.api.email import inline_router as email_inline_router
from app.api.email import router as email_router
from app.api.email_oauth import router as email_oauth_router
from app.api.file_serve import router as file_serve_router
from app.api.gateway import router as gateway_router
from app.api.gateway_live import router as gateway_live_router
from app.api.gateways import router as gateways_router
from app.api.google_calendar import router as google_calendar_router
from app.api.industry_templates import router as industry_templates_router
from app.api.invoice_pdf import router as invoice_pdf_router
from app.api.legal import router as legal_router
from app.api.memory import router as memory_router
from app.api.metrics import router as metrics_router
from app.api.microsoft_graph import router as microsoft_graph_router
from app.api.model_registry import router as model_registry_router
from app.api.observability import router as observability_router
from app.api.org_config import router as org_config_router
from app.api.organization_settings import router as org_settings_router
from app.api.organizations import router as organizations_router
from app.api.paper_bets import router as paper_bets_router
from app.api.paper_trading import router as paper_trading_router
from app.api.pentest import router as pentest_router
from app.api.platform_admin import router as platform_admin_router
from app.api.polymarket import router as polymarket_router
from app.api.skill_config import router as skill_config_router
from app.api.skills_marketplace import router as skills_marketplace_router
from app.api.souls_directory import router as souls_directory_router
from app.api.tags import router as tags_router
from app.api.task_custom_fields import router as task_custom_fields_router
from app.api.tasks import router as tasks_router
from app.api.users import router as users_router
from app.api.watchlist import router as watchlist_router
from app.api.wechat_auth import router as wechat_auth_router
from app.api.wecom import router as wecom_router
from app.core.config import settings
from app.core.error_handling import install_error_handling
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import validate_rate_limit_redis
from app.core.rate_limit_backend import RateLimitBackend
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.session import init_db
from app.schemas.health import HealthStatusResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

configure_logging()
logger = get_logger(__name__)
OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": (
            "Authentication bootstrap endpoints for resolving caller identity and session context."
        ),
    },
    {
        "name": "health",
        "description": (
            "Service liveness/readiness probes used by infrastructure and runtime checks."
        ),
    },
    {
        "name": "agents",
        "description": "Organization-level agent directory, lifecycle, and management operations.",
    },
    {
        "name": "activity",
        "description": "Activity feed and audit timeline endpoints across boards and operations.",
    },
    {
        "name": "gateways",
        "description": "Gateway management, synchronization, and runtime control operations.",
    },
    {
        "name": "metrics",
        "description": "Aggregated operational and board analytics metrics endpoints.",
    },
    {
        "name": "organizations",
        "description": "Organization profile, membership, and governance management endpoints.",
    },
    {
        "name": "souls-directory",
        "description": "Directory and lookup endpoints for agent soul templates and variants.",
    },
    {
        "name": "skills",
        "description": "Skills marketplace, install, uninstall, and synchronization endpoints.",
    },
    {
        "name": "trading",
        "description": "Polymarket prediction market trading, wallet management, risk controls, and approval-gated execution.",
    },
    {
        "name": "email",
        "description": "Email account OAuth connection, sync, message management, and agent triage endpoints.",
    },
    {
        "name": "board-groups",
        "description": "Board group CRUD, assignment, and grouping workflow endpoints.",
    },
    {
        "name": "board-group-memory",
        "description": "Shared memory endpoints scoped to board groups and grouped boards.",
    },
    {
        "name": "boards",
        "description": "Board lifecycle, configuration, and board-level management endpoints.",
    },
    {
        "name": "board-memory",
        "description": "Board-scoped memory read/write endpoints for persistent context.",
    },
    {
        "name": "board-webhooks",
        "description": "Board webhook registration, delivery config, and lifecycle endpoints.",
    },
    {
        "name": "board-onboarding",
        "description": "Board onboarding state, setup actions, and onboarding workflow endpoints.",
    },
    {
        "name": "approvals",
        "description": "Approval request, review, and status-tracking operations for board tasks.",
    },
    {
        "name": "tasks",
        "description": "Task CRUD, dependency management, and task workflow operations.",
    },
    {
        "name": "custom-fields",
        "description": "Organization custom-field definitions and board assignment endpoints.",
    },
    {
        "name": "tags",
        "description": "Tag catalog and task-tag association management endpoints.",
    },
    {
        "name": "users",
        "description": "User profile read/update operations and user-centric settings endpoints.",
    },
    {
        "name": "agent",
        "description": (
            "Agent-scoped API surface. All endpoints require `X-Agent-Token` and are "
            "constrained by agent board access policies."
        ),
    },
    {
        "name": "agent-lead",
        "description": (
            "Lead workflows: delegation, review orchestration, approvals, and "
            "coordination actions."
        ),
    },
    {
        "name": "agent-worker",
        "description": (
            "Worker workflows: task execution, task comments, and board/group context "
            "reads/writes used during heartbeat loops."
        ),
    },
    {
        "name": "agent-main",
        "description": (
            "Gateway-main control workflows that message board leads or broadcast "
            "coordination requests."
        ),
    },
]

_JSON_SCHEMA_REF_PREFIX = "#/components/schemas/"
_OPENAPI_EXAMPLE_TAGS = {
    "agents",
    "activity",
    "email",
    "trading",
    "gateways",
    "metrics",
    "organizations",
    "souls-directory",
    "skills",
    "board-groups",
    "board-group-memory",
    "boards",
    "board-memory",
    "board-webhooks",
    "board-onboarding",
    "approvals",
    "tasks",
    "custom-fields",
    "tags",
    "users",
}
_GENERIC_RESPONSE_DESCRIPTIONS = {"Successful Response", "Validation Error"}
_HTTP_RESPONSE_DESCRIPTIONS = {
    "200": "Request completed successfully.",
    "201": "Resource created successfully.",
    "202": "Request accepted for processing.",
    "204": "Request completed successfully with no response body.",
    "400": "Request validation failed.",
    "401": "Authentication is required or token is invalid.",
    "403": "Caller is authenticated but not authorized for this operation.",
    "404": "Requested resource was not found.",
    "409": "Request conflicts with the current resource state.",
    "422": "Request payload failed schema or field validation.",
    "429": "Request was rate-limited.",
    "500": "Internal server error.",
}
_METHOD_SUMMARY_PREFIX = {
    "get": "List",
    "post": "Create",
    "put": "Replace",
    "patch": "Update",
    "delete": "Delete",
}


def _resolve_schema_ref(
    schema: dict[str, Any],
    *,
    components: dict[str, Any],
    seen_refs: set[str] | None = None,
) -> dict[str, Any]:
    """Resolve local component refs for OpenAPI schema traversal."""
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    if not ref.startswith(_JSON_SCHEMA_REF_PREFIX):
        return schema
    if seen_refs is None:
        seen_refs = set()
    if ref in seen_refs:
        return schema
    seen_refs.add(ref)
    schema_name = ref[len(_JSON_SCHEMA_REF_PREFIX) :]
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        return schema
    target = schemas.get(schema_name)
    if not isinstance(target, dict):
        return schema
    return _resolve_schema_ref(target, components=components, seen_refs=seen_refs)


def _example_from_schema(schema: dict[str, Any], *, components: dict[str, Any]) -> Any:
    """Generate an OpenAPI example from schema metadata with sensible fallbacks."""
    resolved = _resolve_schema_ref(schema, components=components)

    if "example" in resolved:
        return resolved["example"]
    examples = resolved.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]

    for composite_key in ("anyOf", "oneOf", "allOf"):
        composite = resolved.get(composite_key)
        if isinstance(composite, list):
            for branch in composite:
                if not isinstance(branch, dict):
                    continue
                branch_example = _example_from_schema(branch, components=components)
                if branch_example is not None:
                    return branch_example

    enum_values = resolved.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    schema_type = resolved.get("type")
    if schema_type == "object":
        output: dict[str, Any] = {}
        properties = resolved.get("properties")
        if isinstance(properties, dict):
            for key, property_schema in properties.items():
                if not isinstance(property_schema, dict):
                    continue
                property_example = _example_from_schema(property_schema, components=components)
                if property_example is not None:
                    output[key] = property_example
        if output:
            return output
        additional_properties = resolved.get("additionalProperties")
        if isinstance(additional_properties, dict):
            value_example = _example_from_schema(additional_properties, components=components)
            if value_example is not None:
                return {"key": value_example}
        return {}

    if schema_type == "array":
        items = resolved.get("items")
        if isinstance(items, dict):
            item_example = _example_from_schema(items, components=components)
            if item_example is not None:
                return [item_example]
        return []

    if schema_type == "string":
        return "string"
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0
    if schema_type == "boolean":
        return False

    return None


def _inject_json_content_example(
    *,
    content: dict[str, Any],
    components: dict[str, Any],
) -> None:
    """Attach an example to application/json content when one is missing."""
    app_json = content.get("application/json")
    if not isinstance(app_json, dict):
        return
    if "example" in app_json or "examples" in app_json:
        return
    schema = app_json.get("schema")
    if not isinstance(schema, dict):
        return
    generated_example = _example_from_schema(schema, components=components)
    if generated_example is not None:
        app_json["example"] = generated_example


def _build_operation_summary(*, method: str, path: str) -> str:
    """Build a readable summary when an operation does not define one."""
    prefix = _METHOD_SUMMARY_PREFIX.get(method.lower(), "Handle")
    path_without_prefix = path.removeprefix("/api/v1/")
    parts = [
        part.replace("-", " ")
        for part in path_without_prefix.split("/")
        if part and not (part.startswith("{") and part.endswith("}"))
    ]
    if not parts:
        return prefix
    return f"{prefix} {' '.join(parts)}".strip().title()


def _normalize_operation_docs(
    *,
    operation: dict[str, Any],
    method: str,
    path: str,
) -> None:
    """Normalize summary/description/responses/request-body docs for tagged operations."""
    summary = str(operation.get("summary", "")).strip()
    if not summary:
        summary = _build_operation_summary(method=method, path=path)
        operation["summary"] = summary

    description = str(operation.get("description", "")).strip()
    if not description:
        operation["description"] = f"{summary}."

    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        if not str(request_body.get("description", "")).strip():
            request_body["description"] = "JSON request payload."

    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return
    for status_code, response in responses.items():
        if not isinstance(response, dict):
            continue
        existing_description = str(response.get("description", "")).strip()
        if not existing_description or existing_description in _GENERIC_RESPONSE_DESCRIPTIONS:
            response["description"] = _HTTP_RESPONSE_DESCRIPTIONS.get(
                str(status_code),
                "Request processed.",
            )


def _inject_tagged_operation_openapi_docs(openapi_schema: dict[str, Any]) -> None:
    """Ensure targeted-tag operations expose consistent OpenAPI docs and examples."""
    components = openapi_schema.get("components")
    if not isinstance(components, dict):
        return
    paths = openapi_schema.get("paths")
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags")
            if not isinstance(tags, list):
                continue
            if not _OPENAPI_EXAMPLE_TAGS.intersection(tags):
                continue

            _normalize_operation_docs(operation=operation, method=method, path=path)

            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                request_content = request_body.get("content")
                if isinstance(request_content, dict):
                    _inject_json_content_example(content=request_content, components=components)

            responses = operation.get("responses")
            if isinstance(responses, dict):
                for response in responses.values():
                    if not isinstance(response, dict):
                        continue
                    response_content = response.get("content")
                    if isinstance(response_content, dict):
                        _inject_json_content_example(
                            content=response_content, components=components
                        )


def _build_custom_openapi(fastapi_app: FastAPI) -> dict[str, Any]:
    """Generate OpenAPI schema with normalized docs/examples for targeted tags."""
    if fastapi_app.openapi_schema:
        return fastapi_app.openapi_schema
    openapi_schema = get_openapi(
        title=fastapi_app.title,
        version=fastapi_app.version,
        openapi_version=fastapi_app.openapi_version,
        description=fastapi_app.description,
        routes=fastapi_app.routes,
        tags=fastapi_app.openapi_tags,
        servers=fastapi_app.servers,
    )
    _inject_tagged_operation_openapi_docs(openapi_schema)
    fastapi_app.openapi_schema = openapi_schema
    return fastapi_app.openapi_schema


class MissionControlFastAPI(FastAPI):
    """FastAPI application with custom OpenAPI normalization."""

    def openapi(self) -> dict[str, Any]:
        return _build_custom_openapi(self)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize application resources before serving requests."""
    logger.info(
        "app.lifecycle.starting environment=%s db_auto_migrate=%s",
        settings.environment,
        settings.db_auto_migrate,
    )
    await init_db()
    if settings.rate_limit_backend == RateLimitBackend.REDIS:
        validate_rate_limit_redis(settings.rate_limit_redis_url)
        logger.info("app.lifecycle.rate_limit backend=redis")
    else:
        logger.info("app.lifecycle.rate_limit backend=memory")

    # Start gateway event listeners (one per configured gateway) for real-time
    # activity feed.  Replaces the old single-gateway approach.
    listener_tasks: list[asyncio.Task[None]] = []
    try:
        from app.services.openclaw.gateway_event_listener import run_all_event_listeners

        listener_tasks = await run_all_event_listeners()
        logger.info("app.lifecycle.gateway_listeners started count=%d", len(listener_tasks))
    except Exception as exc:  # noqa: BLE001
        logger.warning("app.lifecycle.gateway_listeners_init_failed error=%s", exc)

    # Background task: update DB pool metrics for Prometheus every 15s.
    async def _update_pool_metrics() -> None:
        from app.core.prometheus import db_pool_checked_out, db_pool_size
        from app.db.session import async_engine

        while True:
            try:
                pool = async_engine.pool
                db_pool_size.set(pool.size())  # type: ignore[attr-defined]
                db_pool_checked_out.set(pool.checkedout())  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(15)

    pool_task = asyncio.create_task(_update_pool_metrics())

    # Background task: check budgets every 5 minutes.
    async def _check_budgets_loop() -> None:
        from app.services.budget_monitor import check_budgets

        await asyncio.sleep(60)  # delay to let gateway connect
        while True:
            try:
                await check_budgets()
            except Exception:  # noqa: BLE001
                logger.exception("budget_monitor.check_failed")
            await asyncio.sleep(300)

    budget_task = asyncio.create_task(_check_budgets_loop())

    # Background task: check for stale cron tasks every 10 minutes.
    async def _cron_watchdog_loop() -> None:
        from app.services.cron_watchdog import check_stale_cron_tasks

        await asyncio.sleep(120)  # delay to let gateway connect + first crons finish
        while True:
            try:
                await check_stale_cron_tasks()
            except Exception:  # noqa: BLE001
                logger.exception("cron_watchdog.check_failed")
            await asyncio.sleep(600)

    watchdog_task = asyncio.create_task(_cron_watchdog_loop())

    # Background task: sync emails and process email sync queue every 5 minutes.
    async def _email_sync_loop() -> None:
        from app.services.email.sync import sync_all_active_accounts
        from app.services.email.worker import process_email_sync_queue

        await asyncio.sleep(30)  # delay to let DB settle
        while True:
            try:
                # Enqueue all active accounts for sync
                await sync_all_active_accounts()
                # Process the queue (both periodic + manually-triggered syncs)
                await process_email_sync_queue()
            except Exception:  # noqa: BLE001
                logger.exception("email_sync.loop_failed")
            await asyncio.sleep(settings.email_sync_interval_seconds)

    email_sync_task = asyncio.create_task(_email_sync_loop())

    # Background task: data retention cleanup once per day at ~4 AM UTC.
    async def _data_retention_loop() -> None:
        from app.services.data_retention import run_retention_cleanup

        # Initial delay: wait 10 minutes to let everything settle, then align to ~24h cycle
        await asyncio.sleep(600)
        while True:
            try:
                await run_retention_cleanup()
            except Exception:  # noqa: BLE001
                logger.exception("data_retention.cleanup_failed")
            await asyncio.sleep(86400)  # 24 hours

    retention_task = asyncio.create_task(_data_retention_loop())

    logger.info("app.lifecycle.started")
    try:
        yield
    finally:
        pool_task.cancel()
        budget_task.cancel()
        watchdog_task.cancel()
        email_sync_task.cancel()
        retention_task.cancel()
        for lt in listener_tasks:
            if not lt.done():
                lt.cancel()
        for lt in listener_tasks:
            if not lt.done():
                try:
                    await lt
                except asyncio.CancelledError:
                    pass
            logger.info("app.lifecycle.gateway_listener stopped")
        logger.info("app.lifecycle.stopped")


app = MissionControlFastAPI(
    title="Mission Control API",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count", "X-Limit", "X-Offset"],
    )
    logger.info("app.cors.enabled origins_count=%s", len(origins))
else:
    logger.info("app.cors.disabled")

app.add_middleware(
    SecurityHeadersMiddleware,
    x_content_type_options=settings.security_header_x_content_type_options,
    x_frame_options=settings.security_header_x_frame_options,
    referrer_policy=settings.security_header_referrer_policy,
    permissions_policy=settings.security_header_permissions_policy,
)
install_error_handling(app)

from app.core.prometheus import setup_metrics  # noqa: E402

setup_metrics(app)


@app.get(
    "/health",
    tags=["health"],
    response_model=HealthStatusResponse,
    summary="Health Check",
    description="Lightweight liveness probe endpoint.",
    responses={
        status.HTTP_200_OK: {
            "description": "Service is alive.",
            "content": {"application/json": {"example": {"ok": True}}},
        }
    },
)
def health() -> HealthStatusResponse:
    """Lightweight liveness probe endpoint."""
    return HealthStatusResponse(ok=True)


@app.get(
    "/healthz",
    tags=["health"],
    response_model=HealthStatusResponse,
    summary="Health Alias Check",
    description="Alias liveness probe endpoint for platform compatibility.",
    responses={
        status.HTTP_200_OK: {
            "description": "Service is alive.",
            "content": {"application/json": {"example": {"ok": True}}},
        }
    },
)
def healthz() -> HealthStatusResponse:
    """Alias liveness probe endpoint for platform compatibility."""
    return HealthStatusResponse(ok=True)


@app.get(
    "/readyz",
    tags=["health"],
    response_model=HealthStatusResponse,
    summary="Readiness Check",
    description="Readiness probe endpoint for service orchestration checks.",
    responses={
        status.HTTP_200_OK: {
            "description": "Service is ready.",
            "content": {"application/json": {"example": {"ok": True}}},
        }
    },
)
def readyz() -> HealthStatusResponse:
    """Readiness probe endpoint for service orchestration checks."""
    return HealthStatusResponse(ok=True)


@app.get("/status", tags=["health"], summary="Dependency Health Status")
async def dependency_status() -> Any:
    """Check health of all external dependencies with circuit breaker state."""
    from app.core.prometheus import gateway_listener_connected
    from app.core.resilience import gateway_rpc_breaker, openrouter_breaker

    checks: dict[str, dict[str, Any]] = {}

    # PostgreSQL
    try:
        from app.db.session import async_engine

        async with async_engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["postgresql"] = {"status": "ok"}
    except Exception as exc:
        checks["postgresql"] = {"status": "error", "error": str(exc)[:100]}

    # Redis
    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(
            settings.rate_limit_redis_url or "redis://redis:6379", socket_timeout=2
        )
        r.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": str(exc)[:100]}

    # Gateway WebSocket listener
    try:
        gw_connected = gateway_listener_connected._value.get()
        checks["gateway_listener"] = {
            "status": "ok" if gw_connected == 1 else "disconnected",
        }
    except Exception:
        checks["gateway_listener"] = {"status": "unknown"}

    # Circuit breakers
    checks["circuit_breakers"] = {
        "openrouter": {
            "state": openrouter_breaker.state,
            "failures": openrouter_breaker._failure_count,
        },
        "gateway_rpc": {
            "state": gateway_rpc_breaker.state,
            "failures": gateway_rpc_breaker._failure_count,
        },
    }

    all_ok = all(c.get("status") == "ok" for k, c in checks.items() if k != "circuit_breakers")

    return {"ok": all_ok, "dependencies": checks}


@app.get("/api/v1/system/health", tags=["health"], summary="Aggregated System Health")
async def system_health() -> Any:
    """Aggregate platform health into a single status: healthy / degraded / down.

    Checks: PostgreSQL, Redis, gateway listener, circuit breakers, recent errors,
    and cron job health.
    """
    from app.core.prometheus import gateway_listener_connected
    from app.core.resilience import gateway_rpc_breaker, openrouter_breaker
    from app.services.error_tracker import ERROR_PREFIX

    issues: list[str] = []
    components: dict[str, dict[str, Any]] = {}

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    try:
        from app.db.session import async_engine

        async with async_engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        components["postgresql"] = {"status": "ok"}
    except Exception as exc:
        components["postgresql"] = {"status": "down", "error": str(exc)[:100]}
        issues.append("postgresql down")

    # ── Redis ──────────────────────────────────────────────────────────────
    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(
            settings.rate_limit_redis_url or "redis://redis:6379",
            socket_timeout=2,
        )
        r.ping()
        components["redis"] = {"status": "ok"}
    except Exception as exc:
        components["redis"] = {"status": "down", "error": str(exc)[:100]}
        issues.append("redis down")

    # ── Gateway Listener ───────────────────────────────────────────────────
    try:
        gw_connected = gateway_listener_connected._value.get()
        if gw_connected == 1:
            components["gateway_listener"] = {"status": "ok"}
        else:
            components["gateway_listener"] = {"status": "disconnected"}
            issues.append("gateway listener disconnected")
    except Exception:
        components["gateway_listener"] = {"status": "unknown"}

    # ── Circuit Breakers ───────────────────────────────────────────────────
    cb_issues = []
    for name, breaker in [("openrouter", openrouter_breaker), ("gateway_rpc", gateway_rpc_breaker)]:
        state = breaker.state
        if state == "open":
            cb_issues.append(f"{name} circuit breaker open")
        components[f"cb_{name}"] = {"state": state, "failures": breaker._failure_count}
    issues.extend(cb_issues)

    # ── Recent Errors (last 1 hour) ────────────────────────────────────────
    error_count_1h = 0
    try:
        from datetime import timedelta

        from sqlalchemy import func

        from app.core.time import utcnow
        from app.db.session import async_session_maker
        from app.models.activity_events import ActivityEvent

        async with async_session_maker() as session:
            one_hour_ago = utcnow() - timedelta(hours=1)
            result = await session.execute(
                __import__("sqlalchemy")
                .select(func.count(ActivityEvent.id))  # type: ignore[arg-type]
                .where(
                    ActivityEvent.event_type.startswith(ERROR_PREFIX),
                    ActivityEvent.created_at >= one_hour_ago,
                )
            )
            error_count_1h = result.scalar() or 0
    except Exception:
        pass

    components["recent_errors"] = {"count_1h": error_count_1h}
    if error_count_1h >= 10:
        issues.append(f"{error_count_1h} errors in last hour")

    # ── Cron Health (per-org gateway scan) ─────────────────────────────────
    # Walks both per-org workspaces (GATEWAY_WORKSPACES_ROOT/*/​.openclaw/cron/jobs.json)
    # and the legacy single-tenant fallback path. Aggregates failed counts across
    # all gateways. The previous implementation only checked the legacy path and
    # always returned status: "unknown" once per-org gateways shipped.
    cron_failed = 0
    cron_total = 0
    cron_gateways_scanned = 0
    try:
        import json
        import os
        from pathlib import Path

        candidate_files: list[Path] = []

        workspaces_root = os.environ.get("GATEWAY_WORKSPACES_ROOT")
        if workspaces_root:
            root = Path(workspaces_root)
            if root.exists():
                for org_dir in root.iterdir():
                    if not org_dir.is_dir():
                        continue
                    jobs_file = org_dir / ".openclaw" / "cron" / "jobs.json"
                    if jobs_file.exists():
                        candidate_files.append(jobs_file)

        # Legacy single-tenant fallback retired 2026-04-11. Per-org gateways
        # are the only source of truth — falling back to /app/gateway-cron was
        # double-counting Personal org cron jobs (phantom failures).
        for jobs_path in candidate_files:
            try:
                data = json.loads(jobs_path.read_text())
                jobs = data["jobs"] if isinstance(data, dict) and "jobs" in data else data
                if not isinstance(jobs, list):
                    continue
                cron_gateways_scanned += 1
                cron_total += len(jobs)
                for job in jobs:
                    raw_state = job.get("state") if isinstance(job, dict) else None
                    job_state: dict[str, Any] = raw_state if isinstance(raw_state, dict) else {}
                    last_status = job_state.get("lastRunStatus") or (
                        job.get("last_status") if isinstance(job, dict) else None
                    )
                    if last_status in ("error", "failed"):
                        cron_failed += 1
            except (json.JSONDecodeError, OSError):
                continue

        if cron_gateways_scanned == 0:
            components["cron_jobs"] = {"status": "no_data"}
        else:
            components["cron_jobs"] = {
                "status": "ok" if cron_failed == 0 else "failing",
                "failed": cron_failed,
                "total": cron_total,
                "gateways_scanned": cron_gateways_scanned,
            }
    except Exception as exc:
        components["cron_jobs"] = {"status": "unknown", "error": str(exc)[:100]}

    if cron_failed > 0:
        issues.append(f"{cron_failed} cron job(s) in failed state")

    # ── Overall Status ─────────────────────────────────────────────────────
    critical = any(k in ("postgresql down", "redis down") for k in issues)
    if critical:
        status = "down"
    elif issues:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "issues": issues,
        "components": components,
    }


api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth_router)
api_v1.include_router(agent_router)
api_v1.include_router(agents_router)
api_v1.include_router(activity_router)
api_v1.include_router(gateway_router)
api_v1.include_router(gateways_router)
api_v1.include_router(metrics_router)
api_v1.include_router(organizations_router)
api_v1.include_router(souls_directory_router)
api_v1.include_router(skills_marketplace_router)
api_v1.include_router(board_groups_router)
api_v1.include_router(board_group_memory_router)
api_v1.include_router(boards_router)
api_v1.include_router(email_router)
api_v1.include_router(email_inline_router)
api_v1.include_router(email_oauth_router)
api_v1.include_router(agent_email_router)
api_v1.include_router(agent_memory_vector_router)
api_v1.include_router(memory_vector_router)
api_v1.include_router(agent_contacts_router)
api_v1.include_router(contacts_router)
api_v1.include_router(polymarket_router)
api_v1.include_router(agent_polymarket_router)
api_v1.include_router(pentest_router)
api_v1.include_router(document_gen_router)
api_v1.include_router(microsoft_graph_router)
api_v1.include_router(google_calendar_router)
api_v1.include_router(file_serve_router)
api_v1.include_router(invoice_pdf_router)
api_v1.include_router(legal_router)
api_v1.include_router(memory_router)
api_v1.include_router(gateway_live_router)
api_v1.include_router(crypto_trading_router)
api_v1.include_router(paper_trading_router)
api_v1.include_router(paper_bets_router)
api_v1.include_router(cost_tracker_router)
api_v1.include_router(org_settings_router)
api_v1.include_router(cron_jobs_router)
api_v1.include_router(chat_projects_router)
api_v1.include_router(model_registry_router)
api_v1.include_router(board_memory_router)
api_v1.include_router(board_webhooks_router)
api_v1.include_router(board_onboarding_router)
api_v1.include_router(approvals_router)
api_v1.include_router(tasks_router)
api_v1.include_router(task_custom_fields_router)
api_v1.include_router(tags_router)
api_v1.include_router(users_router)
api_v1.include_router(watchlist_router)
api_v1.include_router(bookkeeping_router)
api_v1.include_router(org_config_router)
api_v1.include_router(skill_config_router)
api_v1.include_router(industry_templates_router)
api_v1.include_router(platform_admin_router)
api_v1.include_router(wechat_auth_router)
api_v1.include_router(wecom_router)
api_v1.include_router(document_intake_router)
api_v1.include_router(observability_router)
app.include_router(api_v1)

add_pagination(app)
logger.debug("app.routes.registered count=%s", len(app.routes))
