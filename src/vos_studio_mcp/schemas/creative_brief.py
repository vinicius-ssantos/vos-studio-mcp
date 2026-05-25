"""Creative brief intake schemas (Issue #48)."""

from pydantic import BaseModel, Field


class BriefConstraints(BaseModel):
    """Optional constraints extracted from client compliance/brand notes."""

    claims_allowed: list[str] = Field(default_factory=list)
    claims_forbidden: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)
    brand_voice: str = ""
    compliance_notes: str = ""


class RequiredAsset(BaseModel):
    asset_type: str          # "video", "image", "carousel"
    format: str              # "9:16", "1:1", "16:9"
    quantity: int
    notes: str = ""


class CreativeBriefInput(BaseModel):
    client_id: str
    raw_brief: str = Field(min_length=10, description="Raw brief text from the client")
    product_description: str = Field(min_length=3)
    target_audience: str = Field(min_length=3)
    platform: str = Field(default="meta", description="Primary platform: meta, tiktok, youtube, linkedin")
    constraints: BriefConstraints = Field(default_factory=BriefConstraints)


class CreativeBriefResponse(BaseModel):
    status: str
    client_id: str
    campaign_objective: str
    offer_and_promise: str
    target_persona: str
    pain_points: list[str]
    objections: list[str]
    creative_angles: list[str]
    required_assets: list[RequiredAsset]
    suggested_sprint_type: str   # "dashboard_manual" or "api_credits"
    provider_suitability_notes: str
    approval_checklist: list[str]
    missing_information: list[str]
    summary: str
    next_action: str
