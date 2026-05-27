"""Asset quality review service — validates QA criteria and persists outcome (Issue #57)."""

import uuid

from db.models import Asset
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.asset_review import (
    AssetReviewCriteria,
    ReviewAssetInput,
    ReviewAssetResponse,
    ReviewOutcome,
)
from vos_studio_mcp.services.database import get_session, set_tenant_context_from_sprint

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
    """Validate asset QA criteria, persist qa_status, and return a structured review outcome.

    Verifies caller owns the sprint's client, evaluates all criteria fields,
    auto-corrects an "approved" outcome to "needs_repair" when any criterion
    fails, persists qa_status to the asset row, and returns checklist + next_action guidance.
    """
    assert_owns_client(client_id)

    criteria_passed, criteria_failed = _evaluate_criteria(data.criteria)
    outcome = _resolve_outcome(data.reviewer_outcome, criteria_failed, data.notes)
    approval_checklist = _build_approval_checklist(outcome, criteria_failed, data.notes)

    # Persist qa_status to the asset row under the sprint's RLS tenant context.
    async with get_session() as session:
        try:
            client_id_from_sprint = await set_tenant_context_from_sprint(
                session, data.sprint_id
            )
        except LookupError as exc:
            raise VosError(
                ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found"
            ) from exc
        assert_owns_client(client_id_from_sprint)

        asset = await session.get(Asset, uuid.UUID(data.asset_id))
        if asset is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Asset {data.asset_id} not found")

        asset.qa_status = outcome
        await session.commit()

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
