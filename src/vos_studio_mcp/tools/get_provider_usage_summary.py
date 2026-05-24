"""get_provider_usage_summary MCP tool — provider quota and budget ledger (ADR-0034)."""

import datetime
import logging

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.budget import ProviderUsageSummaryInput, ProviderUsageSummaryResponse
from vos_studio_mcp.services.budget_guard import get_provider_daily_summary

log = logging.getLogger(__name__)

_UTC = datetime.UTC


def register_get_provider_usage_summary_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_provider_usage_summary(data: ProviderUsageSummaryInput) -> ProviderUsageSummaryResponse:
        """Return today's provider API spend and remaining daily quota.

        Shows estimated and actual costs per provider for the current calendar
        day (UTC).  Useful for monitoring daily quota consumption before
        triggering further paid generations.

        Requires an authenticated session.
        """
        client_id = get_current_client_id()
        if client_id is None:
            raise VosError(ErrorCode.AUTH_REQUIRED, "Authentication required to view provider usage")

        settings = get_settings()
        daily_limit = settings.provider_daily_limit_usd
        today_str = datetime.datetime.now(_UTC).date().isoformat()

        stats = await get_provider_daily_summary(provider=data.provider)

        total_estimated = sum(s.total_estimated_usd for s in stats)
        limit_enforced = daily_limit > 0
        remaining = max(0.0, daily_limit - total_estimated) if limit_enforced else 0.0

        if not stats:
            summary = f"No provider usage recorded for {today_str}."
        elif limit_enforced:
            summary = (
                f"Provider spend today: ${total_estimated:.2f} / ${daily_limit:.2f} limit "
                f"(${remaining:.2f} remaining)."
            )
        else:
            summary = f"Provider spend today: ${total_estimated:.2f} (no daily limit enforced)."

        log.info(
            "get_provider_usage_summary.ok",
            extra={
                "client_id": client_id,
                "provider_filter": data.provider,
                "total_estimated_usd": total_estimated,
                "daily_limit_usd": daily_limit,
            },
        )

        return ProviderUsageSummaryResponse(
            status="ok",
            date=today_str,
            providers=stats,
            total_estimated_usd=total_estimated,
            daily_limit_usd=daily_limit,
            remaining_usd=remaining,
            limit_enforced=limit_enforced,
            summary=summary,
            next_action="request_api_video" if not limit_enforced or remaining > 0 else "quota_exhausted",
        )
