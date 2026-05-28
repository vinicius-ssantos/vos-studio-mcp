"""check_generation_readiness MCP tool — pre-flight validation before request_api_video."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.readiness import GenerationReadinessInput, GenerationReadinessResponse
from vos_studio_mcp.services.readiness_service import check_generation_readiness as _svc
from vos_studio_mcp.tools._instrumentation import instrument


def register_check_generation_readiness_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def check_generation_readiness(
        data: GenerationReadinessInput,
    ) -> GenerationReadinessResponse:
        """Validate all preconditions before submitting a generation request.

        Checks in a single call: provider enabled, circuit breaker state,
        API token configured, sprint open, and budget available.

        Call this before request_api_video to surface blockers early and avoid
        wasted API calls or budget charges.
        """
        return await _svc(data.provider, data.sprint_id, data.client_id)
