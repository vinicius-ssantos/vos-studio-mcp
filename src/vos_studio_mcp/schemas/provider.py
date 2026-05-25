"""Provider capability schemas for MCP tool output (Issue #44)."""
from pydantic import BaseModel


class ProviderCapabilitySummary(BaseModel):
    provider_id: str
    display_name: str
    modes: list[str]
    capabilities: list[str]
    supports_webhooks: bool
    supports_polling: bool
    has_free_tier: bool
    paid_side_effect_risk: bool
    requires_human_approval_for_execution: bool
    default_enabled: bool
    notes: str


class ListProviderCapabilitiesInput(BaseModel):
    include_disabled: bool = False


class ListProviderCapabilitiesResponse(BaseModel):
    status: str
    providers: list[ProviderCapabilitySummary]
    total: int
    summary: str
    next_action: str
