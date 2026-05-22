"""get_video_job_status MCP tool — check video generation progress."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.api_video import VideoJobStatusResponse
from vos_studio_mcp.services.generation_service import get_video_job_status as _service


def register_get_video_job_status_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_video_job_status(asset_id: str) -> VideoJobStatusResponse:
        """Check the current status of an API-generated video asset.

        Reads generation_status from the database without calling the provider.
        Poll this after request_api_video until generation_status is
        'completed' or 'failed'. On 'completed', storage_url holds the
        permanent R2 URL ready for pack preparation.
        """
        return await _service(asset_id)
