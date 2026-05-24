"""list_sprint_assets MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.asset import AssetListResponse
from vos_studio_mcp.services.asset_service import list_sprint_assets as list_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_list_sprint_assets_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def list_sprint_assets(sprint_id: str) -> AssetListResponse:
        """List all assets registered against a sprint.

        Use this to review what has been produced before deciding on next steps.
        """
        return await list_service(sprint_id)
