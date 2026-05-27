"""prepare_creative_brief MCP tool (Issue #48)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.creative_brief import CreativeBriefInput, CreativeBriefResponse
from vos_studio_mcp.services.creative_brief_service import (
    prepare_creative_brief as _prepare_creative_brief,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_prepare_creative_brief_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def prepare_creative_brief(data: CreativeBriefInput) -> CreativeBriefResponse:
        """Parse a raw client brief and produce a structured creative brief with assets, angles, and next actions.

        Pure composition — no paid API calls. Extracts campaign objective, target persona,
        pain points, objections, creative angles, required assets, and sprint recommendations.
        """
        client_id = get_current_client_id()
        if client_id is None:
            raise VosError(ErrorCode.AUTH_REQUIRED, "Authentication required")
        return await _prepare_creative_brief(client_id, data)
