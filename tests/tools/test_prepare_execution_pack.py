"""Tool-layer tests for prepare_execution_pack (Issue #55)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.execution_pack import ExecutionPackResponse, PrepareExecutionPackInput

_PATCH_SERVICE = "vos_studio_mcp.tools.prepare_execution_pack._prepare_execution_pack"


def _make_mock_mcp():
    captured: dict = {}
    mock_mcp = MagicMock()

    def _tool(**kwargs):
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn
        return decorator

    mock_mcp.tool = _tool
    return mock_mcp, captured


def _make_response(stage: str = "stage_0") -> ExecutionPackResponse:
    return ExecutionPackResponse(
        status="ready",
        sprint_id="s-1",
        asset_stage=stage,
        asset_stage_label="Stage 0 â€” Anchor Image",
        provider="manual",
        mode="dashboard_manual",
        objective="Produce anchor image for SuperApp.",
        operator_steps=[],
        qa_criteria=["Check resolution"],
        negative_constraints=["No watermarks"],
        output_spec={"format": "JPEG/PNG"},
        summary="Pack ready.",
        next_action="register_manual_asset",
    )


@pytest.mark.asyncio
async def test_delegates_to_service() -> None:
    from vos_studio_mcp.tools.prepare_execution_pack import register_prepare_execution_pack_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_execution_pack_tools(mock_mcp)

    expected = _make_response()
    with patch(_PATCH_SERVICE, new=AsyncMock(return_value=expected)):
        result = await captured["prepare_execution_pack"](
            data=PrepareExecutionPackInput(sprint_id="s-1", asset_stage="stage_0")
        )

    assert result.status == "ready"
    assert result.asset_stage == "stage_0"


@pytest.mark.asyncio
async def test_stage_c_returns_ready() -> None:
    from vos_studio_mcp.tools.prepare_execution_pack import register_prepare_execution_pack_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_execution_pack_tools(mock_mcp)

    expected = _make_response("stage_c")
    with patch(_PATCH_SERVICE, new=AsyncMock(return_value=expected)):
        result = await captured["prepare_execution_pack"](
            data=PrepareExecutionPackInput(sprint_id="s-1", asset_stage="stage_c")
        )

    assert result.asset_stage == "stage_c"
    assert result.next_action == "register_manual_asset"


@pytest.mark.asyncio
async def test_repair_stage_next_action_is_review() -> None:
    from vos_studio_mcp.tools.prepare_execution_pack import register_prepare_execution_pack_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_execution_pack_tools(mock_mcp)

    repair_resp = ExecutionPackResponse(
        status="ready",
        sprint_id="s-1",
        asset_stage="repair",
        asset_stage_label="Repair Variant",
        provider="manual",
        mode="dashboard_manual",
        objective="Repair.",
        operator_steps=[],
        qa_criteria=[],
        negative_constraints=[],
        output_spec={},
        summary="Pack ready.",
        next_action="review_asset_quality",
    )

    with patch(_PATCH_SERVICE, new=AsyncMock(return_value=repair_resp)):
        result = await captured["prepare_execution_pack"](
            data=PrepareExecutionPackInput(sprint_id="s-1", asset_stage="repair")
        )

    assert result.next_action == "review_asset_quality"


@pytest.mark.asyncio
async def test_blocked_sprint_returns_blocked() -> None:
    from vos_studio_mcp.tools.prepare_execution_pack import register_prepare_execution_pack_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_execution_pack_tools(mock_mcp)

    blocked_resp = ExecutionPackResponse(
        status="blocked",
        sprint_id="s-1",
        asset_stage="stage_0",
        asset_stage_label="Stage 0 â€” Anchor Image",
        provider="manual",
        mode="dashboard_manual",
        objective="",
        operator_steps=[],
        qa_criteria=[],
        negative_constraints=[],
        output_spec={},
        summary="Sprint is closed.",
        next_action="sprint_is_closed",
    )

    with patch(_PATCH_SERVICE, new=AsyncMock(return_value=blocked_resp)):
        result = await captured["prepare_execution_pack"](
            data=PrepareExecutionPackInput(sprint_id="s-1", asset_stage="stage_0")
        )

    assert result.status == "blocked"
    assert result.next_action == "sprint_is_closed"
