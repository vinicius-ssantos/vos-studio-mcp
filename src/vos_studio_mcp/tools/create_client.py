"""create_client MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.client import ClientInput, ClientResponse
from vos_studio_mcp.services.client_service import create_client as create_client_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_create_client_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def create_client(data: ClientInput) -> ClientResponse:
        """Create a new client record. Returns the client_id needed for subsequent tools."""
        return await create_client_service(data)
