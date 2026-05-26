"""FastAPI/FastMCP application entrypoint."""

import logging
from typing import Any, cast

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from mcp.server.fastmcp import FastMCP
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from vos_studio_mcp.auth.middleware import auth_middleware
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import VosError
from vos_studio_mcp.observability.logging import configure_logging
from vos_studio_mcp.observability.metrics import metrics_response
from vos_studio_mcp.observability.middleware import (
    correlation_middleware,
    metrics_instrumentation_middleware,
)
from vos_studio_mcp.resources.playbook import register_resources_and_prompts
from vos_studio_mcp.routes.webhooks import router as webhooks_router
from vos_studio_mcp.services.status import get_health
from vos_studio_mcp.tools import register_tools

log = logging.getLogger(__name__)

settings = get_settings()
configure_logging(settings.log_level)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration(), CeleryIntegration()],
        send_default_pii=False,
    )

if settings.is_production and not (
    settings.oauth_issuer_url or settings.supabase_jwt_secret or settings.dev_bearer_token
):
    log.warning(
        "auth.not_configured_in_production — set OAUTH_ISSUER_URL, SUPABASE_JWT_SECRET, or DEV_BEARER_TOKEN"
    )

mcp = FastMCP(settings.mcp_server_name)
register_tools(mcp)
register_resources_and_prompts(mcp)

app = FastAPI(title=settings.mcp_server_name, debug=settings.debug)
# Middleware executes in reverse registration order:
# metrics_instrumentation runs outermost, then correlation, then auth.
app.middleware("http")(auth_middleware)
app.middleware("http")(correlation_middleware)
app.middleware("http")(metrics_instrumentation_middleware)
# Webhook routes bypass auth middleware via _OPEN_PREFIXES in auth/middleware.py
app.include_router(webhooks_router)


@app.exception_handler(VosError)
async def vos_error_handler(_request: Request, exc: VosError) -> JSONResponse:
    """Translate domain errors into compact structured JSON (ADR-0011, ADR-0030)."""
    log.warning("vos_error", extra={"error_code": exc.error_code, "error_message": exc.message})
    return JSONResponse(
        status_code=400,
        content={"error_code": exc.error_code, "message": exc.message},
    )


@app.get("/health")
async def health() -> dict[str, object]:
    """Return a detailed health check with per-component status.

    Overall status:
    - "ok"       — all components healthy
    - "degraded" — celery worker unreachable (web still serves)
    - "down"     — database or Redis unavailable
    """
    result = await get_health()
    return result.model_dump()


@app.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics for scraping.

    Returns standard Prometheus text format with:
    - vos_http_requests_total
    - vos_http_request_duration_seconds
    - vos_provider_calls_total
    - vos_circuit_breaker_open
    - vos_mcp_tool_calls_total
    """
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)


def _mount_mcp_app(fastapi_app: FastAPI, mcp_server: FastMCP) -> None:
    """Mount the FastMCP ASGI app when supported by the installed SDK."""
    for method_name in ("streamable_http_app", "sse_app"):
        method = getattr(mcp_server, method_name, None)
        if callable(method):
            fastapi_app.mount("/mcp", cast(Any, method)())
            return


_mount_mcp_app(app, mcp)

if __name__ == "__main__":
    mcp.run()
