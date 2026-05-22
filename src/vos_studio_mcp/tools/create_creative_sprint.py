"""create_creative_sprint MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.sprint import SprintInput, SprintResponse
from vos_studio_mcp.services.sprint_service import (
    create_creative_sprint as create_sprint_service,
)


def register_create_sprint_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def create_creative_sprint(data: SprintInput) -> SprintResponse:
        """Open a new creative sprint with a pre-authorized budget (ADR-0005).

        The agent operates autonomously within the approved budget ceiling.
        Returns sprint_id and budget_status for all subsequent tools.
        """
        return await create_sprint_service(data)
