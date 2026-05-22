"""Unit tests for prepare_dashboard_pack tool logic."""

import uuid

import pytest
from pydantic import ValidationError

from vos_studio_mcp.schemas.pack import DashboardPackInput, DashboardPackResponse
from vos_studio_mcp.services.providers.base import BudgetLimit, GenerationParams
from vos_studio_mcp.services.providers.manual_dashboard import ManualDashboardAdapter


def _make_params(sprint_id: str) -> GenerationParams:
    return GenerationParams(
        sprint_id=sprint_id,
        prompt_version="v1",
        preset_version="p1",
        mode="dashboard_manual",
        budget_limit=BudgetLimit(max_spend_usd=0.0),
    )


@pytest.mark.asyncio
async def test_manual_adapter_returns_pack_with_checklist():
    adapter = ManualDashboardAdapter()
    sprint_id = str(uuid.uuid4())
    pack = await adapter.prepare_manual_pack(_make_params(sprint_id))

    assert pack.provider == "manual_dashboard"
    assert len(pack.checklist) > 0
    assert len(pack.qa_criteria) > 0
    assert sprint_id in pack.naming_convention


@pytest.mark.asyncio
async def test_manual_adapter_estimate_cost_is_zero():
    adapter = ManualDashboardAdapter()
    estimate = await adapter.estimate_cost(_make_params("any"))
    assert estimate.estimated_usd == 0.0


def test_dashboard_pack_input_requires_versions():
    with pytest.raises(ValidationError):
        DashboardPackInput(sprint_id="s1", prompt_version="", preset_version="p1")


def test_dashboard_pack_response_shape():
    resp = DashboardPackResponse(
        status="ready",
        sprint_id="s1",
        prompt="a cinematic photo",
        provider="manual_dashboard",
        model="",
        settings={},
        checklist=["step 1"],
        naming_convention="spr-s1-v1",
        qa_criteria=["no forbidden elements"],
        next_action="register_manual_asset",
    )
    assert resp.status == "ready"
    assert resp.next_action == "register_manual_asset"
