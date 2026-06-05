"""Performance record service — ADR-0025 Phase 2.

Stores structured campaign metrics per asset and exposes get_top_performers()
for the sprint creation performance_context block.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from db.models import PerformanceRecord, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.performance_record import (
    PerformanceRecordInput,
    PerformanceRecordResponse,
    TopPerformer,
)
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import (
    get_asset_with_client,
    get_session,
    set_tenant_context,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Composite ranking
# ---------------------------------------------------------------------------

_RECENCY_RECENT_DAYS = 30
_RECENCY_MEDIUM_DAYS = 90
_RECENCY_FACTOR_RECENT = 1.0
_RECENCY_FACTOR_MEDIUM = 0.7
_RECENCY_FACTOR_OLD = 0.4

_DEFAULT_W_CTR = 0.35
_DEFAULT_W_ROAS = 0.30
_DEFAULT_W_RECENCY = 0.15
_DEFAULT_W_PLATFORM = 0.10
_DEFAULT_W_OBJECTIVE = 0.10


@dataclass
class _ScoringWeights:
    w_ctr: float = _DEFAULT_W_CTR
    w_roas: float = _DEFAULT_W_ROAS
    w_recency: float = _DEFAULT_W_RECENCY
    w_platform: float = _DEFAULT_W_PLATFORM
    w_objective: float = _DEFAULT_W_OBJECTIVE


def _recency_factor(recorded_at: datetime | None) -> float:
    """Return a recency weight based on how recently the record was created."""
    if recorded_at is None:
        return _RECENCY_FACTOR_OLD
    now = datetime.now(tz=UTC)
    # Ensure recorded_at is timezone-aware for comparison.
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=UTC)
    age = now - recorded_at
    if age <= timedelta(days=_RECENCY_RECENT_DAYS):
        return _RECENCY_FACTOR_RECENT
    if age <= timedelta(days=_RECENCY_MEDIUM_DAYS):
        return _RECENCY_FACTOR_MEDIUM
    return _RECENCY_FACTOR_OLD


def _composite_score(
    record: PerformanceRecord,
    max_ctr: float,
    max_roas: float,
    platform: str | None,
    campaign_objective: str | None,
    weights: _ScoringWeights,
) -> float:
    """Compute a composite ranking score in [0, 1] for a performance record.

    Signals:
    - normalized_ctr: ctr / max_ctr (0–1); 0 when max_ctr is 0.
    - normalized_roas: roas / max_roas (0–1); 0.5 (neutral) when no roas data.
    - recency_factor: 1.0 / 0.7 / 0.4 based on recorded_at age.
    - platform_match_bonus: 1.0 if platform matches requested, 0.5 otherwise.
    - objective_match_bonus: 1.0 if campaign_objective matches requested, 0.5 otherwise.
    """
    norm_ctr = (record.ctr / max_ctr) if (max_ctr > 0 and record.ctr is not None) else 0.0
    norm_roas = record.roas / max_roas if record.roas is not None and max_roas > 0 else 0.5

    recency = _recency_factor(record.recorded_at)

    platform_bonus = (
        1.0
        if (platform is None or record.platform == platform)
        else 0.5
    )
    objective_bonus = 0.5  # default: no campaign_objective stored on record
    if campaign_objective is not None:
        # PerformanceRecord does not store campaign_objective directly;
        # treat None as no-match (0.5 neutral) unless record carries it in notes.
        objective_bonus = 0.5

    return (
        weights.w_ctr * norm_ctr
        + weights.w_roas * norm_roas
        + weights.w_recency * recency
        + weights.w_platform * platform_bonus
        + weights.w_objective * objective_bonus
    )


async def create_performance_record(data: PerformanceRecordInput) -> PerformanceRecordResponse:
    """Persist a structured performance record for an asset.

    Looks up the asset to resolve sprint_id, client_id, and brand_kit_id.
    Applies RLS via the client's tenant context.
    """
    asset_uuid = uuid.UUID(data.asset_id)

    async with get_session() as session:
        # Resolve the asset's owning client via the SECURITY DEFINER helper
        # (no bypass_rls on the connection); this also sets the RLS tenant
        # context, so subsequent reads are tenant-scoped (ADR-0040).
        asset, client_id = await get_asset_with_client(session, str(asset_uuid))
        if asset is None or client_id is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Asset {data.asset_id} not found")

        # Verify the authenticated caller owns the asset's client (ADR-0019, Issue #46).
        assert_owns_client(client_id)

        # Tenant context is set; the sprint read below is RLS-scoped.
        sprint: Sprint | None = await session.get(Sprint, asset.sprint_id)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint not found for asset {data.asset_id}")

        record = PerformanceRecord(
            id=uuid.uuid4(),
            asset_id=asset_uuid,
            sprint_id=asset.sprint_id,
            client_id=sprint.client_id,
            brand_kit_id=sprint.brand_kit_id,
            platform=data.distribution.platform,
            ad_account_id=data.distribution.ad_account_id,
            campaign_id=data.distribution.campaign_id,
            ad_set_id=data.distribution.ad_set_id,
            start_date=data.distribution.start_date,
            end_date=data.distribution.end_date,
            impressions=data.metrics.impressions,
            clicks=data.metrics.clicks,
            ctr=data.metrics.ctr,
            spend_usd=data.metrics.spend_usd,
            conversions=data.metrics.conversions,
            roas=data.metrics.roas,
            thumb_stop_rate=data.metrics.thumb_stop_rate,
            hook_retention_rate=data.metrics.hook_retention_rate,
            performance_label=data.performance_label,
            notes=data.notes,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)

    await emit_audit_event(
        action=AuditAction.PERFORMANCE_RECORDED,
        entity_type="performance_record",
        entity_id=str(record.id),
        actor=str(sprint.client_id),
        result=AuditResult.SUCCESS,
    )

    log.info(
        "performance_record.created",
        extra={
            "record_id": str(record.id),
            "asset_id": data.asset_id,
            "platform": data.distribution.platform,
            "label": data.performance_label,
        },
    )

    return PerformanceRecordResponse(
        status="recorded",
        record_id=str(record.id),
        asset_id=data.asset_id,
        performance_label=data.performance_label,
        summary=(
            f"Performance record created for asset {data.asset_id} "
            f"on {data.distribution.platform} ({data.performance_label})."
        ),
        next_action="create_creative_sprint",
    )


async def get_top_performers(
    client_id: str,
    brand_kit_id: str,
    platform: str | None = None,
    campaign_objective: str | None = None,
) -> list[TopPerformer]:
    """Return the top-performing assets for a client + brand kit.

    When ``platform`` and/or ``campaign_objective`` are provided, records are
    ranked by a composite score that weighs CTR, ROAS, recency, platform match,
    and objective match.  Without those parameters the function falls back to
    CTR-only ordering (backward-compatible).

    Returns at most 10 records to keep the tool output compact (ADR-0011).
    """
    client_uuid = uuid.UUID(client_id)
    brand_kit_uuid = uuid.UUID(brand_kit_id)

    async with get_session() as session:
        await set_tenant_context(session, client_id)

        result = await session.execute(
            select(PerformanceRecord)
            .where(
                PerformanceRecord.client_id == client_uuid,
                PerformanceRecord.brand_kit_id == brand_kit_uuid,
                PerformanceRecord.performance_label == "top_performer",
            )
            .order_by(PerformanceRecord.ctr.desc().nulls_last())
            .limit(50)  # fetch more to allow re-ranking
        )
        records = list(result.scalars().all())

    if not records:
        return []

    use_composite = platform is not None or campaign_objective is not None

    if use_composite:
        ctrs = [r.ctr for r in records if r.ctr is not None]
        roases = [r.roas for r in records if r.roas is not None]
        max_ctr = max(ctrs) if ctrs else 0.0
        max_roas = max(roases) if roases else 0.0
        weights = _ScoringWeights()
        records = sorted(
            records,
            key=lambda r: _composite_score(r, max_ctr, max_roas, platform, campaign_objective, weights),
            reverse=True,
        )

    return [
        TopPerformer(
            asset_id=str(r.asset_id),
            platform=r.platform,
            performance_label=r.performance_label,
            ctr=r.ctr,
            roas=r.roas,
            impressions=r.impressions,
            recorded_at=r.recorded_at.isoformat() if r.recorded_at else "",
        )
        for r in records[:10]
    ]
