"""Unit tests for blueprint_service.prepare_video_blueprint (issue #13)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.blueprint import VideoBlueprintInput, VideoBlueprintResponse
from vos_studio_mcp.services.blueprint_service import (
    _build_cost_notes,
    _build_creative_intent,
    _build_negative_prompts,
    _build_risk_notes,
    _build_shot_plan,
    prepare_video_blueprint,
)

_MODULE = "vos_studio_mcp.services.blueprint_service"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sprint(**kwargs: object) -> MagicMock:
    sprint = MagicMock()
    sprint.id = "sprint-uuid"
    sprint.client_id = "client-uuid"
    sprint.brand_kit_id = "bk-uuid"
    sprint.product_name = kwargs.get("product_name", "Turbo Sneaker")
    sprint.campaign_objective = kwargs.get("campaign_objective", "Drive Gen-Z trial")
    sprint.target_audience = kwargs.get("target_audience", "Gen-Z urban runners")
    sprint.brief = kwargs.get("brief", "Fast dynamic video showcasing the shoe in motion")
    sprint.sprint_status = kwargs.get("sprint_status", "open")
    sprint.max_spend_usd = kwargs.get("max_spend_usd", 500.0)
    sprint.spent_usd = kwargs.get("spent_usd", 50.0)
    sprint.alert_threshold_pct = kwargs.get("alert_threshold_pct", 0.8)
    return sprint


def _make_brand_kit(**kwargs: object) -> MagicMock:
    bk = MagicMock()
    bk.identity = kwargs.get("identity", {"tone": "bold and energetic"})
    bk.visual = kwargs.get("visual", {"color_palette": "electric blue and white"})
    bk.restrictions = kwargs.get("restrictions", {"forbidden_themes": ["violence", "alcohol"]})
    return bk


def _make_session_ctx(sprint: MagicMock, brand_kit: MagicMock | None = None) -> MagicMock:
    session = AsyncMock()

    async def _get(model: type, pk: object) -> MagicMock | None:
        from db.models import BrandKit, Sprint
        if model is Sprint:
            return sprint
        if model is BrandKit:
            return brand_kit
        return None

    session.get = AsyncMock(side_effect=_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# prepare_video_blueprint — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blueprint_ready_returns_response() -> None:
    sprint = _make_sprint()
    bk = _make_brand_kit()

    with (
        patch(f"{_MODULE}.get_session", return_value=_make_session_ctx(sprint, bk)),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await prepare_video_blueprint(
            VideoBlueprintInput(sprint_id="00000000-0000-0000-0000-000000000001", shot_count=3, provider_targets=["higgsfield", "manual"])
        )

    assert isinstance(result, VideoBlueprintResponse)
    assert result.status == "ready"
    assert len(result.shot_plan) == 3
    assert len(result.provider_packs) == 2
    assert result.next_action == "prepare_dashboard_pack"


@pytest.mark.asyncio
async def test_blueprint_includes_negative_prompts_from_brand_kit() -> None:
    sprint = _make_sprint()
    bk = _make_brand_kit(restrictions={"forbidden_themes": ["violence", "gambling"]})

    with (
        patch(f"{_MODULE}.get_session", return_value=_make_session_ctx(sprint, bk)),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await prepare_video_blueprint(
            VideoBlueprintInput(sprint_id="00000000-0000-0000-0000-000000000001", provider_targets=["higgsfield"])
        )

    assert "violence" in result.negative_prompts
    assert "gambling" in result.negative_prompts


@pytest.mark.asyncio
async def test_blueprint_provider_packs_contain_all_targets() -> None:
    sprint = _make_sprint()
    bk = _make_brand_kit()

    with (
        patch(f"{_MODULE}.get_session", return_value=_make_session_ctx(sprint, bk)),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await prepare_video_blueprint(
            VideoBlueprintInput(sprint_id="00000000-0000-0000-0000-000000000001", provider_targets=["higgsfield", "freepik", "magnific"])
        )

    providers = {p.provider for p in result.provider_packs}
    assert providers == {"higgsfield", "freepik", "magnific"}


@pytest.mark.asyncio
async def test_blueprint_approval_required_when_budget_alert() -> None:
    sprint = _make_sprint(spent_usd=410.0, max_spend_usd=500.0, alert_threshold_pct=0.8)
    bk = _make_brand_kit()

    with (
        patch(f"{_MODULE}.get_session", return_value=_make_session_ctx(sprint, bk)),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await prepare_video_blueprint(
            VideoBlueprintInput(sprint_id="00000000-0000-0000-0000-000000000001", provider_targets=["manual"])
        )

    assert result.approval_required is True
    assert result.next_action == "review_budget_before_generating"


@pytest.mark.asyncio
async def test_blueprint_works_without_brand_kit() -> None:
    sprint = _make_sprint()

    with (
        patch(f"{_MODULE}.get_session", return_value=_make_session_ctx(sprint, None)),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await prepare_video_blueprint(
            VideoBlueprintInput(sprint_id="00000000-0000-0000-0000-000000000001", provider_targets=["manual"])
        )

    assert result.status == "ready"
    assert "No brand kit found" in result.risk_notes


# ---------------------------------------------------------------------------
# prepare_video_blueprint — blocked path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blueprint_blocked_when_sprint_closed() -> None:
    sprint = _make_sprint(sprint_status="closed")

    with (
        patch(f"{_MODULE}.get_session", return_value=_make_session_ctx(sprint)),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await prepare_video_blueprint(
            VideoBlueprintInput(sprint_id="00000000-0000-0000-0000-000000000001", provider_targets=["higgsfield"])
        )

    assert result.status == "blocked"
    assert result.next_action == "sprint_is_closed"
    assert result.shot_plan == []
    assert result.provider_packs == []


@pytest.mark.asyncio
async def test_blueprint_raises_vos_error_when_sprint_not_found() -> None:
    from vos_studio_mcp.errors import VosError

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        pytest.raises(VosError),
    ):
        await prepare_video_blueprint(
            VideoBlueprintInput(sprint_id="00000000-0000-0000-0000-000000000000")
        )


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def test_build_creative_intent_uses_tone_from_identity() -> None:
    sprint = _make_sprint(product_name="AquaGel", campaign_objective="Hydration awareness")
    identity = {"tone": "calming and scientific"}
    result = _build_creative_intent(sprint, identity)
    assert "calming and scientific" in result
    assert "AquaGel" in result


def test_build_shot_plan_length() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=5, visual={"color_palette": "earth tones"})
    assert len(shots) == 5
    assert shots[0].shot_number == 1
    assert shots[4].shot_number == 5


def test_build_shot_plan_duration_default() -> None:
    sprint = _make_sprint()
    shots = _build_shot_plan(sprint, shot_count=2, visual={})
    for shot in shots:
        assert shot.duration_seconds == 5


def test_build_negative_prompts_includes_base_list() -> None:
    negs = _build_negative_prompts({})
    assert "blurry or out-of-focus frames" in negs
    assert "watermarks or overlaid text" in negs


def test_build_negative_prompts_appends_forbidden_list() -> None:
    negs = _build_negative_prompts({"forbidden_themes": ["nudity", "politics"]})
    assert "nudity" in negs
    assert "politics" in negs


def test_build_negative_prompts_handles_string_forbidden() -> None:
    negs = _build_negative_prompts({"forbidden": "excessive darkness"})
    assert "excessive darkness" in negs


def test_build_cost_notes_shows_remaining_budget() -> None:
    sprint = _make_sprint(max_spend_usd=200.0, spent_usd=80.0)
    notes = _build_cost_notes(sprint)
    assert "$200.00" in notes
    assert "$80.00" in notes
    assert "$120.00" in notes


def test_build_risk_notes_budget_alert() -> None:
    sprint = _make_sprint(spent_usd=420.0, max_spend_usd=500.0, alert_threshold_pct=0.8)
    notes = _build_risk_notes(sprint, brand_kit=MagicMock())
    assert "Budget alert" in notes


def test_build_risk_notes_no_brand_kit() -> None:
    sprint = _make_sprint(spent_usd=0.0)
    notes = _build_risk_notes(sprint, brand_kit=None)
    assert "No brand kit found" in notes


def test_build_risk_notes_clean() -> None:
    sprint = _make_sprint(spent_usd=10.0, max_spend_usd=500.0)
    notes = _build_risk_notes(sprint, brand_kit=MagicMock())
    assert "No blocking risks" in notes
