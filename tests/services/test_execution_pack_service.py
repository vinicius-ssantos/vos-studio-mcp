"""Service tests for prepare_execution_pack (Issue #55)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.execution_pack import PrepareExecutionPackInput
from vos_studio_mcp.services.execution_pack_service import (
    _STAGE_NEXT_ACTIONS,
    _STAGE_QA_CRITERIA,
    _build_negative_constraints,
    prepare_execution_pack,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_SPRINT_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
_CLIENT_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
_BRAND_KIT_ID = "cccccccc-0000-0000-0000-cccccccccccc"


def _make_sprint(status: str = "open") -> MagicMock:
    sprint = MagicMock()
    sprint.sprint_status = status
    sprint.client_id = _CLIENT_ID
    sprint.brand_kit_id = _BRAND_KIT_ID
    sprint.product_name = "SuperApp"
    sprint.target_audience = "Gen-Z"
    sprint.campaign_objective = "Drive installs"
    return sprint


def _make_brand_kit() -> MagicMock:
    kit = MagicMock()
    kit.identity = {"tone": ["authentic", "bold"]}
    kit.visual = {"primary_colors": ["#FF0000", "#000000"], "secondary_colors": ["#FFFFFF"]}
    kit.restrictions = {"forbidden_elements": ["alcohol", "violence"]}
    return kit


_PATCH_SESSION = "vos_studio_mcp.services.execution_pack_service.get_session"
_PATCH_AUTH = "vos_studio_mcp.services.execution_pack_service.assert_owns_client"
_PATCH_TENANT = "vos_studio_mcp.services.execution_pack_service.set_tenant_context"


def _patch_session(sprint: MagicMock, brand_kit: MagicMock | None = None) -> MagicMock:
    """Create a mock get_session() context manager returning sprint + brand_kit."""
    session = AsyncMock()

    async def _get(model_class, pk):  # type: ignore[override]
        if "Sprint" in str(model_class):
            return sprint
        if "BrandKit" in str(model_class):
            return brand_kit
        return None

    session.get = _get
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# Blocked sprint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_when_sprint_not_open() -> None:
    sprint = _make_sprint("closed")
    data = PrepareExecutionPackInput(sprint_id=_SPRINT_ID, asset_stage="stage_0")

    with (
        patch(_PATCH_SESSION, return_value=_patch_session(sprint, _make_brand_kit())),
        patch(_PATCH_AUTH),
        patch(_PATCH_TENANT),
    ):
        result = await prepare_execution_pack(data)

    assert result.status == "blocked"
    assert result.next_action == "sprint_is_closed"
    assert result.operator_steps == []


# ---------------------------------------------------------------------------
# Ready packs for all stages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stage",
    ["stage_0", "stage_a", "stage_b", "stage_c", "repair", "final"],
)
@pytest.mark.asyncio
async def test_ready_pack_for_all_stages(stage: str) -> None:
    sprint = _make_sprint()
    brand_kit = _make_brand_kit()
    data = PrepareExecutionPackInput(sprint_id=_SPRINT_ID, asset_stage=stage)  # type: ignore[arg-type]

    with (
        patch(_PATCH_SESSION, return_value=_patch_session(sprint, brand_kit)),
        patch(_PATCH_AUTH),
        patch(_PATCH_TENANT),
    ):
        result = await prepare_execution_pack(data)

    assert result.status == "ready"
    assert result.asset_stage == stage
    assert result.asset_stage_label  # non-empty
    assert len(result.operator_steps) >= 3
    assert len(result.qa_criteria) >= 3
    assert result.objective
    assert "SuperApp" in result.objective
    assert result.summary


# ---------------------------------------------------------------------------
# Stage-specific QA criteria
# ---------------------------------------------------------------------------


def test_qa_criteria_cover_all_stages() -> None:
    for stage in ("stage_0", "stage_a", "stage_b", "stage_c", "repair", "final"):
        assert stage in _STAGE_QA_CRITERIA
        assert len(_STAGE_QA_CRITERIA[stage]) >= 3


def test_stage_c_has_motion_qa() -> None:
    criteria = _STAGE_QA_CRITERIA["stage_c"]
    combined = " ".join(criteria).lower()
    assert "motion" in combined or "duration" in combined


def test_final_stage_has_endcard_qa() -> None:
    criteria = _STAGE_QA_CRITERIA["final"]
    combined = " ".join(criteria).lower()
    assert "endcard" in combined


# ---------------------------------------------------------------------------
# Next-action routing
# ---------------------------------------------------------------------------


def test_repair_next_action_is_review() -> None:
    assert _STAGE_NEXT_ACTIONS["repair"] == "review_asset_quality"


def test_other_stages_next_action_is_register() -> None:
    for stage in ("stage_0", "stage_a", "stage_b", "stage_c", "final"):
        assert _STAGE_NEXT_ACTIONS[stage] == "register_manual_asset"


# ---------------------------------------------------------------------------
# Negative constraints
# ---------------------------------------------------------------------------


def test_negative_constraints_include_brand_restrictions() -> None:
    restrictions = {"forbidden_elements": ["alcohol", "violence"]}
    constraints = _build_negative_constraints(restrictions)
    assert "alcohol" in constraints
    assert "violence" in constraints


def test_negative_constraints_base_always_present() -> None:
    constraints = _build_negative_constraints({})
    combined = " ".join(constraints).lower()
    assert "watermark" in combined or "competitor" in combined


# ---------------------------------------------------------------------------
# Output spec includes prompt/preset version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_output_spec_includes_versions() -> None:
    sprint = _make_sprint()
    data = PrepareExecutionPackInput(
        sprint_id=_SPRINT_ID,
        asset_stage="stage_0",
        prompt_version="v3",
        preset_version="p2",
    )

    with (
        patch(_PATCH_SESSION, return_value=_patch_session(sprint, _make_brand_kit())),
        patch(_PATCH_AUTH),
        patch(_PATCH_TENANT),
    ):
        result = await prepare_execution_pack(data)

    assert result.output_spec.get("prompt_version") == "v3"
    assert result.output_spec.get("preset_version") == "p2"


# ---------------------------------------------------------------------------
# Without brand kit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ready_without_brand_kit() -> None:
    sprint = _make_sprint()
    data = PrepareExecutionPackInput(sprint_id=_SPRINT_ID, asset_stage="stage_c")

    with (
        patch(_PATCH_SESSION, return_value=_patch_session(sprint, None)),
        patch(_PATCH_AUTH),
        patch(_PATCH_TENANT),
    ):
        result = await prepare_execution_pack(data)

    assert result.status == "ready"
    assert len(result.operator_steps) >= 4
