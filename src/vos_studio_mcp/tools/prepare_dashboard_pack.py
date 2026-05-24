"""prepare_dashboard_pack MCP tool."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.pack import DashboardPackInput, DashboardPackResponse
from vos_studio_mcp.services.providers.base import BudgetLimit, GenerationParams
from vos_studio_mcp.services.providers.manual_dashboard import ManualDashboardAdapter
from vos_studio_mcp.services.sprint_service import get_sprint_status
from vos_studio_mcp.tools._instrumentation import instrument

_adapter = ManualDashboardAdapter()


def register_prepare_dashboard_pack_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def prepare_dashboard_pack(data: DashboardPackInput) -> DashboardPackResponse:
        """Prepare a manual generation pack for the operator to execute on the provider dashboard.

        Validates the sprint is open before producing the pack.
        Returns checklist, naming convention, and QA criteria.
        After generation, call register_manual_asset with the result.
        """
        sprint_status = await get_sprint_status(data.sprint_id)
        if sprint_status.sprint_status != "open":
            return DashboardPackResponse(
                status="blocked",
                sprint_id=data.sprint_id,
                prompt="",
                provider="",
                model="",
                settings={},
                checklist=[],
                naming_convention="",
                qa_criteria=[],
                next_action=f"sprint_is_{sprint_status.sprint_status}",
            )

        params = GenerationParams(
            sprint_id=data.sprint_id,
            prompt_version=data.prompt_version,
            preset_version=data.preset_version,
            mode="dashboard_manual",
            budget_limit=BudgetLimit(max_spend_usd=0.0),
        )
        pack = await _adapter.prepare_manual_pack(params)
        return DashboardPackResponse(
            status="ready",
            sprint_id=data.sprint_id,
            prompt=pack.prompt,
            provider=pack.provider,
            model=pack.model,
            settings=pack.settings,
            checklist=pack.checklist,
            naming_convention=pack.naming_convention,
            qa_criteria=pack.qa_criteria,
            negative_prompt=pack.negative_prompt,
            next_action="register_manual_asset",
        )
