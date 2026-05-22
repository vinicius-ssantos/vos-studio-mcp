from mcp.server.fastmcp import FastMCP

from src.vos_studio_mcp.config.env import settings

# Single FastMCP instance — tools import this and register via @mcp.tool()
mcp = FastMCP(settings.mcp_server_name)
