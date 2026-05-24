"""close_sprint MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.sprint import CloseSprintInput, CloseSprintResponse
from vos_studio_mcp.services.sprint_service import close_sprint as close_sprint_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_close_sprint_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def close_sprint(data: CloseSprintInput) -> CloseSprintResponse:
        """Close a creative sprint. No new assets can be prepared after closing.

        Call this when the sprint's creative output is complete or budget is exhausted.
        Typically followed by record_asset_performance for each key asset.
        """
        return await close_sprint_service(data)
