"""Unit tests for prepare_creative_brief MCP tool (Issue #48)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.creative_brief import (
    BriefConstraints,
    CreativeBriefInput,
    CreativeBriefResponse,
    RequiredAsset,
)

_CLIENT_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_mcp() -> tuple[MagicMock, dict[str, Any]]:
    """Return (mock_mcp, captured) where captured maps name -> async fn."""
    captured: dict[str, Any] = {}
    mock = MagicMock()

    def _tool(**kwargs: Any) -> Any:
        def decorator(fn: Any) -> Any:
            captured[fn.__name__] = fn
            return fn

        return decorator

    mock.tool = _tool
    return mock, captured


def _make_input(**kwargs: Any) -> CreativeBriefInput:
    defaults: dict[str, Any] = {
        "client_id": _CLIENT_ID,
        "raw_brief": "We want to increase brand awareness and drive sales among young adults.",
        "product_description": "A premium fitness app that helps users track workouts and nutrition.",
        "target_audience": "Young adults aged 18-35",
        "platform": "meta",
        "constraints": BriefConstraints(),
    }
    defaults.update(kwargs)
    return CreativeBriefInput(**defaults)


def _make_response(**kwargs: Any) -> CreativeBriefResponse:
    defaults: dict[str, Any] = {
        "status": "ready",
        "client_id": _CLIENT_ID,
        "campaign_objective": "Increase brand awareness",
        "offer_and_promise": "A premium fitness app.",
        "target_persona": "Young adults aged 18-35",
        "pain_points": ["time constraints"],
        "objections": ["Too expensive", "Not relevant to me", "Already have a solution"],
        "creative_angles": [
            "How-to / educational angle",
            "Emotional storytelling angle",
            "Direct response angle",
        ],
        "required_assets": [
            RequiredAsset(asset_type="video", format="9:16", quantity=3, notes="Reels-format"),
            RequiredAsset(asset_type="image", format="1:1", quantity=5, notes="Feed posts"),
        ],
        "suggested_sprint_type": "dashboard_manual",
        "provider_suitability_notes": "Higgsfield for image-to-video; Freepik Mystic for text-to-video",
        "approval_checklist": [
            "âœ“ Campaign objective confirmed with client",
            "âœ“ Target audience validated",
            "âœ“ Compliance notes reviewed",
            "âœ“ Asset formats approved",
            "âœ“ Budget allocation set",
        ],
        "missing_information": ["No compliance constraints provided"],
        "summary": "Brief processed for META campaign. 2 asset type(s) required. Sprint type: dashboard_manual.",
        "next_action": "create_creative_sprint",
    }
    defaults.update(kwargs)
    return CreativeBriefResponse(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_meta_platform_returns_nine_sixteen_video_assets() -> None:
    """Meta platform response includes 9:16 video assets."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input(platform="meta")
    mock_resp = _make_response(
        required_assets=[
            RequiredAsset(asset_type="video", format="9:16", quantity=3, notes="Reels-format"),
            RequiredAsset(asset_type="image", format="1:1", quantity=5, notes="Feed posts"),
        ],
    )

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    formats = [a.format for a in result.required_assets]
    assert "9:16" in formats


@pytest.mark.asyncio
async def test_tiktok_platform_returns_five_videos() -> None:
    """TikTok platform response includes 5 video assets."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input(platform="tiktok")
    mock_resp = _make_response(
        required_assets=[
            RequiredAsset(asset_type="video", format="9:16", quantity=5, notes="Native TikTok format"),
        ],
        suggested_sprint_type="dashboard_manual",
    )

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    video_assets = [a for a in result.required_assets if a.asset_type == "video"]
    total_videos = sum(a.quantity for a in video_assets)
    assert total_videos == 5


@pytest.mark.asyncio
async def test_youtube_platform_returns_sixteen_nine_videos() -> None:
    """YouTube platform response includes 16:9 video assets."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input(platform="youtube")
    mock_resp = _make_response(
        required_assets=[
            RequiredAsset(asset_type="video", format="16:9", quantity=2, notes="Pre-roll or mid-roll"),
        ],
        suggested_sprint_type="api_credits",
    )

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    formats = [a.format for a in result.required_assets]
    assert "16:9" in formats


@pytest.mark.asyncio
async def test_suggested_sprint_type_dashboard_manual_for_meta() -> None:
    """Meta platform results in dashboard_manual sprint type."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input(platform="meta")
    mock_resp = _make_response(suggested_sprint_type="dashboard_manual")

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    assert result.suggested_sprint_type == "dashboard_manual"


@pytest.mark.asyncio
async def test_suggested_sprint_type_api_credits_for_youtube() -> None:
    """YouTube platform results in api_credits sprint type."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input(platform="youtube")
    mock_resp = _make_response(suggested_sprint_type="api_credits")

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    assert result.suggested_sprint_type == "api_credits"


@pytest.mark.asyncio
async def test_short_brief_adds_missing_information_entry() -> None:
    """A short raw_brief causes a missing_information warning in the response."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input(raw_brief="Short brief!")
    mock_resp = _make_response(
        missing_information=["Brief is very short â€” request more detail", "No compliance constraints provided"],
    )

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    assert any("short" in msg.lower() for msg in result.missing_information)


@pytest.mark.asyncio
async def test_approval_checklist_has_five_items() -> None:
    """The approval_checklist always contains exactly 5 items."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input()
    mock_resp = _make_response()

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    assert len(result.approval_checklist) == 5


@pytest.mark.asyncio
async def test_next_action_is_create_creative_sprint() -> None:
    """The next_action field is always 'create_creative_sprint'."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input()
    mock_resp = _make_response(next_action="create_creative_sprint")

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    assert result.next_action == "create_creative_sprint"


@pytest.mark.asyncio
async def test_response_has_all_required_fields() -> None:
    """The response is a CreativeBriefResponse with all expected fields populated."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input()
    mock_resp = _make_response()

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=AsyncMock(return_value=mock_resp),
    ):
        result = await captured["prepare_creative_brief"](data=data)

    assert isinstance(result, CreativeBriefResponse)
    assert result.status == "ready"
    assert result.client_id == _CLIENT_ID
    assert result.campaign_objective
    assert result.offer_and_promise
    assert result.target_persona
    assert isinstance(result.pain_points, list)
    assert isinstance(result.objections, list)
    assert isinstance(result.creative_angles, list)
    assert isinstance(result.required_assets, list)
    assert result.suggested_sprint_type
    assert result.provider_suitability_notes
    assert isinstance(result.approval_checklist, list)
    assert isinstance(result.missing_information, list)
    assert result.summary
    assert result.next_action


@pytest.mark.asyncio
async def test_tool_delegates_to_service_with_client_id() -> None:
    """The tool calls the service with the input client_id and input data."""
    from vos_studio_mcp.tools.prepare_creative_brief import register_prepare_creative_brief_tools

    mock_mcp, captured = _make_mock_mcp()
    register_prepare_creative_brief_tools(mock_mcp)  # type: ignore[arg-type]

    data = _make_input()
    mock_resp = _make_response()
    mock_svc = AsyncMock(return_value=mock_resp)

    with patch(
        "vos_studio_mcp.tools.prepare_creative_brief._prepare_creative_brief",
        new=mock_svc,
    ):
        result = await captured["prepare_creative_brief"](data=data)

    mock_svc.assert_awaited_once_with(_CLIENT_ID, data)
    assert result is mock_resp
