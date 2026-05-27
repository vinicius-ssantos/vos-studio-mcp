"""Tool-layer tests for review_asset_quality (Issue #57)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.asset_review import (
    AssetReviewCriteria,
    ReviewAssetInput,
    ReviewAssetResponse,
)

_CLIENT_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
_ASSET_ID = "aaaaaaaabbbbccccdddd1234567890ab"
_SPRINT_ID = "00000000-0000-0000-0000-000000000001"
_PATCH_AUTH = "vos_studio_mcp.tools.review_asset_quality.get_current_client_id"
_PATCH_SERVICE = "vos_studio_mcp.tools.review_asset_quality._review_asset"


def _make_mock_mcp() -> tuple[MagicMock, dict]:
    captured: dict = {}
    mock_mcp = MagicMock()

    def _tool(**kwargs):
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn

        return decorator

    mock_mcp.tool = _tool
    return mock_mcp, captured


def _make_input(**kwargs) -> ReviewAssetInput:
    return ReviewAssetInput(
        asset_id=str(kwargs.get("asset_id", _ASSET_ID)),
        sprint_id=str(kwargs.get("sprint_id", _SPRINT_ID)),
        criteria=kwargs.get("criteria", AssetReviewCriteria()),
        notes=str(kwargs.get("notes", "")),
        reviewer_outcome=kwargs.get("reviewer_outcome", "approved"),
    )


def _make_response(outcome: str = "approved") -> ReviewAssetResponse:
    return ReviewAssetResponse(
        status="reviewed",
        asset_id=_ASSET_ID,
        sprint_id=_SPRINT_ID,
        outcome=outcome,  # type: ignore[arg-type]
        criteria_passed=["product_consistency"],
        criteria_failed=[],
        notes="",
        approval_checklist=["✓ Product consistency verified"],
        summary=f"Asset {_ASSET_ID[:8]}... {outcome}. 0 criteria failed.",
        next_action="promote_to_library" if outcome == "approved" else "register_manual_asset",
    )


# ---------------------------------------------------------------------------
# AUTH_REQUIRED when no client_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_required_when_no_client_id() -> None:
    from vos_studio_mcp.tools.review_asset_quality import register_review_asset_quality_tools

    mock_mcp, captured = _make_mock_mcp()
    register_review_asset_quality_tools(mock_mcp)

    with patch(_PATCH_AUTH, return_value=None), pytest.raises(VosError) as exc_info:
        await captured["review_asset_quality"](data=_make_input())

    assert exc_info.value.error_code == ErrorCode.AUTH_REQUIRED


# ---------------------------------------------------------------------------
# Approved outcome when all criteria pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_outcome_when_all_criteria_pass() -> None:
    from vos_studio_mcp.tools.review_asset_quality import register_review_asset_quality_tools

    mock_mcp, captured = _make_mock_mcp()
    register_review_asset_quality_tools(mock_mcp)

    mock_resp = _make_response("approved")
    data = _make_input(reviewer_outcome="approved")

    with (
        patch(_PATCH_AUTH, return_value=_CLIENT_ID),
        patch(_PATCH_SERVICE, new=AsyncMock(return_value=mock_resp)) as mock_svc,
    ):
        result = await captured["review_asset_quality"](data=data)

    mock_svc.assert_awaited_once_with(_CLIENT_ID, data)
    assert result.outcome == "approved"
    assert result is mock_resp


# ---------------------------------------------------------------------------
# needs_repair auto-corrects when criteria fail but outcome is "approved"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_needs_repair_auto_corrects_when_criteria_fail() -> None:
    from vos_studio_mcp.tools.review_asset_quality import register_review_asset_quality_tools

    mock_mcp, captured = _make_mock_mcp()
    register_review_asset_quality_tools(mock_mcp)

    mock_resp = ReviewAssetResponse(
        status="reviewed",
        asset_id=_ASSET_ID,
        sprint_id=_SPRINT_ID,
        outcome="needs_repair",
        criteria_passed=["label_accuracy"],
        criteria_failed=["product_consistency"],
        notes="",
        approval_checklist=["Fix required: product consistency"],
        summary=f"Asset {_ASSET_ID[:8]}... needs_repair. 1 criteria failed.",
        next_action="register_manual_asset",
    )
    data = _make_input(
        criteria=AssetReviewCriteria(product_consistency=False),
        reviewer_outcome="approved",
    )

    with (
        patch(_PATCH_AUTH, return_value=_CLIENT_ID),
        patch(_PATCH_SERVICE, new=AsyncMock(return_value=mock_resp)),
    ):
        result = await captured["review_asset_quality"](data=data)

    assert result.outcome == "needs_repair"
    assert result.next_action == "register_manual_asset"


# ---------------------------------------------------------------------------
# Rejected returns correct next_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejected_returns_correct_next_action() -> None:
    from vos_studio_mcp.tools.review_asset_quality import register_review_asset_quality_tools

    mock_mcp, captured = _make_mock_mcp()
    register_review_asset_quality_tools(mock_mcp)

    mock_resp = ReviewAssetResponse(
        status="reviewed",
        asset_id=_ASSET_ID,
        sprint_id=_SPRINT_ID,
        outcome="rejected",
        criteria_passed=[],
        criteria_failed=["no_risky_claims"],
        notes="Makes unverifiable health claims",
        approval_checklist=["✗ Asset rejected — do not promote", "Review notes: Makes unverifiable health claims"],
        summary=f"Asset {_ASSET_ID[:8]}... rejected. 1 criteria failed.",
        next_action="create_creative_sprint",
    )
    data = _make_input(
        criteria=AssetReviewCriteria(no_risky_claims=False),
        reviewer_outcome="rejected",
        notes="Makes unverifiable health claims",
    )

    with (
        patch(_PATCH_AUTH, return_value=_CLIENT_ID),
        patch(_PATCH_SERVICE, new=AsyncMock(return_value=mock_resp)),
    ):
        result = await captured["review_asset_quality"](data=data)

    assert result.outcome == "rejected"
    assert result.next_action == "create_creative_sprint"


# ---------------------------------------------------------------------------
# Tool delegates to service with correct args
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_delegates_to_service_with_client_id() -> None:
    from vos_studio_mcp.tools.review_asset_quality import register_review_asset_quality_tools

    mock_mcp, captured = _make_mock_mcp()
    register_review_asset_quality_tools(mock_mcp)

    mock_resp = _make_response("approved")
    data = _make_input()

    with (
        patch(_PATCH_AUTH, return_value=_CLIENT_ID),
        patch(_PATCH_SERVICE, new=AsyncMock(return_value=mock_resp)) as mock_svc,
    ):
        await captured["review_asset_quality"](data=data)

    mock_svc.assert_awaited_once_with(_CLIENT_ID, data)
