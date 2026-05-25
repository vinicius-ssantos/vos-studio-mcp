"""list_provider_capabilities MCP tool (Issue #44)."""
import logging

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.schemas.provider import (
    ListProviderCapabilitiesInput,
    ListProviderCapabilitiesResponse,
    ProviderCapabilitySummary,
)
from vos_studio_mcp.services.providers.capability_registry import list_capabilities
from vos_studio_mcp.tools._instrumentation import instrument

log = logging.getLogger(__name__)


def register_list_provider_capabilities_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def list_provider_capabilities(
        data: ListProviderCapabilitiesInput,
    ) -> ListProviderCapabilitiesResponse:
        """List all registered provider capabilities.

        Returns each provider's modes, asset capabilities, cost profile,
        and safety attributes. Use this before selecting a provider for
        a generation workflow.
        """
        caps = list_capabilities(enabled_only=not data.include_disabled)
        providers = [
            ProviderCapabilitySummary(
                provider_id=c.provider_id,
                display_name=c.display_name,
                modes=list(c.modes),
                capabilities=list(c.capabilities),
                supports_webhooks=c.supports_webhooks,
                supports_polling=c.supports_polling,
                has_free_tier=c.has_free_tier,
                paid_side_effect_risk=c.paid_side_effect_risk,
                requires_human_approval_for_execution=c.requires_human_approval_for_execution,
                default_enabled=c.default_enabled,
                notes=c.notes,
            )
            for c in caps
        ]

        paid = sum(1 for p in providers if p.paid_side_effect_risk)
        free = sum(1 for p in providers if p.has_free_tier)

        log.info("list_provider_capabilities.ok", extra={"count": len(providers)})

        return ListProviderCapabilitiesResponse(
            status="ok",
            providers=providers,
            total=len(providers),
            summary=(
                f"{len(providers)} provider(s) available: "
                f"{paid} paid (approval required), {free} with free tier."
            ),
            next_action="prepare_video_blueprint",
        )
