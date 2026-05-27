"""Creative sprint schemas."""

from typing import Literal

from pydantic import BaseModel, Field

from vos_studio_mcp.schemas.performance_record import PerformanceContext


class SprintBudget(BaseModel):
    max_spend_usd: float = Field(..., gt=0)
    max_images: int | None = None
    max_videos: int | None = None
    alert_threshold_pct: float = Field(default=0.8, ge=0.0, le=1.0)


class VariantInput(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    prompt_version: str = Field(..., min_length=1, max_length=50)
    preset_version: str = Field(..., min_length=1, max_length=50)


class VariantGroupInput(BaseModel):
    hypothesis: str = Field(..., min_length=1)
    variable: str = Field(..., min_length=1, max_length=100)
    variants: list[VariantInput] = Field(..., min_length=2)


class SprintInput(BaseModel):
    client_id: str
    brand_kit_id: str
    product_name: str = Field(..., min_length=1, max_length=200)
    campaign_objective: str = Field(..., min_length=1)
    target_audience: str = Field(..., min_length=1)
    brief: str = Field(..., min_length=1)
    budget: SprintBudget
    mode: Literal["dashboard_manual", "api_credits"] = "dashboard_manual"
    variant_groups: list[VariantGroupInput] = Field(
        default_factory=list,
        description="Optional A/B test groups to create with the sprint (ADR-0027).",
    )
    industry: list[str] = Field(
        default_factory=list,
        description="Industry tags for prompt library suggestions (ADR-0029).",
    )
    format: list[str] = Field(
        default_factory=list,
        description="Format tags for prompt library suggestions (e.g. video_ad, static_image).",
    )
    objective: list[str] = Field(
        default_factory=list,
        description="Objective tags for prompt library suggestions (e.g. conversion, awareness).",
    )
    platform: list[str] = Field(
        default_factory=list,
        description="Platform tags for prompt library suggestions (e.g. meta, tiktok).",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "Optional client-generated key to prevent duplicate sprint creation on retries. "
            "If a sprint with this key already exists for the client, the existing sprint is "
            "returned without creating a new one."
        ),
    )


class BudgetStatus(BaseModel):
    approved_usd: float
    spent_usd: float
    remaining_usd: float
    alert: bool


class LibrarySuggestion(BaseModel):
    template_id: str
    name: str
    performance_tier: str
    avg_ctr: float | None
    prompt_preview: str


class SprintResponse(BaseModel):
    status: str
    sprint_id: str
    summary: str
    budget_status: BudgetStatus
    next_action: str
    variant_groups_created: int = 0
    library_suggestions: list[LibrarySuggestion] = Field(default_factory=list)
    performance_context: PerformanceContext | None = None
    idempotency_key: str | None = None  # echoed back when supplied


class SprintStatusResponse(BaseModel):
    status: str
    sprint_id: str
    product_name: str
    mode: str
    sprint_status: str
    budget_status: BudgetStatus
    asset_count: int
    summary: str
    next_action: str


class CloseSprintInput(BaseModel):
    sprint_id: str
    reason: str | None = None
    force: bool = Field(
        default=False,
        description=(
            "Bypass final-delivery validation. Use only when the approved delivery asset "
            "exists outside the system or when QA is handled externally."
        ),
    )


class CloseSprintResponse(BaseModel):
    status: str
    sprint_id: str
    sprint_status: str
    summary: str
    next_action: str


# ---------------------------------------------------------------------------
# Sprint performance summary (by asset stage)
# ---------------------------------------------------------------------------


class StagePerformanceSummary(BaseModel):
    """Per-stage quality and performance snapshot."""

    asset_stage: str
    asset_stage_label: str | None
    total_assets: int
    approved_count: int
    needs_repair_count: int
    rejected_count: int
    avg_performance_score: float | None


class SprintPerformanceSummaryResponse(BaseModel):
    status: str
    sprint_id: str
    total_assets: int
    by_stage: list[StagePerformanceSummary]
    summary: str
    next_action: str
