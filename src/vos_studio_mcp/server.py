"""FastAPI/FastMCP application entrypoint."""

import logging
from typing import Any, cast

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from vos_studio_mcp.auth.middleware import auth_middleware
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import VosError
from vos_studio_mcp.observability.logging import configure_logging
from vos_studio_mcp.observability.middleware import correlation_middleware
from vos_studio_mcp.routes.webhooks import router as webhooks_router
from vos_studio_mcp.services.status import get_server_status
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

mcp = FastMCP(settings.mcp_server_name)
register_tools(mcp)

app = FastAPI(title=settings.mcp_server_name, debug=settings.debug)
# Middleware executes in reverse registration order: correlation runs first, then auth.
app.middleware("http")(auth_middleware)
app.middleware("http")(correlation_middleware)
# Webhook routes bypass auth middleware via _OPEN_PREFIXES in auth/middleware.py
app.include_router(webhooks_router)


@app.exception_handler(VosError)
async def vos_error_handler(_request: Request, exc: VosError) -> JSONResponse:
    """Translate domain errors into compact structured JSON (ADR-0011, ADR-0030)."""
    log.warning("vos_error", extra={"error_code": exc.error_code, "message": exc.message})
    return JSONResponse(
        status_code=400,
        content={"error_code": exc.error_code, "message": exc.message},
    )


@app.get("/health")
async def health() -> dict[str, str | None]:
    """Return a minimal HTTP health check payload."""
    status = get_server_status(settings)
    return {
        "status": status.status,
        "service": status.service,
        "version": status.version,
    }


def _mount_mcp_app(fastapi_app: FastAPI, mcp_server: FastMCP) -> None:
    """Mount the FastMCP ASGI app when supported by the installed SDK."""
    for method_name in ("streamable_http_app", "sse_app"):
        method = getattr(mcp_server, method_name, None)
        if callable(method):
            fastapi_app.mount("/mcp", cast(Any, method)())
            return


_mount_mcp_app(app, mcp)
