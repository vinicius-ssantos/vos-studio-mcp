"""Provider capability registry.

This module keeps static provider metadata separate from adapter instances so
orchestration code can select providers by capability before executing any
external action.
"""

from vos_studio_mcp.schemas.provider import ProviderCapability

_PROVIDER_CAPABILITIES: dict[str, ProviderCapability] = {
    "manual_dashboard": ProviderCapability(
        provider_id="manual_dashboard",
        display_name="Manual Dashboard",
        modes=["dashboard_manual"],
        capabilities=["manual_dashboard_pack"],
        supports_webhooks=False,
        supports_polling=False,
        requires_api_key=False,
        has_free_tier=False,
        paid_side_effect_risk=False,
        requires_human_approval_for_execution=False,
        default_enabled=True,
    ),
    "higgsfield": ProviderCapability(
        provider_id="higgsfield",
        display_name="Higgsfield",
        modes=["dashboard_manual", "api_credits"],
        capabilities=["image_to_video", "text_to_video", "job_status_polling"],
        supports_webhooks=True,
        supports_polling=True,
        requires_api_key=True,
        has_free_tier=False,
        paid_side_effect_risk=True,
        requires_human_approval_for_execution=True,
        default_enabled=True,
    ),
    "freepik": ProviderCapability(
        provider_id="freepik",
        display_name="Freepik",
        modes=["dashboard_manual", "api_credits"],
        capabilities=["text_to_image", "job_status_polling"],
        supports_webhooks=True,
        supports_polling=True,
        requires_api_key=True,
        has_free_tier=False,
        paid_side_effect_risk=True,
        requires_human_approval_for_execution=True,
        default_enabled=True,
    ),
    "magnific": ProviderCapability(
        provider_id="magnific",
        display_name="Magnific",
        modes=["dashboard_manual", "api_credits"],
        capabilities=["upscale", "job_status_polling"],
        supports_webhooks=True,
        supports_polling=True,
        requires_api_key=True,
        has_free_tier=False,
        paid_side_effect_risk=True,
        requires_human_approval_for_execution=True,
        default_enabled=True,
    ),
}


def list_provider_capabilities(
    *, include_disabled: bool = False,
) -> list[ProviderCapability]:
    """Return provider capabilities ordered by provider ID."""

    providers = sorted(_PROVIDER_CAPABILITIES.values(), key=lambda item: item.provider_id)
    if include_disabled:
        return providers
    return [provider for provider in providers if provider.default_enabled]


def get_provider_capability(provider_id: str) -> ProviderCapability:
    """Return capability metadata for a provider ID."""

    try:
        return _PROVIDER_CAPABILITIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Unknown provider capability: {provider_id}") from exc
