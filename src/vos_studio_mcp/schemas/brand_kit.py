"""Brand kit schemas (ADR-0024)."""

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


class BrandKitInput(BaseModel):
    client_id: str
    name: str = Field(..., min_length=1, max_length=200)
    identity: BrandIdentity
    visual: BrandVisualSystem
    restrictions: BrandRestrictions


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
