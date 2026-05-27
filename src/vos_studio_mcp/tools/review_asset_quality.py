"""review_asset_quality MCP tool (Issue #57)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.asset_review import ReviewAssetInput, ReviewAssetResponse
from vos_studio_mcp.services.asset_review_service import review_asset as _review_asset
from vos_studio_mcp.tools._instrumentation import instrument


def register_review_asset_quality_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def review_asset_quality(data: ReviewAssetInput) -> ReviewAssetResponse:
        """Review a generated asset against VOS quality criteria.

        Records QA outcome (approved / needs_repair / rejected) for each asset
        before promotion to the creative library. Pure composition — no paid calls.
        Checks product consistency, label accuracy, campaign coherence, mobile
        readability, endcard correctness, and claim safety.
        """
        client_id = get_current_client_id()
        if client_id is None:
            raise VosError(ErrorCode.AUTH_REQUIRED, "Authentication required")
        return await _review_asset(client_id, data)
