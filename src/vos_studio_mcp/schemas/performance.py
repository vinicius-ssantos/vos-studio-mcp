"""Performance feedback schemas (ADR-0025)."""

from typing import Literal

from pydantic import BaseModel, Field


class PerformanceInput(BaseModel):
    asset_id: str
    sprint_id: str
    score: int = Field(..., ge=1, le=5)
    label: Literal["top_performer", "failed", "neutral"] = "neutral"
    hook_label: str | None = None
    angle_label: str | None = None
    notes: str | None = None


class PerformanceResponse(BaseModel):
    status: str
    asset_id: str
    brand_kit_updated: bool
    summary: str
    next_action: str
