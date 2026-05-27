"""Client performance analytics — cross-sprint aggregation (ADR-0025)."""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from db.models import PerformanceRecord, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.client_analytics import ClientPerformanceSummaryResponse
from vos_studio_mcp.schemas.performance_record import TopPerformer
from vos_studio_mcp.services.database import get_session, set_tenant_context

log = logging.getLogger(__name__)

_DEFAULT_PERIOD_DAYS = 90
_TOP_PERFORMERS_LIMIT = 5
_RECORDS_LIMIT = 500  # cap to avoid unbounded scans


async def get_client_performance_summary(
    client_id: str,
    period_days: int = _DEFAULT_PERIOD_DAYS,
) -> ClientPerformanceSummaryResponse:
    """Aggregate PerformanceRecord data across all sprints for a client.

    Returns avg CTR/ROAS, best platform, and top-performing assets for the
    requested look-back window (default: 90 days).
    """
    assert_owns_client(client_id)

    if period_days < 1 or period_days > 730:
        raise VosError(
            ErrorCode.INVALID_INPUT,
            "period_days must be between 1 and 730",
        )

    cutoff = datetime.now(UTC) - timedelta(days=period_days)
    client_uuid = uuid.UUID(client_id)

    async with get_session() as session:
        await set_tenant_context(session, client_id)

        # Total sprint count for the client (all time)
        sprint_count_result = await session.execute(
            select(func.count(Sprint.id)).where(Sprint.client_id == client_uuid)
        )
        total_sprints: int = sprint_count_result.scalar_one()

        # Performance records in the requested window
        records_result = await session.scalars(
            select(PerformanceRecord)
            .where(
                PerformanceRecord.client_id == client_uuid,
                PerformanceRecord.recorded_at >= cutoff,
            )
            .order_by(PerformanceRecord.ctr.desc().nulls_last())
            .limit(_RECORDS_LIMIT)
        )
        records = list(records_result)

    # ── Aggregate stats ────────────────────────────────────────────────────
    ctrs = [r.ctr for r in records if r.ctr is not None]
    roases = [r.roas for r in records if r.roas is not None]
    avg_ctr = sum(ctrs) / len(ctrs) if ctrs else None
    avg_roas = sum(roases) / len(roases) if roases else None

    # Platform with most top_performer records
    top_performer_platforms = [
        r.platform for r in records if r.performance_label == "top_performer"
    ]
    platform_counts = Counter(top_performer_platforms)
    top_platform = platform_counts.most_common(1)[0][0] if platform_counts else None

    # Top N assets by CTR
    top_records = [r for r in records if r.performance_label == "top_performer"][
        :_TOP_PERFORMERS_LIMIT
    ]
    top_performers = [
        TopPerformer(
            asset_id=str(r.asset_id),
            platform=r.platform,
            performance_label=r.performance_label,
            ctr=r.ctr,
            roas=r.roas,
            impressions=r.impressions,
            recorded_at=r.recorded_at.isoformat(),
        )
        for r in top_records
    ]

    ctr_str = f"{avg_ctr:.1%}" if avg_ctr is not None else "n/a"
    roas_str = f"{avg_roas:.2f}x" if avg_roas is not None else "n/a"

    return ClientPerformanceSummaryResponse(
        status="ok",
        client_id=client_id,
        period_days=period_days,
        total_sprints=total_sprints,
        total_records=len(records),
        avg_ctr=avg_ctr,
        avg_roas=avg_roas,
        top_platform=top_platform,
        top_performing_assets=top_performers,
        summary=(
            f"{total_sprints} sprint(s) | {len(records)} record(s) in last {period_days}d | "
            f"avg CTR {ctr_str} | avg ROAS {roas_str}"
        ),
        next_action="record_performance_metrics" if not records else "create_creative_sprint",
    )
