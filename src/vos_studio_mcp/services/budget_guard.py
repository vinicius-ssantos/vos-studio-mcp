"""Provider quota and budget ledger (ADR-0034, Issue #42).

check_provider_budget() enforces a global daily spend cap per provider.
record_actual_cost()    updates a usage event with the final billed amount.
get_provider_daily_summary() returns today's per-provider totals for the
  get_provider_usage_summary tool.
"""

import datetime
import logging
import uuid

from sqlalchemy import func, select

from db.models import ProviderUsageEvent
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.budget import ProviderDailyStats
from vos_studio_mcp.services.database import get_privileged_session

log = logging.getLogger(__name__)

_UTC = datetime.UTC


def _today_start() -> datetime.datetime:
    """Return midnight UTC for the current calendar day."""
    return datetime.datetime.now(_UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def check_provider_budget(
    provider: str,
    client_id: str,
    sprint_id: str,
    estimated_usd: float,
) -> str:
    """Enforce the global daily provider quota and record the usage event.

    Raises ``VosError(QUOTA_EXCEEDED)`` if the daily limit is set and the new
    request would push today's estimated spend past it.

    Returns the ``str(UUID)`` of the created ``ProviderUsageEvent`` so the
    caller can later update it with ``record_actual_cost()``.

    If ``PROVIDER_DAILY_LIMIT_USD`` is 0 (the default) no enforcement is done
    but a usage event is still written to build the ledger.
    """
    settings = get_settings()
    daily_limit = settings.provider_daily_limit_usd
    today = _today_start()

    # Cross-tenant by design: the daily cap is global per provider (ADR-0040
    # step 2 — privileged connection, RLS bypassed at the role level).
    async with get_privileged_session() as session:
        # Sum all estimated spend for this provider today
        today_spend_result = await session.execute(
            select(func.coalesce(func.sum(ProviderUsageEvent.estimated_usd), 0.0)).where(
                ProviderUsageEvent.provider == provider,
                ProviderUsageEvent.recorded_at >= today,
            )
        )
        today_spend: float = float(today_spend_result.scalar_one())

        if daily_limit > 0 and today_spend + estimated_usd > daily_limit:
            raise VosError(
                ErrorCode.QUOTA_EXCEEDED,
                f"Daily provider quota for '{provider}' would be exceeded "
                f"(today: ${today_spend:.2f}, "
                f"limit: ${daily_limit:.2f}, "
                f"estimated: ${estimated_usd:.2f})",
            )

        event = ProviderUsageEvent(
            id=uuid.uuid4(),
            provider=provider,
            sprint_id=uuid.UUID(sprint_id),
            client_id=uuid.UUID(client_id),
            estimated_usd=estimated_usd,
            actual_usd=None,
            event_type="generation_requested",
        )
        session.add(event)
        await session.commit()

    log.info(
        "budget_guard.event_recorded",
        extra={
            "provider": provider,
            "client_id": client_id,
            "sprint_id": sprint_id,
            "estimated_usd": estimated_usd,
            "today_spend_before": today_spend,
            "daily_limit": daily_limit,
            "event_id": str(event.id),
        },
    )
    return str(event.id)


async def record_actual_cost(event_id: str, actual_usd: float) -> None:
    """Update a usage event with the final billed amount.

    Called by the poll task when a generation job completes and the provider
    returns the actual cost.  Best-effort: logs and swallows errors so it
    never blocks the primary workflow.
    """
    try:
        async with get_privileged_session() as session:
            event: ProviderUsageEvent | None = await session.get(
                ProviderUsageEvent, uuid.UUID(event_id)
            )
            if event is None:
                log.warning("budget_guard.event_not_found", extra={"event_id": event_id})
                return
            event.actual_usd = actual_usd
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "budget_guard.actual_cost_update_failed",
            extra={"event_id": event_id, "reason": str(exc)},
        )


async def get_provider_daily_summary(
    provider: str | None = None,
) -> list[ProviderDailyStats]:
    """Return today's aggregated spend per provider.

    ``provider=None`` returns all providers that have events today.
    """
    today = _today_start()

    # Global per-provider aggregation across all tenants (ADR-0040 step 2).
    async with get_privileged_session() as session:
        query = (
            select(
                ProviderUsageEvent.provider,
                func.sum(ProviderUsageEvent.estimated_usd).label("total_estimated"),
                func.sum(ProviderUsageEvent.actual_usd).label("total_actual"),
                func.count().label("event_count"),
            )
            .where(ProviderUsageEvent.recorded_at >= today)
            .group_by(ProviderUsageEvent.provider)
            .order_by(ProviderUsageEvent.provider)
        )
        if provider is not None:
            query = query.where(ProviderUsageEvent.provider == provider)

        result = await session.execute(query)
        rows = result.all()

    return [
        ProviderDailyStats(
            provider=row.provider,
            total_estimated_usd=float(row.total_estimated or 0.0),
            total_actual_usd=float(row.total_actual) if row.total_actual is not None else None,
            event_count=int(row.event_count),
        )
        for row in rows
    ]
