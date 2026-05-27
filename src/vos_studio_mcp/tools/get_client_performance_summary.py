"""get_client_performance_summary MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.client_analytics import ClientPerformanceSummaryResponse
from vos_studio_mcp.services.client_analytics_service import (
    get_client_performance_summary as _svc,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_get_client_performance_summary_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def get_client_performance_summary(
        client_id: str,
        period_days: int = 90,
    ) -> ClientPerformanceSummaryResponse:
        """Return aggregated performance metrics across all sprints for a client.

        Queries PerformanceRecord data for the given look-back window (default
        90 days) and returns:
          - avg CTR and ROAS across all records
          - best-performing platform (by top_performer count)
          - top 5 assets by CTR

        Use period_days to widen or narrow the window (max 730 days).
        Compare results across clients to identify cross-client best practices.
        """
        return await _svc(client_id, period_days)
