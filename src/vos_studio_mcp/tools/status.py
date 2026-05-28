"""Status MCP tools."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.schemas.status import ServerStatus
from vos_studio_mcp.services.status import get_server_status as build_server_status
from vos_studio_mcp.services.tool_catalog_service import registered_tools
from vos_studio_mcp.tools._instrumentation import instrument


def register_status_tools(mcp: FastMCP) -> None:
    """Register status-related tools."""

    @mcp.tool()
    @instrument
    async def get_server_status() -> ServerStatus:
        """Return the current MCP server status."""

        return build_server_status(get_settings(), registered_tools(mcp))
