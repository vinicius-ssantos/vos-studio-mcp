"""request_api_video MCP tool — trigger Higgsfield video generation via API credits."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.api_video import ApiVideoInput, ApiVideoResponse
from vos_studio_mcp.services.generation_service import request_api_video as _service


def register_request_api_video_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def request_api_video(data: ApiVideoInput) -> ApiVideoResponse:
        """Queue a video generation job via the Higgsfield API.

        Validates the sprint is open and within budget before submitting.
        Requires an approval_token confirming the operator has pre-approved
        this paid action (ADR-0005). Returns a job_id to poll with
        get_video_job_status.
        """
        return await _service(data)
