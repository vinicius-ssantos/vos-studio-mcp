"""record_asset_performance MCP tool (ADR-0025)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.performance import PerformanceInput, PerformanceResponse
from vos_studio_mcp.services.performance_service import (
    record_asset_performance as record_service,
)


def register_record_asset_performance_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def record_asset_performance(data: PerformanceInput) -> PerformanceResponse:
        """Record the real-world performance of a registered asset (ADR-0025).

        Score 1-5, label top_performer/failed/neutral.
        Supplying hook_label or angle_label for top_performer assets updates the brand
        kit's performance memory so future sprints inherit proven patterns.
        Failed assets append to failed_approaches to avoid repeating mistakes.
        """
        return await record_service(data)
