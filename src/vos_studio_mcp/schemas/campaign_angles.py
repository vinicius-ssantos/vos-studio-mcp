"""Campaign angle generator schemas (Issue #49)."""
from pydantic import BaseModel, Field


class CampaignAnglesInput(BaseModel):
    client_id: str
    product_description: str = Field(min_length=3)
    target_audience: str = Field(min_length=3)
    platform: str = Field(default="meta")
    campaign_objective: str = Field(default="brand_awareness")
    existing_angles: list[str] = Field(default_factory=list, description="Angles already tried — avoid repeating")
    n_angles: int = Field(default=5, ge=1, le=10)


class CampaignAngle(BaseModel):
    angle_id: str   # e.g. "angle_01"
    title: str      # short hook title
    hook: str       # the opening hook line
    angle_type: str  # "emotional", "rational", "social_proof", "urgency", "curiosity", "authority"
    primary_message: str
    cta: str         # call to action
    format_suggestion: str  # e.g. "15s Reel", "30s YouTube pre-roll"


class CampaignAnglesResponse(BaseModel):
    status: str
    client_id: str
    product_description: str
    target_audience: str
    platform: str
    angles: list[CampaignAngle]
    diversity_score: float  # 0.0 to 1.0: ratio of unique angle_types
    summary: str
    next_action: str
