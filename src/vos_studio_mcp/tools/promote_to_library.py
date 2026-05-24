"""promote_to_library MCP tool (ADR-0029)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.schemas.prompt_template import PromoteToLibraryInput, PromoteToLibraryResponse
from vos_studio_mcp.services.prompt_library_service import (
    promote_to_library as promote_to_library_service,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_promote_to_library_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def promote_to_library(data: PromoteToLibraryInput) -> PromoteToLibraryResponse:
        """Promote an anonymized prompt version to the cross-client prompt library.

        This is a human-approved, deliberate action. Use confirmed=False first to
        review the anonymization checklist. Only set confirmed=True after replacing
        all brand-specific content with {{placeholders}}.

        The prompt_template field must contain at least one {{placeholder}}.
        """
        operator_id = get_current_client_id() or "unknown"
        return await promote_to_library_service(data, operator_id)
