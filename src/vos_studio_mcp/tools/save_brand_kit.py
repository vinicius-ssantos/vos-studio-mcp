"""save_brand_kit MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.brand_kit import BrandKitInput, BrandKitResponse
from vos_studio_mcp.services.brand_kit_service import save_brand_kit as save_brand_kit_service


def register_save_brand_kit_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def save_brand_kit(data: BrandKitInput) -> BrandKitResponse:
        """Save or update the brand kit for a client. Returns brand_kit_id for sprint creation."""
        return await save_brand_kit_service(data)
