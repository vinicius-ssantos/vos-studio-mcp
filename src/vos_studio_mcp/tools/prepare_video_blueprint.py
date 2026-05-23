"""prepare_video_blueprint MCP tool (issue #13)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.blueprint import VideoBlueprintInput, VideoBlueprintResponse
from vos_studio_mcp.services.blueprint_service import (
    prepare_video_blueprint as _prepare_video_blueprint,
)


def register_prepare_video_blueprint_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def prepare_video_blueprint(data: VideoBlueprintInput) -> VideoBlueprintResponse:
        """Compose a director-level video blueprint from sprint and brand kit context.

        Produces a detailed shot plan, per-provider execution packs, negative
        prompt list, manual production checklist, and cost/risk notes — all
        derived from stored sprint and brand kit data with no paid API calls.

        Use this before any video generation step (API or manual) to align the
        creative team on intent, camera direction, and execution parameters.
        After blueprint review, proceed with prepare_dashboard_pack or
        request_api_video for each provider target.
        """
        return await _prepare_video_blueprint(data)
