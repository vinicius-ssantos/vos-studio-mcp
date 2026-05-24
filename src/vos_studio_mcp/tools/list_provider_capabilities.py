"""Provider capability MCP tools."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.provider import ProviderCapabilitiesResponse
from vos_studio_mcp.services.providers.capabilities import list_provider_capabilities
from vos_studio_mcp.tools._instrumentation import instrument


def register_provider_capability_tools(mcp: FastMCP) -> None:
    """Register provider capability tools."""

    @mcp.tool()
    @instrument
    async def list_provider_capabilities_tool(
        include_disabled: bool = False,
    ) -> ProviderCapabilitiesResponse:
        """Return available creative provider capabilities without executing providers."""

        providers = list_provider_capabilities(include_disabled=include_disabled)
        return ProviderCapabilitiesResponse(
            providers=providers,
            total=len(providers),
            next_action="select_provider_by_capability_before_generation",
        )
