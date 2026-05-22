"""conclude_variant_test MCP tool (ADR-0027)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.variant import ConcludeVariantTestInput, ConcludeVariantTestResponse
from vos_studio_mcp.services.variant_service import (
    conclude_variant_test as conclude_variant_test_service,
)


def register_conclude_variant_test_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def conclude_variant_test(
        data: ConcludeVariantTestInput,
    ) -> ConcludeVariantTestResponse:
        """Conclude an A/B variant test within a creative sprint.

        Marks the winning variant (or inconclusive) for a VariantGroup.
        Use confirmed=False first to preview; set confirmed=True to commit.
        The winning variant's creative elements should then be added to the
        brand kit's proven_angles via save_brand_kit.
        """
        return await conclude_variant_test_service(data)
