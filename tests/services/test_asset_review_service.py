"""Unit tests for asset_review_service (Issue #57)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.asset_review import AssetReviewCriteria, ReviewAssetInput
from vos_studio_mcp.services.asset_review_service import review_asset

_GET_SESSION = "vos_studio_mcp.services.asset_review_service.get_session"
_SET_TENANT = "vos_studio_mcp.services.asset_review_service.set_tenant_context_from_sprint"
_GUARD = "vos_studio_mcp.services.asset_review_service.assert_owns_client"

_ASSET_ID = "aaaaaaaabbbbccccdddd1234567890ab"
_SPRINT_ID = "00000000-0000-0000-0000-000000000001"
_CLIENT_ID = "00000000-0000-0000-0000-000000000002"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(**kwargs: object) -> ReviewAssetInput:
    return ReviewAssetInput(
        asset_id=str(kwargs.get("asset_id", _ASSET_ID)),
        sprint_id=str(kwargs.get("sprint_id", _SPRINT_ID)),
        criteria=kwargs.get("criteria", AssetReviewCriteria()),  # type: ignore[arg-type]
        notes=str(kwargs.get("notes", "")),
        reviewer_outcome=kwargs.get("reviewer_outcome", "approved"),  # type: ignore[arg-type]
        performance_score=kwargs.get("performance_score"),  # type: ignore[arg-type]
    )


def _mock_asset(asset_id: str = _ASSET_ID) -> MagicMock:
    asset = MagicMock()
    asset.id = uuid.UUID(asset_id)
    asset.qa_status = None
    asset.performance_score = None
    return asset


def _session_ctx(asset: MagicMock) -> MagicMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=asset)
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _call(data: ReviewAssetInput, asset: MagicMock | None = None):  # type: ignore[return]
    """Run review_asset with all DB/auth mocks in place."""
    if asset is None:
        asset = _mock_asset(data.asset_id)
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        import asyncio

        return asyncio.get_event_loop().run_until_complete(review_asset(data))


# ---------------------------------------------------------------------------
# All criteria passed -> approved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_criteria_passed_returns_approved() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(
            product_consistency=True,
            label_accuracy=True,
            campaign_coherence=True,
            mobile_readability=True,
            endcard_correct=True,
            no_risky_claims=True,
        ),
        reviewer_outcome="approved",
    )
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.outcome == "approved"
    assert result.status == "reviewed"
    assert result.criteria_failed == []
    assert len(result.criteria_passed) == 6


# ---------------------------------------------------------------------------
# One criterion failed -> auto-corrects to needs_repair when reviewer says approved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_criteria_failed_auto_corrects_to_needs_repair() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(product_consistency=False),
        reviewer_outcome="approved",
    )
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.outcome == "needs_repair"


# ---------------------------------------------------------------------------
# Explicit rejected -> rejected regardless of criteria
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_rejected_ignores_criteria() -> None:
    data = _make_input(reviewer_outcome="rejected")
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.outcome == "rejected"
    assert result.next_action == "create_creative_sprint"


# ---------------------------------------------------------------------------
# criteria_failed and criteria_passed lists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_criteria_failed_list_contains_failed_field_names() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(
            product_consistency=False,
            label_accuracy=False,
        ),
        reviewer_outcome="needs_repair",
    )
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert "product_consistency" in result.criteria_failed
    assert "label_accuracy" in result.criteria_failed
    assert len(result.criteria_failed) == 2


@pytest.mark.asyncio
async def test_criteria_passed_list_contains_passed_field_names() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(
            endcard_correct=False,
            no_risky_claims=False,
        ),
        reviewer_outcome="needs_repair",
    )
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert "product_consistency" in result.criteria_passed
    assert "label_accuracy" in result.criteria_passed
    assert len(result.criteria_passed) == 4


# ---------------------------------------------------------------------------
# approval_checklist has items for each outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_checklist_has_expected_items() -> None:
    data = _make_input(reviewer_outcome="approved")
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    checklist_text = " ".join(result.approval_checklist)
    assert "Product consistency" in checklist_text
    assert "Mobile readability" in checklist_text
    assert len(result.approval_checklist) >= 4


@pytest.mark.asyncio
async def test_needs_repair_checklist_lists_failed_criteria() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(product_consistency=False),
        reviewer_outcome="approved",
    )
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.outcome == "needs_repair"
    assert len(result.approval_checklist) >= 1
    assert any("product" in item.lower() for item in result.approval_checklist)


@pytest.mark.asyncio
async def test_rejected_checklist_has_rejection_message() -> None:
    data = _make_input(reviewer_outcome="rejected", notes="Off-brand imagery")
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    checklist_text = " ".join(result.approval_checklist)
    assert "rejected" in checklist_text.lower()
    assert "Off-brand imagery" in checklist_text


# ---------------------------------------------------------------------------
# next_action per outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_next_action_is_promote_to_library() -> None:
    data = _make_input(reviewer_outcome="approved")
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.next_action == "promote_to_library"


@pytest.mark.asyncio
async def test_needs_repair_next_action_is_register_manual_asset() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(mobile_readability=False),
        reviewer_outcome="needs_repair",
    )
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.next_action == "register_manual_asset"


@pytest.mark.asyncio
async def test_rejected_next_action_is_create_creative_sprint() -> None:
    data = _make_input(reviewer_outcome="rejected")
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.next_action == "create_creative_sprint"


# ---------------------------------------------------------------------------
# Summary field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_contains_asset_id_prefix() -> None:
    asset_id = _ASSET_ID
    data = _make_input(asset_id=asset_id, reviewer_outcome="approved")
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset(asset_id))),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert asset_id[:8] in result.summary


@pytest.mark.asyncio
async def test_summary_contains_outcome() -> None:
    data = _make_input(reviewer_outcome="approved")
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset())),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert "approved" in result.summary


# ---------------------------------------------------------------------------
# qa_status is persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qa_status_is_written_to_asset() -> None:
    asset = _mock_asset()
    data = _make_input(reviewer_outcome="approved")
    session = AsyncMock()
    session.get = AsyncMock(return_value=asset)
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)

    assert asset.qa_status == result.outcome
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_performance_score_is_persisted_and_returned() -> None:
    asset = _mock_asset()
    data = _make_input(reviewer_outcome="approved", performance_score=0.85)
    session = AsyncMock()
    session.get = AsyncMock(return_value=asset)
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)

    assert asset.performance_score == 85
    assert result.performance_score == 0.85


@pytest.mark.asyncio
async def test_existing_performance_score_is_returned_when_not_overwritten() -> None:
    asset = _mock_asset()
    asset.performance_score = 72
    data = _make_input(reviewer_outcome="approved")

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)

    assert result.performance_score == 0.72


# ---------------------------------------------------------------------------
# Response fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_contains_correct_asset_and_sprint_ids() -> None:
    asset_id = "aabbccdd11223344556677889900aabb"
    sprint_id = "00000000-0000-0000-0000-000000000099"
    data = _make_input(asset_id=asset_id, sprint_id=sprint_id)
    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=_session_ctx(_mock_asset(asset_id))),
        patch(_SET_TENANT, new_callable=AsyncMock, return_value=_CLIENT_ID),
    ):
        result = await review_asset(data)
    assert result.asset_id == asset_id
    assert result.sprint_id == sprint_id
