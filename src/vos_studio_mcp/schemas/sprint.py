"""Creative sprint schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class SprintBudget(BaseModel):
    max_spend_usd: float = Field(..., gt=0)
    max_images: int | None = None
    max_videos: int | None = None
    alert_threshold_pct: float = Field(default=0.8, ge=0.0, le=1.0)


class SprintInput(BaseModel):
    client_id: str
    brand_kit_id: str
    product_name: str = Field(..., min_length=1, max_length=200)
    campaign_objective: str = Field(..., min_length=1)
    target_audience: str = Field(..., min_length=1)
    brief: str = Field(..., min_length=1)
    budget: SprintBudget
    mode: Literal["dashboard_manual", "api_credits"] = "dashboard_manual"


class BudgetStatus(BaseModel):
    approved_usd: float
    spent_usd: float
    remaining_usd: float
    alert: bool


class SprintResponse(BaseModel):
    status: str
    sprint_id: str
    summary: str
    budget_status: BudgetStatus
    next_action: str


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
