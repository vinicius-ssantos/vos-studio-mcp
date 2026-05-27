"""Unit tests for creative_brief_service.prepare_creative_brief (Issue #48)."""

import pytest

from vos_studio_mcp.schemas.creative_brief import (
    BriefConstraints,
    CreativeBriefInput,
    CreativeBriefResponse,
    RequiredAsset,
)
from vos_studio_mcp.services.creative_brief_service import prepare_creative_brief

_CLIENT_ID = "00000000-0000-0000-0000-000000000001"


def _make_input(**kwargs: object) -> CreativeBriefInput:
    defaults: dict[str, object] = {
        "client_id": _CLIENT_ID,
        "raw_brief": "We want to increase brand awareness and drive sales among young adults.",
        "product_description": "A premium fitness app that helps users track workouts and nutrition.",
        "target_audience": "Young adults aged 18-35",
        "platform": "meta",
        "constraints": BriefConstraints(),
    }
    defaults.update(kwargs)
    return CreativeBriefInput(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_returns_creative_brief_response_for_valid_input() -> None:
    data = _make_input()
    result = await prepare_creative_brief(_CLIENT_ID, data)
    assert isinstance(result, CreativeBriefResponse)
    assert result.status == "ready"
    assert result.client_id == _CLIENT_ID


@pytest.mark.asyncio
async def test_pain_points_is_list_with_at_least_one_item() -> None:
    data = _make_input()
    result = await prepare_creative_brief(_CLIENT_ID, data)
    assert isinstance(result.pain_points, list)
    assert len(result.pain_points) >= 1


@pytest.mark.asyncio
async def test_objections_is_list_with_at_least_one_item() -> None:
    data = _make_input()
    result = await prepare_creative_brief(_CLIENT_ID, data)
    assert isinstance(result.objections, list)
    assert len(result.objections) >= 1


@pytest.mark.asyncio
async def test_creative_angles_is_list_with_at_least_one_item() -> None:
    data = _make_input()
    result = await prepare_creative_brief(_CLIENT_ID, data)
    assert isinstance(result.creative_angles, list)
    assert len(result.creative_angles) >= 1


@pytest.mark.asyncio
async def test_required_assets_are_required_asset_instances() -> None:
    data = _make_input()
    result = await prepare_creative_brief(_CLIENT_ID, data)
    assert len(result.required_assets) >= 1
    for asset in result.required_assets:
        assert isinstance(asset, RequiredAsset)


@pytest.mark.asyncio
async def test_short_brief_missing_information_includes_warning() -> None:
    data = _make_input(raw_brief="Short brief!")
    result = await prepare_creative_brief(_CLIENT_ID, data)
    assert any("short" in msg.lower() for msg in result.missing_information)


@pytest.mark.asyncio
async def test_meta_platform_has_nine_sixteen_assets() -> None:
    data = _make_input(
        platform="meta",
        raw_brief="We want to increase brand awareness on Instagram with meta ads. "
                  "Our target is young adults who love fitness.",
    )
    result = await prepare_creative_brief(_CLIENT_ID, data)
    formats = [a.format for a in result.required_assets]
    assert "9:16" in formats


@pytest.mark.asyncio
async def test_provider_suitability_notes_is_non_empty() -> None:
    data = _make_input()
    result = await prepare_creative_brief(_CLIENT_ID, data)
    assert result.provider_suitability_notes
    assert len(result.provider_suitability_notes) > 0
