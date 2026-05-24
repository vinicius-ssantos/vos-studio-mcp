"""search_library MCP tool — keyword + faceted search over the prompt library (Issue #32)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.prompt_template import SearchLibraryInput, SearchLibraryResponse
from vos_studio_mcp.services.prompt_library_service import search_library as _service


def register_search_library_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search_library(data: SearchLibraryInput) -> SearchLibraryResponse:
        """Search the cross-client prompt library by keyword and/or tag filters.

        At least one filter must be provided.  Keyword search (query) matches
        against template name, description, and prompt text.  Tag filters
        (industry, format, objective, platform) narrow results further.

        Use min_tier='top_performer' to retrieve only proven templates.
        Results are ranked by performance tier (top_performer first), then by
        usage_count.

        Returns up to `limit` results (default 10, max 50).

        next_action guidance:
        - If results found: use 'prepare_video_blueprint' with a chosen template_id
        - If no results: use 'promote_to_library' to add a new template
        """
        return await _service(data)
