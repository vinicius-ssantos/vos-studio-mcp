"""Asset service — register manually produced assets (ADR-0008)."""

import logging
import uuid

from sqlalchemy import select

from db.models import Asset
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.asset import (
    _ASSET_STAGE_LABELS,
    AssetInput,
    AssetListItem,
    AssetListResponse,
    AssetResponse,
)
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import get_session, set_tenant_context_from_sprint

log = logging.getLogger(__name__)


async def register_manual_asset(data: AssetInput) -> AssetResponse:
    async with get_session() as session:
        # Resolve sprint ownership, set RLS tenant context, and assert caller owns the sprint.
        try:
            client_id = await set_tenant_context_from_sprint(session, data.sprint_id)
        except LookupError as exc:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found") from exc
        assert_owns_client(client_id)

        source_uuid = uuid.UUID(data.source_asset_id) if data.source_asset_id else None


        asset = Asset(
            sprint_id=uuid.UUID(data.sprint_id),
            provider=data.provider,
            prompt_version=data.prompt_version,
            preset_version=data.preset_version,
            storage_url=data.storage_url,
            preview_url=data.preview_url,
            width=data.width,
            height=data.height,
            format=data.format,
            notes=data.notes,
            # Stage / lineage (Issue #53)
            asset_stage=data.asset_stage,
            asset_kind=data.asset_kind,
            source_asset_id=source_uuid,
            approved_as_reference=data.approved_as_reference,
            is_final_delivery=data.is_final_delivery,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)

    stage_label = _ASSET_STAGE_LABELS.get(asset.asset_stage or "", "")

    await emit_audit_event(
        action=AuditAction.MANUAL_ASSET_REGISTERED,
        entity_type="asset",
        entity_id=str(asset.id),
        provider=data.provider,
        mode="dashboard_manual",
        result=AuditResult.SUCCESS,
    )
    log.info(
        "asset registered",
        extra={
            "asset_id": str(asset.id),
            "sprint_id": data.sprint_id,
            "asset_stage": data.asset_stage,
            "asset_kind": data.asset_kind,
        },
    )

    stage_note = f" [{stage_label}]" if stage_label else ""
    return AssetResponse(
        status="registered",
        asset_id=str(asset.id),
        sprint_id=data.sprint_id,
        summary=(
            f"Asset registered for sprint {data.sprint_id} via {data.provider}{stage_note}."
        ),
        next_action="register_manual_asset",
    )


async def list_sprint_assets(sprint_id: str) -> AssetListResponse:
    sprint_uuid = uuid.UUID(sprint_id)
    async with get_session() as session:
        # Resolve sprint ownership, set RLS tenant context, and assert caller owns the sprint.
        try:
            client_id = await set_tenant_context_from_sprint(session, sprint_id)
        except LookupError as exc:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {sprint_id} not found") from exc
        assert_owns_client(client_id)

        result = await session.execute(
            select(Asset).where(Asset.sprint_id == sprint_uuid).order_by(Asset.created_at)
        )
        rows = list(result.scalars().all())

    items = [
        AssetListItem(
            asset_id=str(row.id),
            provider=row.provider,
            prompt_version=row.prompt_version,
            preset_version=row.preset_version,
            storage_url=row.storage_url or "",
            preview_url=row.preview_url,
            width=row.width,
            height=row.height,
            format=row.format,
            # Stage / lineage (Issue #53)
            asset_stage=row.asset_stage,
            asset_stage_label=_ASSET_STAGE_LABELS.get(row.asset_stage or "", None),
            asset_kind=row.asset_kind,
            source_asset_id=str(row.source_asset_id) if row.source_asset_id else None,
            approved_as_reference=row.approved_as_reference,
            is_final_delivery=row.is_final_delivery,
            generation_status=row.generation_status,
            storage_status=row.storage_status,
            qa_status=row.qa_status,
        )
        for row in rows
    ]

    return AssetListResponse(
        status="ok",
        sprint_id=sprint_id,
        total=len(items),
        assets=items,
        next_action="prepare_dashboard_pack" if items else "prepare_dashboard_pack",
    )
