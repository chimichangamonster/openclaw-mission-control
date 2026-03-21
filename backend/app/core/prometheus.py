"""Prometheus metrics instrumentation for the FastAPI backend."""

from __future__ import annotations

from prometheus_client import Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator

app_info = Info("mc_app", "Mission Control backend metadata")
app_info.info({"version": "0.1.0", "app": "mission-control"})

db_pool_size = Gauge("mc_db_pool_size", "SQLAlchemy connection pool size")
db_pool_checked_out = Gauge("mc_db_pool_checked_out", "SQLAlchemy connections checked out")
gateway_listener_connected = Gauge(
    "mc_gateway_listener_connected",
    "Whether the gateway WebSocket listener is connected (1=yes, 0=no)",
)

instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    excluded_handlers=["/health", "/healthz", "/readyz", "/metrics"],
)


def setup_metrics(app):  # noqa: ANN001
    """Attach Prometheus instrumentation to the FastAPI app."""
    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
    )
