"""Asset quality review service — pure composition, no paid calls (Issue #57).

Validates QA criteria, records outcome, and returns a structured review
response for the asset. DB update is skipped because Asset does not have
a qa_status column yet (pure composition path).
"""

from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.schemas.asset_review import (
    AssetReviewCriteria,
    ReviewAssetInput,
    ReviewAssetResponse,
    ReviewOutcome,
)

# ---------------------------------------------------------------------------
# Criteria field names (ordered for consistent output)
# ---------------------------------------------------------------------------

_CRITERIA_FIELDS: list[str] = [
    "product_consistency",
    "label_accuracy",
    "campaign_coherence",
    "mobile_readability",
    "endcard_correct",
    "no_risky_claims",
]

# ---------------------------------------------------------------------------
# Checklist templates
# ---------------------------------------------------------------------------

_APPROVED_CHECKLIST: list[str] = [
    "✓ Product consistency verified",
    "✓ Campaign coherence confirmed",
    "✓ Mobile readability checked",
    "✓ No risky claims detected",
]

_NEXT_ACTIONS: dict[ReviewOutcome, str] = {
    "approved": "promote_to_library",
    "needs_repair": "register_manual_asset",
    "rejected": "create_creative_sprint",
}


# ---------------------------------------------------------------------------
# Public service function
# ---------------------------------------------------------------------------


async def review_asset(client_id: str, data: ReviewAssetInput) -> ReviewAssetResponse:
    """Validate asset QA criteria and return a structured review outcome.

    Verifies caller owns the sprint's client, evaluates all criteria fields,
    auto-corrects an "approved" outcome to "needs_repair" when any criterion
    fails, and returns checklist + next_action guidance.
    """
    assert_owns_client(client_id)

    criteria_passed, criteria_failed = _evaluate_criteria(data.criteria)

    outcome = _resolve_outcome(data.reviewer_outcome, criteria_failed, data.notes)

    approval_checklist = _build_approval_checklist(outcome, criteria_failed, data.notes)

    summary = (
        f"Asset {data.asset_id[:8]}... {outcome}. "
        f"{len(criteria_failed)} criteria failed."
    )

    return ReviewAssetResponse(
        status="reviewed",
        asset_id=data.asset_id,
        sprint_id=data.sprint_id,
        outcome=outcome,
        criteria_passed=criteria_passed,
        criteria_failed=criteria_failed,
        notes=data.notes,
        approval_checklist=approval_checklist,
        summary=summary,
        next_action=_NEXT_ACTIONS[outcome],
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _evaluate_criteria(criteria: AssetReviewCriteria) -> tuple[list[str], list[str]]:
    """Return (passed_fields, failed_fields) from the criteria object."""
    passed: list[str] = []
    failed: list[str] = []
    for field in _CRITERIA_FIELDS:
        if getattr(criteria, field):
            passed.append(field)
        else:
            failed.append(field)
    return passed, failed


def _resolve_outcome(
    reviewer_outcome: ReviewOutcome,
    criteria_failed: list[str],
    notes: str,
) -> ReviewOutcome:
    """Auto-correct to 'needs_repair' when criteria fail but outcome is 'approved'."""
    if reviewer_outcome == "approved" and criteria_failed:
        return "needs_repair"
    return reviewer_outcome


def _build_approval_checklist(
    outcome: ReviewOutcome,
    criteria_failed: list[str],
    notes: str,
) -> list[str]:
    """Build outcome-specific checklist items."""
    if outcome == "approved":
        return list(_APPROVED_CHECKLIST)
    if outcome == "needs_repair":
        return [f"Fix required: {field.replace('_', ' ')}" for field in criteria_failed]
    # rejected
    items: list[str] = ["✗ Asset rejected — do not promote"]
    if notes:
        items.append(f"Review notes: {notes}")
    return items
