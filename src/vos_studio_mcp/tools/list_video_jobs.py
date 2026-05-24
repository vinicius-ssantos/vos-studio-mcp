"""list_video_jobs MCP tool — bulk status for all API-generated assets in a sprint."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.api_video import ListVideoJobsResponse
from vos_studio_mcp.services.generation_service import list_video_jobs as _service


def register_list_video_jobs_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_video_jobs(sprint_id: str, client_id: str) -> ListVideoJobsResponse:
        """Return all API-generated video jobs in a sprint with aggregated status counts.

        More efficient than calling get_video_job_status for each asset individually.
        Returns a summary with total/completed/processing/pending/failed counts and a
        next_action hint for the next step in the pipeline.

        Only includes assets with provider_job_id (API-generated). Manual assets are excluded.
        """
        return await _service(sprint_id, client_id)
