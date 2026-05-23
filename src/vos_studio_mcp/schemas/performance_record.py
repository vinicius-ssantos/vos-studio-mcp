"""Performance record schemas — ADR-0025 Phase 2 structured distribution + metrics."""

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class DistributionContext(BaseModel):
    platform: str = Field(..., description="Ad platform, e.g. 'meta', 'google', 'tiktok'.")
    ad_account_id: str | None = None
    campaign_id: str | None = None
    ad_set_id: str | None = None
    start_date: str = Field(..., description="ISO 8601 date, e.g. '2026-05-01'.")
    end_date: str | None = None


class PerformanceMetrics(BaseModel):
    impressions: int | None = None
    clicks: int | None = None
    ctr: float | None = Field(default=None, description="Click-through rate (0–1).")
    spend_usd: float | None = None
    conversions: int | None = None
    roas: float | None = Field(default=None, description="Return on ad spend.")
    thumb_stop_rate: float | None = Field(default=None, description="3-second view rate (0–1).")
    hook_retention_rate: float | None = Field(default=None, description="Watch-through rate (0–1).")


class TopPerformer(BaseModel):
    asset_id: str
    platform: str
    performance_label: str
    ctr: float | None
    roas: float | None
    impressions: int | None
    recorded_at: str


class PerformanceContext(BaseModel):
    top_angles: list[str]
    proven_hooks: list[str]
    avoid_approaches: list[str]
    top_performers: list[TopPerformer]


# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------


class PerformanceRecordInput(BaseModel):
    asset_id: str = Field(..., description="Asset the metrics belong to.")
    distribution: DistributionContext
    metrics: PerformanceMetrics
    performance_label: Literal["top_performer", "average", "underperformer"]
    notes: str | None = None


class PerformanceRecordResponse(BaseModel):
    status: str
    record_id: str
    asset_id: str
    performance_label: str
    summary: str
    next_action: str
