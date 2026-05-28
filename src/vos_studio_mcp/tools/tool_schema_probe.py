"""tool_schema_probe MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.status import ToolSchemaProbeResponse
from vos_studio_mcp.services.tool_catalog_service import (
    build_tool_schema_probe,
    registered_tools,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_tool_schema_probe_tools(mcp: FastMCP) -> None:
    """Register read-only MCP schema diagnostics."""

    @mcp.tool()
    @instrument
    async def tool_schema_probe(tool_name: str) -> ToolSchemaProbeResponse:
        """Inspect the currently advertised input schema for one MCP tool."""

        return build_tool_schema_probe(registered_tools(mcp), tool_name)
