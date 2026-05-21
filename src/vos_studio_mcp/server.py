"""FastAPI/FastMCP application entrypoint."""

from typing import Any, cast

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.observability.logging import configure_logging
from vos_studio_mcp.observability.middleware import correlation_middleware
from vos_studio_mcp.services.status import get_server_status
from vos_studio_mcp.tools import register_tools

settings = get_settings()
configure_logging(settings.log_level)

mcp = FastMCP(settings.mcp_server_name)
register_tools(mcp)

app = FastAPI(title=settings.mcp_server_name, debug=settings.debug)
app.middleware("http")(correlation_middleware)


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
