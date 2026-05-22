import structlog

from src.vos_studio_mcp._instance import mcp
from src.vos_studio_mcp.config.env import settings

log = structlog.get_logger(__name__)


@mcp.tool()
async def health_check() -> dict:
    """Returns server health status. Use this to verify the MCP server is reachable."""
    log.info("health_check_called")
    return {
        "status": "ok",
        "server": settings.mcp_server_name,
    }
