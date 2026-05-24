"""get_sprint_status MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.sprint import SprintStatusResponse
from vos_studio_mcp.services.sprint_service import get_sprint_status as get_status_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_get_sprint_status_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def get_sprint_status(sprint_id: str) -> SprintStatusResponse:
        """Return the current status of a creative sprint including budget and asset count.

        Call this before preparing a new pack to confirm budget headroom.
        """
        return await get_status_service(sprint_id)
