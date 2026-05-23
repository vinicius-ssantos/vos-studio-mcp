"""record_performance_metrics MCP tool — ADR-0025 Phase 2."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.performance_record import (
    PerformanceRecordInput,
    PerformanceRecordResponse,
)
from vos_studio_mcp.services.performance_record_service import (
    create_performance_record as _create_performance_record,
)


def register_record_performance_metrics_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def record_performance_metrics(data: PerformanceRecordInput) -> PerformanceRecordResponse:
        """Record structured campaign performance metrics for a delivered asset.

        Stores quantitative metrics (impressions, CTR, ROAS, conversions, etc.)
        alongside distribution context (platform, campaign, dates).

        These records inform the performance_context block in future sprint
        creation calls — giving the agent creative direction grounded in what
        actually worked for this client on this brand kit.

        Use after a campaign has run and you have platform metrics available.
        For lightweight recording without metrics, use record_asset_performance.
        """
        return await _create_performance_record(data)
