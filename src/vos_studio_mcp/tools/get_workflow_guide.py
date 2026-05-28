"""get_workflow_guide MCP tool — returns step-by-step tool sequences for a given goal."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.workflow_guide import WorkflowGuideInput, WorkflowGuideResponse
from vos_studio_mcp.services.workflow_guide_service import (
    get_workflow_guide as _svc,
)
from vos_studio_mcp.services.workflow_guide_service import (
    list_available_goals,
)
from vos_studio_mcp.tools._instrumentation import instrument


def register_get_workflow_guide_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def get_workflow_guide(data: WorkflowGuideInput) -> WorkflowGuideResponse:
        """Return an ordered step-by-step guide for a VOS creative workflow goal.

        Available goals: generate_video, register_manual_asset, onboard_client,
        review_and_approve_assets, performance_feedback.

        Each step lists the tool to call, its purpose, required inputs, and
        optional notes. Use this tool when starting a new workflow or when
        unsure which tool to call next.
        """
        _ = list_available_goals()  # eager load for docstring accuracy
        return _svc(data.goal)
