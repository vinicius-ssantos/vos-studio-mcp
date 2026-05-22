"""Variant group schemas for A/B testing (ADR-0027)."""

from typing import Literal

from pydantic import BaseModel, Field


class ConcludeVariantTestInput(BaseModel):
    group_id: str = Field(..., description="UUID of the VariantGroup to conclude")
    winner_variant_id: str | None = Field(
        default=None,
        description="UUID of the winning Variant. Omit to mark as inconclusive.",
    )
    confirmed: bool = Field(
        default=False,
        description="Must be True to commit the conclusion.",
    )


class VariantSummary(BaseModel):
    variant_id: str
    label: str
    prompt_version: str
    preset_version: str


class ConcludeVariantTestResponse(BaseModel):
    status: str
    group_id: str
    outcome: Literal["concluded", "inconclusive"]
    winner_variant_id: str | None
    hypothesis: str
    variable: str
    variants: list[VariantSummary]
    summary: str
    next_action: str
