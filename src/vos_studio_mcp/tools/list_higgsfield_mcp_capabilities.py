"""list_higgsfield_mcp_capabilities MCP tool (ADR-0044, Issue #73)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.higgsfield_mcp import HighgsfieldMcpCapabilitiesResponse
from vos_studio_mcp.services.mcp_clients.higgsfield import (
    list_higgsfield_mcp_capabilities as _svc,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_list_higgsfield_mcp_capabilities_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def list_higgsfield_mcp_capabilities() -> HighgsfieldMcpCapabilitiesResponse:
        """Probe the Higgsfield MCP server and return its available tools, resources, and prompts.

        Performs an MCP initialize handshake against the configured
        HIGGSFIELD_MCP_URL and lists capabilities without triggering any
        generation or incurring cost.

        Returns one of:
          - status="ok"            — connected; tool/resource/prompt lists populated
          - status="disabled"      — HIGGSFIELD_MCP_ENABLED is false
          - status="auth_required" — token absent or rejected (HTTP 401)
          - status="unreachable"   — network error, timeout, or unexpected HTTP error

        No paid action is performed. Use request_api_video for actual generation.
        """
        return await _svc()
