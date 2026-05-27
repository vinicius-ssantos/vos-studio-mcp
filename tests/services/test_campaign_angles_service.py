"""Unit tests for campaign_angles_service (Issue #49)."""

import pytest

from vos_studio_mcp.schemas.campaign_angles import CampaignAngle, CampaignAnglesInput
from vos_studio_mcp.services.campaign_angles_service import generate_campaign_angles

_CLIENT_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"


def _make_input(**kwargs) -> CampaignAnglesInput:  # type: ignore[return]
    defaults = dict(
        client_id=_CLIENT_ID,
        product_description="EcoBottle water bottle",
        target_audience="eco-conscious millennials",
        platform="meta",
        campaign_objective="brand_awareness",
    )
    defaults.update(kwargs)
    return CampaignAnglesInput(**defaults)


@pytest.mark.asyncio
async def test_returns_correct_number_of_angles() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=5))
    assert len(result.angles) == 5


@pytest.mark.asyncio
async def test_respects_n_angles_parameter() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=3))
    assert len(result.angles) == 3


@pytest.mark.asyncio
async def test_single_angle() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=1))
    assert len(result.angles) == 1


@pytest.mark.asyncio
async def test_max_angles() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=10))
    assert len(result.angles) == 10


@pytest.mark.asyncio
async def test_all_angle_fields_populated() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=3))
    for angle in result.angles:
        assert isinstance(angle, CampaignAngle)
        assert angle.angle_id  # non-empty
        assert angle.title
        assert angle.hook
        assert angle.angle_type
        assert angle.primary_message
        assert angle.cta
        assert angle.format_suggestion


@pytest.mark.asyncio
async def test_angle_id_format() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=3))
    assert result.angles[0].angle_id == "angle_01"
    assert result.angles[1].angle_id == "angle_02"
    assert result.angles[2].angle_id == "angle_03"


@pytest.mark.asyncio
async def test_diversity_score_between_0_and_1() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=6))
    assert 0.0 <= result.diversity_score <= 1.0


@pytest.mark.asyncio
async def test_full_diversity_for_6_unique_types() -> None:
    """6 angles should cover all 6 unique types → diversity=1.0."""
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=6))
    unique = {a.angle_type for a in result.angles}
    assert len(unique) == 6
    assert result.diversity_score == 1.0


@pytest.mark.asyncio
async def test_response_has_required_fields() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input())
    assert result.status == "ok"
    assert result.client_id == _CLIENT_ID
    assert result.product_description
    assert result.target_audience
    assert result.platform
    assert result.summary
    assert result.next_action == "prepare_creative_brief"


@pytest.mark.asyncio
async def test_meta_platform_format_suggestions() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(platform="meta", n_angles=6))
    formats = {a.format_suggestion for a in result.angles}
    assert "15s Reel" in formats or "30s Feed Video" in formats


@pytest.mark.asyncio
async def test_tiktok_platform_format_suggestion() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(platform="tiktok", n_angles=3))
    for angle in result.angles:
        assert angle.format_suggestion == "15-30s TikTok"


@pytest.mark.asyncio
async def test_youtube_platform_format_suggestion() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(platform="youtube", n_angles=3))
    for angle in result.angles:
        assert "Pre-roll" in angle.format_suggestion


@pytest.mark.asyncio
async def test_existing_angles_filtering() -> None:
    """When existing_angles contain all type keywords, service cycles back gracefully."""
    existing = ["emotional", "rational", "social_proof", "urgency", "curiosity", "authority"]
    result = await generate_campaign_angles(
        _CLIENT_ID, _make_input(n_angles=3, existing_angles=existing)
    )
    # Should still return 3 angles (cycles back to all types)
    assert len(result.angles) == 3


@pytest.mark.asyncio
async def test_summary_contains_platform_and_count() -> None:
    result = await generate_campaign_angles(_CLIENT_ID, _make_input(n_angles=4, platform="meta"))
    assert "META" in result.summary
    assert "4" in result.summary
