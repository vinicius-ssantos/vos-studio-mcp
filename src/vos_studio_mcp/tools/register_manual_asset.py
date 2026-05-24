"""register_manual_asset MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.asset import AssetInput, AssetResponse
from vos_studio_mcp.services.asset_service import register_manual_asset as register_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_manual_asset_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def register_manual_asset(data: AssetInput) -> AssetResponse:
        """Register an asset produced manually on the provider dashboard.

        Call this after executing the pack from prepare_dashboard_pack.
        Returns asset_id linked to the sprint for tracking and feedback.
        """
        return await register_service(data)
