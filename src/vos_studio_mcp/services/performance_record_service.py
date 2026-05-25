"""Performance record service — ADR-0025 Phase 2.

Stores structured campaign metrics per asset and exposes get_top_performers()
for the sprint creation performance_context block.
"""

import logging
import uuid

from sqlalchemy import select

from db.models import Asset, PerformanceRecord, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.performance_record import (
    PerformanceRecordInput,
    PerformanceRecordResponse,
    TopPerformer,
)
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import bypass_rls, get_session, set_tenant_context

log = logging.getLogger(__name__)


async def create_performance_record(data: PerformanceRecordInput) -> PerformanceRecordResponse:
    """Persist a structured performance record for an asset.

    Looks up the asset to resolve sprint_id, client_id, and brand_kit_id.
    Applies RLS via the client's tenant context.
    """
    asset_uuid = uuid.UUID(data.asset_id)

    async with get_session() as session:
        # Bypass RLS to look up the asset's client context
        await bypass_rls(session)

        asset: Asset | None = await session.get(Asset, asset_uuid)
        if asset is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Asset {data.asset_id} not found")

        sprint: Sprint | None = await session.get(Sprint, asset.sprint_id)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint not found for asset {data.asset_id}")

        # Verify the authenticated caller owns the sprint's client (ADR-0019, Issue #46).
        assert_owns_client(str(sprint.client_id))
        await set_tenant_context(session, str(sprint.client_id))

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


async def get_top_performers(client_id: str, brand_kit_id: str) -> list[TopPerformer]:
    """Return the top-performing assets for a client + brand kit, ordered by CTR desc.

    Used by create_creative_sprint to populate the performance_context block.
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
            .limit(10)
        )
        records = list(result.scalars().all())

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
        for r in records
    ]
