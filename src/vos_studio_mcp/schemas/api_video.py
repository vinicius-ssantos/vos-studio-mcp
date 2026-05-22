"""API video generation schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class ApiVideoInput(BaseModel):
    sprint_id: str
    client_id: str
    prompt: str = Field(..., min_length=1)
    prompt_version: str
    preset_version: str
    approval_token: str = Field(..., min_length=1)
    image_url: str | None = None
    duration_seconds: int = Field(default=5, ge=5, le=10)
    resolution: Literal["480p", "720p", "1080p"] = "720p"
    aspect_ratio: Literal["16:9", "4:3", "1:1", "9:21"] = "16:9"


class ApiVideoResponse(BaseModel):
    status: str
    job_id: str
    asset_id: str
    sprint_id: str
    estimated_cost_usd: float
    summary: str
    next_action: str


class VideoJobStatusResponse(BaseModel):
    status: str
    asset_id: str
    generation_status: str
    storage_url: str | None
    provider_job_id: str | None
    summary: str
    next_action: str
