"""get_sprint_performance_summary MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.sprint import SprintPerformanceSummaryResponse
from vos_studio_mcp.services.sprint_service import (
    get_sprint_performance_summary as get_summary_service,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_get_sprint_performance_summary_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def get_sprint_performance_summary(
        sprint_id: str,
    ) -> SprintPerformanceSummaryResponse:
        """Return a per-stage quality and performance snapshot for a sprint.

        Aggregates assets by VOS production stage (stage_0, stage_a … final,
        repair) and returns approved/needs_repair/rejected counts and average
        performance score per stage. Use this before close_sprint to confirm
        at least one approved final-delivery asset exists.
        """
        return await get_summary_service(sprint_id)
