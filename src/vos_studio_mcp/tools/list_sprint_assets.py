"""list_sprint_assets MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.asset import AssetListFilters, AssetListResponse
from vos_studio_mcp.services.asset_service import list_sprint_assets as list_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_list_sprint_assets_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def list_sprint_assets(
        sprint_id: str,
        filters: AssetListFilters | None = None,
    ) -> AssetListResponse:
        """List assets registered against a sprint, with optional filtering.

        Use filters.asset_stage to narrow to a specific production stage
        (e.g. stage_c, repair) and filters.qa_status to show only approved,
        needs_repair, or rejected assets. Omit filters to return all assets.
        """
        return await list_service(sprint_id, filters)
