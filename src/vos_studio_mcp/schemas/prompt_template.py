"""Prompt template schemas for cross-client prompt library (ADR-0029)."""

from pydantic import BaseModel, Field


class PromoteToLibraryInput(BaseModel):
    sprint_id: str = Field(..., description="Sprint the source prompt came from")
    prompt_version: str = Field(..., description="Prompt version being promoted")
    name: str = Field(..., min_length=1, max_length=200, description="Template display name")
    description: str = Field(..., min_length=1)
    industry: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    objective: list[str] = Field(default_factory=list)
    platform: list[str] = Field(default_factory=list)
    prompt_template: str = Field(
        ...,
        min_length=1,
        description="Anonymized prompt with {{placeholders}} for brand-specific values",
    )
    negative_prompt_template: str | None = None
    preset_recommendations: list[str] = Field(default_factory=list)
    confirmed: bool = Field(
        default=False,
        description="Must be True to save. Use False to preview anonymization checklist.",
    )


class PromptTemplateSuggestion(BaseModel):
    template_id: str
    name: str
    performance_tier: str
    avg_ctr: float | None
    prompt_preview: str


class PromoteToLibraryResponse(BaseModel):
    status: str
    template_id: str | None
    name: str
    performance_tier: str
    summary: str
    next_action: str
    anonymization_checklist: list[str]
