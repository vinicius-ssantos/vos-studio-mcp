"""Schema validation tests for video blueprint (issue #13)."""

import pytest
from pydantic import ValidationError

from vos_studio_mcp.schemas.blueprint import (
    ProviderExecutionPack,
    ShotPlan,
    VideoBlueprintInput,
    VideoBlueprintResponse,
)

# ---------------------------------------------------------------------------
# VideoBlueprintInput
# ---------------------------------------------------------------------------


def test_input_defaults() -> None:
    data = VideoBlueprintInput(sprint_id="sprint-1")
    assert data.prompt_version == "v1"
    assert data.preset_version == "p1"
    assert data.shot_count == 3
    assert set(data.provider_targets) == {"higgsfield", "freepik", "magnific", "manual"}


def test_input_custom_providers() -> None:
    data = VideoBlueprintInput(sprint_id="s", provider_targets=["higgsfield", "manual"])
    assert data.provider_targets == ["higgsfield", "manual"]


def test_input_shot_count_bounds() -> None:
    assert VideoBlueprintInput(sprint_id="s", shot_count=1).shot_count == 1
    assert VideoBlueprintInput(sprint_id="s", shot_count=10).shot_count == 10


def test_input_shot_count_below_min_raises() -> None:
    with pytest.raises(ValidationError):
        VideoBlueprintInput(sprint_id="s", shot_count=0)


def test_input_shot_count_above_max_raises() -> None:
    with pytest.raises(ValidationError):
        VideoBlueprintInput(sprint_id="s", shot_count=11)


def test_input_empty_provider_list_raises() -> None:
    with pytest.raises(ValidationError):
        VideoBlueprintInput(sprint_id="s", provider_targets=[])


def test_input_invalid_provider_raises() -> None:
    with pytest.raises(ValidationError):
        VideoBlueprintInput(sprint_id="s", provider_targets=["openai"])  # not a valid provider


# ---------------------------------------------------------------------------
# ShotPlan
# ---------------------------------------------------------------------------


def test_shot_plan_fields() -> None:
    shot = ShotPlan(
        shot_number=1,
        scene_description="Wide establishing",
        motion_prompt="slow push-in on product",
        keyframe_guidance="product centred, warm light",
        camera_movement="Slow push-in",
        pacing="slow-burn (4–6 s)",
        duration_seconds=5,
    )
    assert shot.shot_number == 1
    assert shot.duration_seconds == 5


# ---------------------------------------------------------------------------
# ProviderExecutionPack
# ---------------------------------------------------------------------------


def test_provider_pack_fields() -> None:
    pack = ProviderExecutionPack(
        provider="higgsfield",
        model_recommendation="Higgsfield Animate v1",
        adapted_prompt="cinematic reveal of product",
        settings={"aspect_ratio": "16:9", "duration_seconds": 5},
        checklist=["Upload image", "Paste prompt"],
    )
    assert pack.provider == "higgsfield"
    assert pack.settings["aspect_ratio"] == "16:9"


# ---------------------------------------------------------------------------
# VideoBlueprintResponse
# ---------------------------------------------------------------------------


def test_response_ready() -> None:
    resp = VideoBlueprintResponse(
        status="ready",
        sprint_id="s-1",
        creative_intent="Authentic video for Gen-Z",
        campaign_objective="Drive trial downloads",
        shot_plan=[],
        negative_prompts=["blurry frames"],
        provider_packs=[],
        manual_checklist=["Review shot plan"],
        cost_notes="$100 remaining",
        risk_notes="No blocking risks.",
        approval_required=False,
        summary="Blueprint ready.",
        next_action="prepare_dashboard_pack",
    )
    assert resp.status == "ready"
    assert resp.approval_required is False


def test_response_blocked() -> None:
    resp = VideoBlueprintResponse(
        status="blocked",
        sprint_id="s-2",
        creative_intent="",
        campaign_objective="obj",
        shot_plan=[],
        negative_prompts=[],
        provider_packs=[],
        manual_checklist=[],
        cost_notes="",
        risk_notes="",
        approval_required=False,
        summary="Sprint is closed.",
        next_action="sprint_is_closed",
    )
    assert resp.status == "blocked"
    assert resp.next_action == "sprint_is_closed"
