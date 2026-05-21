"""MCP tool registration."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.tools.status import register_status_tools


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on the provided FastMCP instance."""

    register_status_tools(mcp)
