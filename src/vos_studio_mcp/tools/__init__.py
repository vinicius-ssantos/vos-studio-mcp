"""MCP tool registration."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.tools.close_sprint import register_close_sprint_tools
from vos_studio_mcp.tools.conclude_variant_test import register_conclude_variant_test_tools
from vos_studio_mcp.tools.create_client import register_create_client_tools
from vos_studio_mcp.tools.create_creative_sprint import register_create_sprint_tools
from vos_studio_mcp.tools.get_provider_usage_summary import (
    register_get_provider_usage_summary_tools,
)
from vos_studio_mcp.tools.get_sprint_status import register_get_sprint_status_tools
from vos_studio_mcp.tools.get_video_job_status import register_get_video_job_status_tools
from vos_studio_mcp.tools.list_sprint_assets import register_list_sprint_assets_tools
from vos_studio_mcp.tools.list_provider_capabilities import register_provider_capability_tools
from vos_studio_mcp.tools.list_video_jobs import register_list_video_jobs_tools
from vos_studio_mcp.tools.prepare_dashboard_pack import register_prepare_dashboard_pack_tools
from vos_studio_mcp.tools.prepare_video_blueprint import register_prepare_video_blueprint_tools
from vos_studio_mcp.tools.promote_to_library import register_promote_to_library_tools
from vos_studio_mcp.tools.record_asset_performance import register_record_asset_performance_tools
from vos_studio_mcp.tools.record_performance_metrics import (
    register_record_performance_metrics_tools,
)
from vos_studio_mcp.tools.register_manual_asset import register_manual_asset_tools
from vos_studio_mcp.tools.request_api_video import register_request_api_video_tools
from vos_studio_mcp.tools.save_brand_kit import register_save_brand_kit_tools
from vos_studio_mcp.tools.search_library import register_search_library_tools
from vos_studio_mcp.tools.set_client_webhook import register_set_client_webhook_tools
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
    register_list_video_jobs_tools(mcp)
    register_provider_capability_tools(mcp)
    register_conclude_variant_test_tools(mcp)
    register_promote_to_library_tools(mcp)
    register_search_library_tools(mcp)
    register_prepare_video_blueprint_tools(mcp)
    register_record_performance_metrics_tools(mcp)
    register_set_client_webhook_tools(mcp)
    register_get_provider_usage_summary_tools(mcp)
