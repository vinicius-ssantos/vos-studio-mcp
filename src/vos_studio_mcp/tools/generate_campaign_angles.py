"""generate_campaign_angles MCP tool (Issue #49)."""
from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.campaign_angles import CampaignAnglesInput, CampaignAnglesResponse
from vos_studio_mcp.services.campaign_angles_service import (
    generate_campaign_angles as _generate_campaign_angles,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_generate_campaign_angles_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def generate_campaign_angles(data: CampaignAnglesInput) -> CampaignAnglesResponse:
        """Generate diverse campaign angles for a product and target audience.

        Pure composition — no paid API calls. Produces N structurally distinct
        angles covering emotional, rational, social-proof, urgency, curiosity, and
        authority hooks. Use before prepare_creative_brief to explore creative territory.
        """
        client_id = get_current_client_id()
        if client_id is None:
            raise VosError(ErrorCode.AUTH_REQUIRED, "Authentication required")
        return await _generate_campaign_angles(client_id, data)
