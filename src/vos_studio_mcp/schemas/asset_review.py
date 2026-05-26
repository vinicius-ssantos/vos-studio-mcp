"""Asset quality review schemas (Issue #57)."""

from typing import Literal

from pydantic import BaseModel, Field

ReviewOutcome = Literal["approved", "needs_repair", "rejected"]


class AssetReviewCriteria(BaseModel):
    product_consistency: bool = True  # product looks correct
    label_accuracy: bool = True  # no label drift or wrong text
    campaign_coherence: bool = True  # matches campaign brief/objective
    mobile_readability: bool = True  # readable on mobile
    endcard_correct: bool = True  # endcard/CTA is correct
    no_risky_claims: bool = True  # no claims that violate constraints


class ReviewAssetInput(BaseModel):
    asset_id: str
    sprint_id: str
    criteria: AssetReviewCriteria = Field(default_factory=AssetReviewCriteria)
    notes: str = ""
    reviewer_outcome: ReviewOutcome = "approved"


class ReviewAssetResponse(BaseModel):
    status: str
    asset_id: str
    sprint_id: str
    outcome: ReviewOutcome
    criteria_passed: list[str]
    criteria_failed: list[str]
    notes: str
    approval_checklist: list[str]
    summary: str
    next_action: str
