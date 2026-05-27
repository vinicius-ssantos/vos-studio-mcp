"""Brand kit schemas (ADR-0024, Issue #56)."""

from typing import Literal

from pydantic import BaseModel, Field


class BrandIdentity(BaseModel):
    brand_name: str
    tagline: str | None = None
    voice: list[str] = Field(default_factory=list)
    tone: list[str] = Field(default_factory=list)
    target_audience: str
    positioning: str


class BrandVisualSystem(BaseModel):
    primary_colors: list[str] = Field(default_factory=list)
    secondary_colors: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    style_keywords: list[str] = Field(default_factory=list)


class BrandRestrictions(BaseModel):
    forbidden_elements: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    content_warnings: list[str] = Field(default_factory=list)
    platform_rules: dict[str, list[str]] = Field(default_factory=dict)


class BrandPerformanceMemory(BaseModel):
    proven_angles: list[str] = Field(default_factory=list)
    proven_hooks: list[str] = Field(default_factory=list)
    failed_approaches: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Campaign visual system v2 — Asset Lock (Issue #56)
# ---------------------------------------------------------------------------


class AssetLock(BaseModel):
    """Explicit campaign visual constraints for the Asset Lock system.

    These fields describe the allowed and forbidden visual registers, materials,
    environments, and policies that govern all creative assets in this campaign.
    They expand on the lighter `BrandVisualSystem` by making constraints
    actionable and specific enough for operator-level execution.
    """

    dominant_register: str = Field(
        default="",
        description="Primary visual register for the campaign (e.g. 'bold product-forward').",
    )
    secondary_register: str = Field(
        default="",
        description="Supporting visual register (e.g. 'warm lifestyle').",
    )
    forbidden_register: list[str] = Field(
        default_factory=list,
        description="Visual registers explicitly forbidden in this campaign.",
    )
    allowed_materials: list[str] = Field(
        default_factory=list,
        description="Materials/surfaces allowed in visual compositions.",
    )
    forbidden_materials: list[str] = Field(
        default_factory=list,
        description="Materials/surfaces forbidden in visual compositions.",
    )
    allowed_environments: list[str] = Field(
        default_factory=list,
        description="Environments/settings allowed in visual compositions.",
    )
    forbidden_environments: list[str] = Field(
        default_factory=list,
        description="Environments/settings forbidden in visual compositions.",
    )
    text_policy: str = Field(
        default="",
        description=(
            "Text-in-frame policy, e.g. 'no text except CTA on shot 8' or "
            "'brand tagline only in final frame'."
        ),
    )
    endcard_policy: str = Field(
        default="",
        description=(
            "Endcard requirements, e.g. 'brand logo + CTA button, 2 seconds minimum'."
        ),
    )
    reference_asset_ids: list[str] = Field(
        default_factory=list,
        description="Asset IDs of approved reference assets for this campaign.",
    )


# ---------------------------------------------------------------------------
# Input / output
# ---------------------------------------------------------------------------


class BrandKitInput(BaseModel):
    client_id: str
    name: str = Field(..., min_length=1, max_length=200)
    identity: BrandIdentity
    visual: BrandVisualSystem
    restrictions: BrandRestrictions
    asset_lock: AssetLock | None = Field(
        default=None,
        description="Optional campaign visual system / asset lock constraints.",
    )


class BrandKitResponse(BaseModel):
    status: str
    brand_kit_id: str
    version: str
    name: str
    summary: str
    next_action: str


class BrandKitSummary(BaseModel):
    brand_kit_id: str
    version: str
    name: str
    status: Literal["active", "archived"]
