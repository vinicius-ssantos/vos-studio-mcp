"""Tests verifying BrandKit field mapping in blueprint_service (Issue #52)."""

from unittest.mock import MagicMock

from vos_studio_mcp.services.blueprint_service import (
    _build_negative_prompts,
    _build_shot_plan,
)


def _make_sprint(**kwargs: object) -> MagicMock:
    sprint = MagicMock()
    sprint.product_name = kwargs.get("product_name", "Alpha Shoe")
    sprint.campaign_objective = kwargs.get("campaign_objective", "Drive trial")
    sprint.target_audience = kwargs.get("target_audience", "Gen-Z runners")
    sprint.brief = kwargs.get("brief", "Dynamic video showcasing the shoe")
    return sprint


# ---------------------------------------------------------------------------
# _build_shot_plan — color field mapping
# ---------------------------------------------------------------------------


def test_shot_plan_uses_primary_colors_from_visual() -> None:
    """primary_colors from BrandVisualSystem must appear in motion_prompt."""
    sprint = _make_sprint()
    visual = {"primary_colors": ["electric blue", "white"], "secondary_colors": []}
    shots = _build_shot_plan(sprint, shot_count=1, visual=visual)

    assert len(shots) == 1
    assert "electric blue" in shots[0].motion_prompt
    assert "white" in shots[0].motion_prompt


def test_shot_plan_uses_secondary_colors_when_primary_absent() -> None:
    """secondary_colors must be used when primary_colors is empty."""
    sprint = _make_sprint()
    visual = {"primary_colors": [], "secondary_colors": ["gold", "charcoal"]}
    shots = _build_shot_plan(sprint, shot_count=1, visual=visual)

    assert "gold" in shots[0].motion_prompt


def test_shot_plan_combines_primary_and_secondary_up_to_three() -> None:
    """Color palette combines primary + secondary colors, capped at three."""
    sprint = _make_sprint()
    visual = {
        "primary_colors": ["red", "green"],
        "secondary_colors": ["blue", "yellow"],
    }
    shots = _build_shot_plan(sprint, shot_count=1, visual=visual)

    prompt = shots[0].motion_prompt
    # Up to 3 colors used: red, green, blue (yellow is 4th, excluded)
    assert "red" in prompt
    assert "green" in prompt
    assert "blue" in prompt
    assert "yellow" not in prompt


def test_shot_plan_falls_back_to_brand_palette_when_no_colors() -> None:
    """'brand palette' fallback used when visual has no color fields."""
    sprint = _make_sprint()
    visual: dict[str, object] = {}
    shots = _build_shot_plan(sprint, shot_count=1, visual=visual)

    assert "brand palette" in shots[0].motion_prompt


def test_shot_plan_falls_back_when_colors_are_empty_lists() -> None:
    """'brand palette' fallback used when primary_colors and secondary_colors are empty."""
    sprint = _make_sprint()
    visual: dict[str, object] = {"primary_colors": [], "secondary_colors": []}
    shots = _build_shot_plan(sprint, shot_count=1, visual=visual)

    assert "brand palette" in shots[0].motion_prompt


def test_shot_plan_color_appears_in_keyframe_guidance() -> None:
    """Colors must also appear in keyframe_guidance, not just motion_prompt."""
    sprint = _make_sprint()
    visual = {"primary_colors": ["coral red"], "secondary_colors": []}
    shots = _build_shot_plan(sprint, shot_count=1, visual=visual)

    assert "coral red" in shots[0].keyframe_guidance


# ---------------------------------------------------------------------------
# _build_negative_prompts — restriction field mapping
# ---------------------------------------------------------------------------


def test_negative_prompts_uses_forbidden_elements_not_forbidden_themes() -> None:
    """forbidden_elements is the correct BrandRestrictions field name."""
    negs = _build_negative_prompts({"forbidden_elements": ["violence", "alcohol"]})
    assert "violence" in negs
    assert "alcohol" in negs


def test_negative_prompts_forbidden_themes_are_ignored() -> None:
    """forbidden_themes does NOT exist in BrandRestrictions — items must not appear."""
    negs = _build_negative_prompts({"forbidden_themes": ["violence", "alcohol"]})
    assert "violence" not in negs
    assert "alcohol" not in negs


def test_negative_prompts_uses_forbidden_phrases() -> None:
    """forbidden_phrases is a valid BrandRestrictions field and must be included."""
    negs = _build_negative_prompts({"forbidden_phrases": ["buy now", "limited time"]})
    assert "buy now" in negs
    assert "limited time" in negs


def test_negative_prompts_both_forbidden_fields_combined() -> None:
    """Both forbidden_elements and forbidden_phrases are combined into negative prompts."""
    negs = _build_negative_prompts({
        "forbidden_elements": ["nudity"],
        "forbidden_phrases": ["discount"],
    })
    assert "nudity" in negs
    assert "discount" in negs


def test_negative_prompts_base_list_always_present() -> None:
    """Base negative prompts are always included regardless of restrictions."""
    negs = _build_negative_prompts({})
    assert "blurry or out-of-focus frames" in negs
    assert "watermarks or overlaid text" in negs
    assert "competitor branding" in negs
