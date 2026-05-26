"""Unit tests for asset_review_service (Issue #57)."""

import pytest

from vos_studio_mcp.schemas.asset_review import AssetReviewCriteria, ReviewAssetInput
from vos_studio_mcp.services.asset_review_service import review_asset

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(**kwargs: object) -> ReviewAssetInput:
    return ReviewAssetInput(
        asset_id=str(kwargs.get("asset_id", "aaaaaaaabbbbccccdddd1234567890ab")),
        sprint_id=str(kwargs.get("sprint_id", "00000000-0000-0000-0000-000000000001")),
        criteria=kwargs.get("criteria", AssetReviewCriteria()),  # type: ignore[arg-type]
        notes=str(kwargs.get("notes", "")),
        reviewer_outcome=kwargs.get("reviewer_outcome", "approved"),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# All criteria passed → approved
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
    result = await review_asset("client-1", data)
    assert result.outcome == "approved"
    assert result.status == "reviewed"
    assert result.criteria_failed == []
    assert len(result.criteria_passed) == 6


# ---------------------------------------------------------------------------
# One criterion failed → auto-corrects to needs_repair when reviewer says approved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_criteria_failed_auto_corrects_to_needs_repair() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(
            product_consistency=False,
            label_accuracy=True,
            campaign_coherence=True,
            mobile_readability=True,
            endcard_correct=True,
            no_risky_claims=True,
        ),
        reviewer_outcome="approved",
    )
    result = await review_asset("client-1", data)
    assert result.outcome == "needs_repair"


# ---------------------------------------------------------------------------
# Explicit rejected → rejected regardless of criteria
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_rejected_ignores_criteria() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(
            product_consistency=True,
            label_accuracy=True,
            campaign_coherence=True,
            mobile_readability=True,
            endcard_correct=True,
            no_risky_claims=True,
        ),
        reviewer_outcome="rejected",
    )
    result = await review_asset("client-1", data)
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
            campaign_coherence=True,
            mobile_readability=True,
            endcard_correct=True,
            no_risky_claims=True,
        ),
        reviewer_outcome="needs_repair",
    )
    result = await review_asset("client-1", data)
    assert "product_consistency" in result.criteria_failed
    assert "label_accuracy" in result.criteria_failed
    assert len(result.criteria_failed) == 2


@pytest.mark.asyncio
async def test_criteria_passed_list_contains_passed_field_names() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(
            product_consistency=True,
            label_accuracy=True,
            campaign_coherence=True,
            mobile_readability=True,
            endcard_correct=False,
            no_risky_claims=False,
        ),
        reviewer_outcome="needs_repair",
    )
    result = await review_asset("client-1", data)
    assert "product_consistency" in result.criteria_passed
    assert "label_accuracy" in result.criteria_passed
    assert "campaign_coherence" in result.criteria_passed
    assert "mobile_readability" in result.criteria_passed
    assert len(result.criteria_passed) == 4


# ---------------------------------------------------------------------------
# approval_checklist has items for each outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_checklist_has_expected_items() -> None:
    data = _make_input(reviewer_outcome="approved")
    result = await review_asset("client-1", data)
    checklist_text = " ".join(result.approval_checklist)
    assert "Product consistency" in checklist_text
    assert "Mobile readability" in checklist_text
    assert len(result.approval_checklist) >= 4


@pytest.mark.asyncio
async def test_needs_repair_checklist_lists_failed_criteria() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(
            product_consistency=False,
            label_accuracy=True,
            campaign_coherence=True,
            mobile_readability=True,
            endcard_correct=True,
            no_risky_claims=True,
        ),
        reviewer_outcome="approved",
    )
    result = await review_asset("client-1", data)
    assert result.outcome == "needs_repair"
    assert len(result.approval_checklist) >= 1
    assert any("product" in item.lower() for item in result.approval_checklist)


@pytest.mark.asyncio
async def test_rejected_checklist_has_rejection_message() -> None:
    data = _make_input(reviewer_outcome="rejected", notes="Off-brand imagery")
    result = await review_asset("client-1", data)
    checklist_text = " ".join(result.approval_checklist)
    assert "rejected" in checklist_text.lower()
    assert "Off-brand imagery" in checklist_text


# ---------------------------------------------------------------------------
# next_action per outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_next_action_is_promote_to_library() -> None:
    data = _make_input(reviewer_outcome="approved")
    result = await review_asset("client-1", data)
    assert result.next_action == "promote_to_library"


@pytest.mark.asyncio
async def test_needs_repair_next_action_is_register_manual_asset() -> None:
    data = _make_input(
        criteria=AssetReviewCriteria(mobile_readability=False),
        reviewer_outcome="needs_repair",
    )
    result = await review_asset("client-1", data)
    assert result.next_action == "register_manual_asset"


@pytest.mark.asyncio
async def test_rejected_next_action_is_create_creative_sprint() -> None:
    data = _make_input(reviewer_outcome="rejected")
    result = await review_asset("client-1", data)
    assert result.next_action == "create_creative_sprint"


# ---------------------------------------------------------------------------
# Summary field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_contains_asset_id_prefix() -> None:
    asset_id = "aaaaaaaabbbbccccdddd1234567890ab"
    data = _make_input(asset_id=asset_id, reviewer_outcome="approved")
    result = await review_asset("client-1", data)
    assert asset_id[:8] in result.summary


@pytest.mark.asyncio
async def test_summary_contains_outcome() -> None:
    data = _make_input(reviewer_outcome="approved")
    result = await review_asset("client-1", data)
    assert "approved" in result.summary


# ---------------------------------------------------------------------------
# Response fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_contains_correct_asset_and_sprint_ids() -> None:
    data = _make_input(
        asset_id="aabbccdd11223344556677889900aabb",
        sprint_id="00000000-0000-0000-0000-000000000099",
    )
    result = await review_asset("client-1", data)
    assert result.asset_id == "aabbccdd11223344556677889900aabb"
    assert result.sprint_id == "00000000-0000-0000-0000-000000000099"
