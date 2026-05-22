import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from src.vos_studio_mcp._instance import mcp
from src.vos_studio_mcp.config.env import settings
from src.vos_studio_mcp.config.logging import configure_logging

# Observability — must be initialized before tools and routes (ADR-0030)
configure_logging(debug=settings.debug)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        send_default_pii=False,
    )

# Register all tools by importing the tools package (ADR-0006)
import src.vos_studio_mcp.tools  # noqa: F401, E402

# FastAPI wraps FastMCP to add HTTP middleware (auth, rate limiting, webhooks)
app = FastAPI(
    title="VOS Studio MCP",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
)

# Mount the MCP server as an ASGI sub-application (ADR-0002)
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def http_health() -> dict:
    """HTTP health check — for load balancers and uptime monitors."""
    return {"status": "ok", "server": settings.mcp_server_name}
