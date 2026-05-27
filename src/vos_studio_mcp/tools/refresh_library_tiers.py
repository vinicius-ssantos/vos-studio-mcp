"""refresh_library_tiers MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.library_maintenance import RefreshLibraryTiersResponse
from vos_studio_mcp.services.library_maintenance_service import (
    refresh_library_tiers as do_refresh,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_refresh_library_tiers_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def refresh_library_tiers() -> RefreshLibraryTiersResponse:
        """Recalculate performance stats and auto-promote tiers for all prompt templates.

        Aggregates PerformanceRecord data from sprints linked via
        derived_from_sprint_ids and applies tier rules:
          - top_performer : ≥10 records, avg CTR ≥ 5 %
          - tested        : ≥5 records,  avg CTR ≥ 3 %
          - experimental  : below all thresholds

        Runs automatically every day at 03:30 UTC via Celery Beat.
        Call this tool to trigger an immediate recalculation after bulk
        performance data has been imported.
        """
        result = await do_refresh()
        return RefreshLibraryTiersResponse(
            status="ok",
            templates_updated=result["updated"],
            tiers_changed=result["promoted"],
            summary=(
                f"{result['updated']} template(s) updated, "
                f"{result['promoted']} tier change(s) applied."
            ),
            next_action="search_library",
        )
