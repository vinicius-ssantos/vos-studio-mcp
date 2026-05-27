"""Prompt template schemas for cross-client prompt library (ADR-0029)."""

from pydantic import BaseModel, Field, model_validator


class PromoteToLibraryInput(BaseModel):
    sprint_id: str = Field(..., description="Sprint the source prompt came from")
    prompt_version: str = Field(..., description="Prompt version being promoted")
    name: str = Field(..., min_length=1, max_length=200, description="Template display name")
    description: str = Field(..., min_length=1)
    industry: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    objective: list[str] = Field(default_factory=list)
    platform: list[str] = Field(default_factory=list)
    asset_stage: list[str] = Field(
        default_factory=list,
        description=(
            "VOS production stages this template is suited for "
            "(e.g. stage_a, stage_c, final). Leave empty if stage-agnostic."
        ),
    )
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


class SearchLibraryInput(BaseModel):
    """Input for search_library — at least one filter must be provided."""

    query: str | None = Field(
        default=None,
        description="Keyword(s) to match against template name, description, and prompt text",
    )
    industry: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    objective: list[str] = Field(default_factory=list)
    platform: list[str] = Field(default_factory=list)
    asset_stage: list[str] = Field(
        default_factory=list,
        description=(
            "Filter by VOS production stage tag (e.g. stage_c, final). "
            "Returns templates tagged for the requested stage(s) or stage-agnostic templates."
        ),
    )
    min_tier: str | None = Field(
        default=None,
        description="Minimum performance tier: 'experimental', 'tested', or 'top_performer'",
    )
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def require_at_least_one_filter(self) -> "SearchLibraryInput":
        has_filter = (
            self.query is not None
            or self.industry
            or self.format
            or self.objective
            or self.platform
            or self.asset_stage
            or self.min_tier is not None
        )
        if not has_filter:
            raise ValueError(
                "At least one filter (query, industry, format, objective, platform, "
                "asset_stage, or min_tier) is required"
            )
        return self


class SearchLibraryResult(BaseModel):
    template_id: str
    name: str
    description: str
    performance_tier: str
    avg_ctr: float | None
    usage_count: int
    industry: list[str]
    format: list[str]
    objective: list[str]
    platform: list[str]
    asset_stage: list[str]
    prompt_preview: str  # first 300 chars of anonymized template


class SearchLibraryResponse(BaseModel):
    status: str
    total: int
    results: list[SearchLibraryResult]
    next_action: str
