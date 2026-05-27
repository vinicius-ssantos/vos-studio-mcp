"""Video blueprint schemas (issue #13)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

_SUPPORTED_PROVIDERS = Literal["higgsfield", "freepik", "magnific", "manual"]


class VideoBlueprintInput(BaseModel):
    sprint_id: str = Field(..., description="Sprint to build the blueprint from.")
    prompt_version: str = Field(default="v1", description="Prompt version tag.")
    preset_version: str = Field(default="p1", description="Preset version tag.")
    provider_targets: list[_SUPPORTED_PROVIDERS] = Field(
        default=["higgsfield", "freepik", "magnific", "manual"],
        min_length=1,
        description="Providers to include execution packs for.",
    )
    shot_count: int = Field(
        default=9,
        ge=1,
        le=15,
        description="Number of shots in the shot plan.",
    )


# ---------------------------------------------------------------------------
# Output sub-models
# ---------------------------------------------------------------------------


class ShotPlan(BaseModel):
    shot_number: int
    scene_description: str
    motion_prompt: str
    keyframe_guidance: str
    camera_movement: str
    pacing: str
    duration_seconds: int


class ProviderExecutionPack(BaseModel):
    provider: str
    model_recommendation: str
    adapted_prompt: str
    settings: dict[str, Any]
    checklist: list[str]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class VideoBlueprintResponse(BaseModel):
    status: str
    sprint_id: str
    creative_intent: str
    campaign_objective: str
    shot_plan: list[ShotPlan]
    negative_prompts: list[str]
    provider_packs: list[ProviderExecutionPack]
    manual_checklist: list[str]
    cost_notes: str
    risk_notes: str
    approval_required: bool
    summary: str
    next_action: str
