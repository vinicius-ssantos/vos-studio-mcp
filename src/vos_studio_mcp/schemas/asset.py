"""Asset schemas."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Stage / kind constants
# ---------------------------------------------------------------------------

AssetStage = Literal["stage_0", "stage_a", "stage_b", "stage_c", "repair", "final"]
AssetKind = Literal["generated", "manual", "upscaled"]

_ASSET_STAGE_LABELS: dict[str, str] = {
    "stage_0": "Stage 0 â€” Anchor Image",
    "stage_a": "Stage A â€” Character Sheet",
    "stage_b": "Stage B â€” Storyboard",
    "stage_c": "Stage C â€” Video",
    "repair": "Repair Variant",
    "final": "Final Delivery",
}


class AssetInput(BaseModel):
    sprint_id: str
    provider: str
    prompt_version: str = "v1"
    preset_version: str = "p1"
    storage_url: str
    preview_url: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    notes: str | None = None
    # Stage / lineage (Issue #53)
    asset_stage: AssetStage | None = Field(
        default=None,
        description="VOS production stage this asset belongs to.",
    )
    asset_kind: AssetKind = Field(
        default="manual",
        description="How the asset was produced: generated, manual, or upscaled.",
    )
    source_asset_id: str | None = Field(
        default=None,
        description="Asset ID of the source asset (for repairs, upscales, or derived assets).",
    )
    approved_as_reference: bool = Field(
        default=False,
        description="True when QA-approved for use as reference in future sprints.",
    )
    is_final_delivery: bool = Field(
        default=False,
        description="True when this asset is the final deliverable for the sprint.",
    )

    @model_validator(mode="before")
    @classmethod
    def accept_agent_friendly_aliases(cls, raw: Any) -> Any:
        """Accept common MCP-agent aliases while keeping the canonical contract."""
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        if "storage_url" not in data and "uri" in data:
            data["storage_url"] = data["uri"]
        if "format" not in data and "mime_type" in data:
            data["format"] = data["mime_type"]
        return data


class AssetReference(BaseModel):
    asset_id: str
    storage_url: str
    preview_url: str | None = None


class AssetResponse(BaseModel):
    status: str
    asset_id: str
    sprint_id: str
    summary: str
    next_action: str


class AssetListItem(BaseModel):
    asset_id: str
    provider: str
    prompt_version: str
    preset_version: str
    storage_url: str
    preview_url: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    # Stage / lineage (Issue #53)
    asset_stage: str | None = None
    asset_stage_label: str | None = None
    asset_kind: str = "manual"
    source_asset_id: str | None = None
    approved_as_reference: bool = False
    is_final_delivery: bool = False
    generation_status: str | None = None
    storage_status: str | None = None
    # QA review outcome (Issue #57)
    qa_status: str | None = None


class AssetListResponse(BaseModel):
    status: str
    sprint_id: str
    total: int
    assets: list[AssetListItem]
    next_action: str


class AssetListFilters(BaseModel):
    """Optional filters for list_sprint_assets."""

    asset_stage: AssetStage | None = Field(
        default=None,
        description="Filter by VOS production stage (e.g. stage_c, repair).",
    )
    qa_status: Literal["needs_review", "approved", "needs_repair", "rejected"] | None = Field(
        default=None,
        description=(
            "Filter by QA review outcome. 'needs_review' = ready for QA but not yet reviewed. "
            "Omit to return all."
        ),
    )
