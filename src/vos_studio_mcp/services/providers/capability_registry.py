"""Provider capability registry (Issue #44).

Single source of truth for what each provider can do. Used by tools and
services to answer "which provider supports X?" without hard-coded assumptions.
"""
from dataclasses import dataclass
from typing import Literal

ProviderMode = Literal["dashboard_manual", "api_credits", "api_free_public", "local_or_self_hosted"]
ProviderCapabilityType = Literal["text_to_image", "image_to_video", "text_to_video", "upscale", "asset_qa"]


@dataclass(frozen=True)
class ProviderCapability:
    provider_id: str
    display_name: str
    modes: list[ProviderMode]
    capabilities: list[ProviderCapabilityType]
    supports_webhooks: bool
    supports_polling: bool
    requires_api_key: bool
    has_free_tier: bool
    paid_side_effect_risk: bool
    requires_human_approval_for_execution: bool
    default_enabled: bool
    notes: str = ""


_REGISTRY: dict[str, ProviderCapability] = {
    "manual_dashboard": ProviderCapability(
        provider_id="manual_dashboard",
        display_name="Manual Dashboard",
        modes=["dashboard_manual"],
        capabilities=["text_to_image", "image_to_video", "text_to_video"],
        supports_webhooks=False,
        supports_polling=False,
        requires_api_key=False,
        has_free_tier=True,
        paid_side_effect_risk=False,
        requires_human_approval_for_execution=True,
        default_enabled=True,
        notes="Human executes prompts manually via provider dashboards. No API calls.",
    ),
    "higgsfield": ProviderCapability(
        provider_id="higgsfield",
        display_name="Higgsfield Animate",
        modes=["api_credits"],
        capabilities=["image_to_video"],
        supports_webhooks=True,
        supports_polling=True,
        requires_api_key=True,
        has_free_tier=False,
        paid_side_effect_risk=True,
        requires_human_approval_for_execution=True,
        default_enabled=True,
        notes="API-based image-to-video generation. Requires approval_token before execution.",
    ),
    "freepik": ProviderCapability(
        provider_id="freepik",
        display_name="Freepik Mystic",
        modes=["api_credits"],
        capabilities=["text_to_image", "text_to_video"],
        supports_webhooks=True,
        supports_polling=True,
        requires_api_key=True,
        has_free_tier=False,
        paid_side_effect_risk=True,
        requires_human_approval_for_execution=True,
        default_enabled=True,
        notes="API-based text-to-image and text-to-video generation.",
    ),
    "magnific": ProviderCapability(
        provider_id="magnific",
        display_name="Magnific Upscale+Motion",
        modes=["api_credits"],
        capabilities=["upscale", "image_to_video"],
        supports_webhooks=True,
        supports_polling=True,
        requires_api_key=True,
        has_free_tier=False,
        paid_side_effect_risk=True,
        requires_human_approval_for_execution=True,
        default_enabled=True,
        notes="API-based image upscaling and motion enhancement.",
    ),
    "cloudflare_workers_ai": ProviderCapability(
        provider_id="cloudflare_workers_ai",
        display_name="Cloudflare Workers AI",
        modes=["api_free_public"],
        capabilities=["text_to_image"],
        supports_webhooks=False,
        supports_polling=False,
        requires_api_key=True,
        has_free_tier=True,
        paid_side_effect_risk=False,
        requires_human_approval_for_execution=False,
        default_enabled=False,
        notes="Free-tier text-to-image generation. Disabled by default; enable via CLOUDFLARE_WORKERS_AI_ENABLED=true.",
    ),
}


def get_capability(provider_id: str) -> ProviderCapability:
    cap = _REGISTRY.get(provider_id)
    if cap is None:
        raise KeyError(f"No capability entry for provider '{provider_id}'")
    return cap


def list_capabilities(enabled_only: bool = True) -> list[ProviderCapability]:
    """Return capabilities, optionally filtered to only default-enabled providers."""
    caps = list(_REGISTRY.values())
    if enabled_only:
        caps = [c for c in caps if c.default_enabled]
    return caps


def get_providers_for_capability(
    capability: ProviderCapabilityType,
    enabled_only: bool = True,
) -> list[ProviderCapability]:
    """Return all providers that support the given capability type."""
    return [
        c for c in list_capabilities(enabled_only=enabled_only)
        if capability in c.capabilities
    ]
