"""Provider capability response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProviderMode = Literal[
    "dashboard_manual",
    "api_credits",
    "api_free_public",
    "local_or_self_hosted",
]

ProviderCapabilityName = Literal[
    "text_to_image",
    "image_to_video",
    "text_to_video",
    "upscale",
    "manual_dashboard_pack",
    "job_status_polling",
]


class ProviderCapability(BaseModel):
    """Static provider capability metadata used for safe provider selection."""

    provider_id: str
    display_name: str
    modes: list[ProviderMode] = Field(default_factory=list)
    capabilities: list[ProviderCapabilityName] = Field(default_factory=list)
    supports_webhooks: bool = False
    supports_polling: bool = False
    requires_api_key: bool = False
    has_free_tier: bool = False
    paid_side_effect_risk: bool = False
    requires_human_approval_for_execution: bool = False
    default_enabled: bool = True


class ProviderCapabilitiesResponse(BaseModel):
    """Compact list of provider capabilities exposed via MCP."""

    providers: list[ProviderCapability]
    total: int
    next_action: str | None = None
