"""MCP tool registration."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.tools.close_sprint import register_close_sprint_tools
from vos_studio_mcp.tools.create_client import register_create_client_tools
from vos_studio_mcp.tools.create_creative_sprint import register_create_sprint_tools
from vos_studio_mcp.tools.get_sprint_status import register_get_sprint_status_tools
from vos_studio_mcp.tools.get_video_job_status import register_get_video_job_status_tools
from vos_studio_mcp.tools.list_sprint_assets import register_list_sprint_assets_tools
from vos_studio_mcp.tools.prepare_dashboard_pack import register_prepare_dashboard_pack_tools
from vos_studio_mcp.tools.record_asset_performance import register_record_asset_performance_tools
from vos_studio_mcp.tools.register_manual_asset import register_manual_asset_tools
from vos_studio_mcp.tools.request_api_video import register_request_api_video_tools
from vos_studio_mcp.tools.save_brand_kit import register_save_brand_kit_tools
from vos_studio_mcp.tools.status import register_status_tools


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on the provided FastMCP instance."""
    register_status_tools(mcp)
    register_create_client_tools(mcp)
    register_save_brand_kit_tools(mcp)
    register_create_sprint_tools(mcp)
    register_get_sprint_status_tools(mcp)
    register_prepare_dashboard_pack_tools(mcp)
    register_list_sprint_assets_tools(mcp)
    register_manual_asset_tools(mcp)
    register_close_sprint_tools(mcp)
    register_record_asset_performance_tools(mcp)
    register_request_api_video_tools(mcp)
    register_get_video_job_status_tools(mcp)
