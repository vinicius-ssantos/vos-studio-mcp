"""Tests for VOS 9-shot blueprint structure (Issue #54)."""

from unittest.mock import MagicMock

from vos_studio_mcp.schemas.blueprint import VideoBlueprintInput
from vos_studio_mcp.services.blueprint_service import (
    VOS_DEFAULT_SHOT_COUNT,
    _build_shot_plan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sprint(**kwargs: object) -> MagicMock:
    sprint = MagicMock()
    sprint.product_name = kwargs.get("product_name", "Turbo Sneaker")
    sprint.campaign_objective = kwargs.get("campaign_objective", "Drive Gen-Z trial")
    sprint.target_audience = kwargs.get("target_audience", "Gen-Z urban runners")
    sprint.brief = kwargs.get("brief", "Fast dynamic video showcasing the shoe in motion")
    return sprint


# ---------------------------------------------------------------------------
# VOS_DEFAULT_SHOT_COUNT constant
# ---------------------------------------------------------------------------


def test_vos_default_shot_count_is_9() -> None:
    assert VOS_DEFAULT_SHOT_COUNT == 9


# ---------------------------------------------------------------------------
# Default shot_count produces 9 shots
# ---------------------------------------------------------------------------


def test_schema_default_shot_count_is_9() -> None:
    data = VideoBlueprintInput(sprint_id="sprint-1")
    assert data.shot_count == VOS_DEFAULT_SHOT_COUNT


def test_build_shot_plan_default_produces_9_shots() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    assert len(shots) == 9


# ---------------------------------------------------------------------------
# VOS 9-shot block structure
# ---------------------------------------------------------------------------


def test_vos_9shot_has_3_distinct_pacing_values() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    pacings = {s.pacing for s in shots}
    assert len(pacings) == 3


def test_vos_9shot_block1_shots_are_establish() -> None:
    """Shots 1-3 belong to the Establish block (slow-burn pacing)."""
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    block1 = shots[:3]
    for shot in block1:
        assert shot.pacing == "slow-burn"


def test_vos_9shot_block2_shots_are_engage() -> None:
    """Shots 4-6 belong to the Engage block (mid-pace pacing)."""
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    block2 = shots[3:6]
    for shot in block2:
        assert shot.pacing == "mid-pace"


def test_vos_9shot_block3_shots_are_convert() -> None:
    """Shots 7-9 belong to the Convert block (energetic pacing)."""
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    block3 = shots[6:9]
    for shot in block3:
        assert shot.pacing == "energetic"


# ---------------------------------------------------------------------------
# Each shot has non-empty required fields
# ---------------------------------------------------------------------------


def test_vos_9shot_all_shots_have_non_empty_scene_description() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    for shot in shots:
        assert shot.scene_description, f"Shot {shot.shot_number} has empty scene_description"


def test_vos_9shot_all_shots_have_non_empty_motion_prompt() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    for shot in shots:
        assert shot.motion_prompt, f"Shot {shot.shot_number} has empty motion_prompt"


def test_vos_9shot_all_shots_have_non_empty_keyframe_guidance() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    for shot in shots:
        assert shot.keyframe_guidance, f"Shot {shot.shot_number} has empty keyframe_guidance"


def test_vos_9shot_duration_is_4s_per_shot() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    for shot in shots:
        assert shot.duration_seconds == 4


def test_vos_9shot_shot_numbers_are_sequential() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    for i, shot in enumerate(shots, start=1):
        assert shot.shot_number == i


# ---------------------------------------------------------------------------
# Non-9 shot_count uses generic logic (fallback)
# ---------------------------------------------------------------------------


def test_shot_count_3_override_uses_generic_logic() -> None:
    """When shot_count != 9, the generic shot plan is used."""
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=3, visual={})
    assert len(shots) == 3


def test_shot_count_3_override_has_duration_5s() -> None:
    """Generic shots default to 5s duration, not 4s."""
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=3, visual={})
    for shot in shots:
        assert shot.duration_seconds == 5


def test_shot_count_5_override_produces_5_shots() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=5, visual={})
    assert len(shots) == 5


# ---------------------------------------------------------------------------
# Product/audience context is embedded in shot content
# ---------------------------------------------------------------------------


def test_vos_9shot_scene_description_contains_product() -> None:
    sprint = _make_sprint(product_name="AlphaWatch")
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    products_found = sum(1 for s in shots if "AlphaWatch" in s.scene_description)
    assert products_found > 0


def test_vos_9shot_motion_prompt_contains_product() -> None:
    sprint = _make_sprint(product_name="NanoBar")
    shots = _build_shot_plan(sprint, shot_count=9, visual={})
    for shot in shots:
        assert "NanoBar" in shot.motion_prompt


def test_vos_9shot_color_palette_from_visual_is_used() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(
        sprint,
        shot_count=9,
        visual={"primary_colors": ["electric-blue", "white"]},
    )
    # At least some shots should reference the palette
    palette_found = sum(1 for s in shots if "electric-blue" in s.motion_prompt)
    assert palette_found > 0
