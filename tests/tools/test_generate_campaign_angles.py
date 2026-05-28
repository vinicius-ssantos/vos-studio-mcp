"""Tool-layer tests for generate_campaign_angles (Issue #49)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.campaign_angles import (
    CampaignAngle,
    CampaignAnglesInput,
    CampaignAnglesResponse,
)

_CLIENT_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"

_PATCH_SVC = "vos_studio_mcp.tools.generate_campaign_angles.generate_campaign_angles_svc"


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


def _make_angles(n: int = 3) -> list[CampaignAngle]:
    return [
        CampaignAngle(
            angle_id=f"angle_{i+1:02d}",
            title=f"Title {i+1}",
            hook=f"Hook {i+1}",
            angle_type="emotional",
            primary_message=f"Message {i+1}",
            cta="See how",
            format_suggestion="15s Reel",
        )
        for i in range(n)
    ]


def _make_response(n: int = 3) -> CampaignAnglesResponse:
    angles = _make_angles(n)
    return CampaignAnglesResponse(
        status="ok",
        client_id=_CLIENT_ID,
        product_description="EcoBottle",
        target_audience="Millennials",
        platform="meta",
        angles=angles,
        diversity_score=1.0,
        summary=f"Generated {n} angles.",
        next_action="prepare_creative_brief",
    )


def _make_input(**kwargs) -> CampaignAnglesInput:
    defaults = dict(
        client_id=_CLIENT_ID,
        product_description="EcoBottle water bottle",
        target_audience="eco-conscious millennials",
    )
    defaults.update(kwargs)
    return CampaignAnglesInput(**defaults)


@pytest.mark.asyncio
async def test_returns_response_when_authenticated() -> None:
    from vos_studio_mcp.tools.generate_campaign_angles import (
        register_generate_campaign_angles_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_generate_campaign_angles_tools(mock_mcp)

    mock_response = _make_response(5)
    with patch(
        "vos_studio_mcp.tools.generate_campaign_angles._generate_campaign_angles",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await captured["generate_campaign_angles"](data=_make_input())

    assert result.status == "ok"
    assert len(result.angles) == 5


@pytest.mark.asyncio
async def test_passes_client_id_from_input() -> None:
    from vos_studio_mcp.tools.generate_campaign_angles import (
        register_generate_campaign_angles_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_generate_campaign_angles_tools(mock_mcp)

    mock_response = _make_response()
    with patch(
        "vos_studio_mcp.tools.generate_campaign_angles._generate_campaign_angles",
        new=AsyncMock(return_value=mock_response),
    ) as mock_svc:
        await captured["generate_campaign_angles"](data=_make_input())

    call_args = mock_svc.call_args
    assert call_args.args[0] == _CLIENT_ID


@pytest.mark.asyncio
async def test_next_action_is_prepare_creative_brief() -> None:
    from vos_studio_mcp.tools.generate_campaign_angles import (
        register_generate_campaign_angles_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_generate_campaign_angles_tools(mock_mcp)

    mock_response = _make_response()
    with patch(
        "vos_studio_mcp.tools.generate_campaign_angles._generate_campaign_angles",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await captured["generate_campaign_angles"](data=_make_input())

    assert result.next_action == "prepare_creative_brief"


@pytest.mark.asyncio
async def test_angles_have_required_fields() -> None:
    from vos_studio_mcp.tools.generate_campaign_angles import (
        register_generate_campaign_angles_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_generate_campaign_angles_tools(mock_mcp)

    mock_response = _make_response(3)
    with patch(
        "vos_studio_mcp.tools.generate_campaign_angles._generate_campaign_angles",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await captured["generate_campaign_angles"](data=_make_input())

    for angle in result.angles:
        assert angle.angle_id
        assert angle.title
        assert angle.hook
        assert angle.angle_type
        assert angle.primary_message
        assert angle.cta
        assert angle.format_suggestion


@pytest.mark.asyncio
async def test_diversity_score_in_result() -> None:
    from vos_studio_mcp.tools.generate_campaign_angles import (
        register_generate_campaign_angles_tools,
    )

    mock_mcp, captured = _make_mock_mcp()
    register_generate_campaign_angles_tools(mock_mcp)

    mock_response = _make_response()
    with patch(
        "vos_studio_mcp.tools.generate_campaign_angles._generate_campaign_angles",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await captured["generate_campaign_angles"](data=_make_input())

    assert 0.0 <= result.diversity_score <= 1.0
