"""list_sprints MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.sprint import SprintListFilters, SprintListResponse
from vos_studio_mcp.services.sprint_service import list_sprints as list_sprints_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_list_sprints_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def list_sprints(
        client_id: str,
        filters: SprintListFilters | None = None,
    ) -> SprintListResponse:
        """List sprints for a client, newest first.

        Use filters.status='open' to show only active sprints or 'closed' for
        completed ones. Returns sprint_id, product_name, status, spend, and
        asset_count so you can identify which sprint to work with next.
        """
        return await list_sprints_service(client_id, filters)
