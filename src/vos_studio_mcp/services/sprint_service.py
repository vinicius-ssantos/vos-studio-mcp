"""Sprint service — create and manage creative sprints (ADR-0005)."""

import logging
import uuid

from sqlalchemy import func, select

from db.models import Asset, BrandKit, Sprint, Variant, VariantGroup
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.asset import _ASSET_STAGE_LABELS
from vos_studio_mcp.schemas.performance_record import PerformanceContext
from vos_studio_mcp.schemas.sprint import (
    BudgetStatus,
    CloseSprintInput,
    CloseSprintResponse,
    LibrarySuggestion,
    SprintInput,
    SprintListFilters,
    SprintListItem,
    SprintListResponse,
    SprintPerformanceSummaryResponse,
    SprintResponse,
    SprintStatusResponse,
    StagePerformanceSummary,
)
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.database import get_session, set_tenant_context
from vos_studio_mcp.services.performance_record_service import get_top_performers
from vos_studio_mcp.services.prompt_library_service import get_library_suggestions
from vos_studio_mcp.services.rate_limiter import check_rate_limit

log = logging.getLogger(__name__)


def _str_list(memory: dict[str, object], key: str) -> list[str]:
    """Extract a string list from a performance_memory dict key."""
    value = memory.get(key)
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


async def _find_idempotent_sprint(
    session: object, client_id: str, idempotency_key: str
) -> Sprint | None:
    """Return an existing sprint with the given idempotency key, or None."""
    result = await (session).execute(  # type: ignore[attr-defined]
        select(Sprint).where(
            Sprint.client_id == uuid.UUID(client_id),
            Sprint.idempotency_key == idempotency_key,
        )
    )
    found: Sprint | None = result.scalars().first()
    return found


async def create_creative_sprint(data: SprintInput) -> SprintResponse:
    assert_owns_client(data.client_id)
    await check_rate_limit("create_creative_sprint", data.client_id)
    async with get_session() as session:
        await set_tenant_context(session, data.client_id)

        # Idempotency: if a sprint with this key already exists, return it.
        if data.idempotency_key is not None:
            existing = await _find_idempotent_sprint(session, data.client_id, data.idempotency_key)
            if existing is not None:
                log.info(
                    "sprint.idempotent_replay",
                    extra={
                        "sprint_id": str(existing.id),
                        "idempotency_key": data.idempotency_key,
                    },
                )
                alert = (
                    existing.spent_usd >= existing.max_spend_usd * existing.alert_threshold_pct
                )
                return SprintResponse(
                    status="created",
                    sprint_id=str(existing.id),
                    summary=(
                        f"Idempotent replay: returning existing sprint for "
                        f"'{existing.product_name}'."
                    ),
                    budget_status=BudgetStatus(
                        approved_usd=existing.max_spend_usd,
                        spent_usd=existing.spent_usd,
                        remaining_usd=existing.max_spend_usd - existing.spent_usd,
                        alert=alert,
                    ),
                    next_action="prepare_dashboard_pack",
                    idempotency_key=data.idempotency_key,
                )

        sprint = Sprint(
            client_id=uuid.UUID(data.client_id),
            brand_kit_id=uuid.UUID(data.brand_kit_id),
            product_name=data.product_name,
            campaign_objective=data.campaign_objective,
            target_audience=data.target_audience,
            brief=data.brief,
            mode=data.mode,
            max_spend_usd=data.budget.max_spend_usd,
            max_images=data.budget.max_images,
            max_videos=data.budget.max_videos,
            alert_threshold_pct=data.budget.alert_threshold_pct,
            spent_usd=0.0,
            sprint_status="open",
            idempotency_key=data.idempotency_key,
        )
        session.add(sprint)
        await session.flush()  # get sprint.id before adding children

        for vg_input in data.variant_groups:
            group = VariantGroup(
                id=uuid.uuid4(),
                sprint_id=sprint.id,
                hypothesis=vg_input.hypothesis,
                variable=vg_input.variable,
                status="running",
            )
            session.add(group)
            await session.flush()
            for v_input in vg_input.variants:
                session.add(
                    Variant(
                        id=uuid.uuid4(),
                        group_id=group.id,
                        label=v_input.label,
                        description=v_input.description,
                        prompt_version=v_input.prompt_version,
                        preset_version=v_input.preset_version,
                    )
                )

        await session.commit()
        await session.refresh(sprint)

    log.info(
        "sprint created",
        extra={
            "sprint_id": str(sprint.id),
            "client_id": data.client_id,
            "mode": sprint.mode,
            "variant_groups": len(data.variant_groups),
        },
    )

    await emit_audit_event(
        action=AuditAction.SPRINT_CREATED,
        entity_type="sprint",
        entity_id=str(sprint.id),
        actor=data.client_id,
        mode=sprint.mode,
        result=AuditResult.SUCCESS,
    )

    library_suggestions = await get_library_suggestions(
        industry=data.industry,
        format=data.format,
        objective=data.objective,
        platform=data.platform,
    )

    top_performers = await get_top_performers(data.client_id, data.brand_kit_id)

    # Enrich performance_context from brand_kit qualitative memory + quantitative records
    performance_context: PerformanceContext | None = None
    async with get_session() as session:
        await set_tenant_context(session, data.client_id)
        brand_kit = await session.get(BrandKit, uuid.UUID(data.brand_kit_id))

    if brand_kit is not None:
        mem: dict[str, object] = dict(brand_kit.performance_memory)
        top_angles: list[str] = _str_list(mem, "proven_angles")
        proven_hooks: list[str] = _str_list(mem, "proven_hooks")
        avoid_approaches: list[str] = _str_list(mem, "failed_approaches")
        if top_angles or proven_hooks or avoid_approaches or top_performers:
            performance_context = PerformanceContext(
                top_angles=top_angles,
                proven_hooks=proven_hooks,
                avoid_approaches=avoid_approaches,
                top_performers=top_performers,
            )

    alert = sprint.spent_usd >= sprint.max_spend_usd * sprint.alert_threshold_pct
    return SprintResponse(
        status="created",
        sprint_id=str(sprint.id),
        summary=(
            f"Creative sprint for '{sprint.product_name}' created "
            f"in {sprint.mode} mode with ${sprint.max_spend_usd:.2f} budget."
        ),
        budget_status=BudgetStatus(
            approved_usd=sprint.max_spend_usd,
            spent_usd=sprint.spent_usd,
            remaining_usd=sprint.max_spend_usd - sprint.spent_usd,
            alert=alert,
        ),
        next_action="prepare_dashboard_pack",
        variant_groups_created=len(data.variant_groups),
        library_suggestions=[
            LibrarySuggestion(
                template_id=s.template_id,
                name=s.name,
                performance_tier=s.performance_tier,
                avg_ctr=s.avg_ctr,
                prompt_preview=s.prompt_preview,
            )
            for s in library_suggestions
        ],
        performance_context=performance_context,
        idempotency_key=data.idempotency_key,
    )


async def get_sprint_status(sprint_id: str) -> SprintStatusResponse:
    sprint_uuid = uuid.UUID(sprint_id)
    async with get_session() as session:
        sprint = await session.get(Sprint, sprint_uuid)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {sprint_id} not found")
        # Verify the authenticated caller owns the sprint's client (ADR-0019, Issue #46).
        assert_owns_client(str(sprint.client_id))

        asset_count_result = await session.execute(
            select(func.count()).where(Asset.sprint_id == sprint_uuid)
        )
        asset_count = asset_count_result.scalar_one()

    alert = sprint.spent_usd >= sprint.max_spend_usd * sprint.alert_threshold_pct
    remaining = sprint.max_spend_usd - sprint.spent_usd

    if sprint.sprint_status == "open" and not alert:
        next_action = "prepare_dashboard_pack"
    elif alert:
        next_action = "review_budget_before_continuing"
    else:
        next_action = "no_action_sprint_closed"

    return SprintStatusResponse(
        status="ok",
        sprint_id=sprint_id,
        product_name=sprint.product_name,
        mode=sprint.mode,
        sprint_status=sprint.sprint_status,
        budget_status=BudgetStatus(
            approved_usd=sprint.max_spend_usd,
            spent_usd=sprint.spent_usd,
            remaining_usd=remaining,
            alert=alert,
        ),
        asset_count=asset_count,
        summary=(
            f"Sprint '{sprint.product_name}' is {sprint.sprint_status} with "
            f"{asset_count} asset(s) registered and ${remaining:.2f} remaining."
        ),
        next_action=next_action,
    )


async def close_sprint(data: CloseSprintInput) -> CloseSprintResponse:
    sprint_uuid = uuid.UUID(data.sprint_id)
    async with get_session() as session:
        sprint = await session.get(Sprint, sprint_uuid)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")
        # Verify the authenticated caller owns the sprint's client (ADR-0019, Issue #46).
        assert_owns_client(str(sprint.client_id))
        if sprint.sprint_status == "closed":
            raise VosError(ErrorCode.INVALID_INPUT, f"Sprint {data.sprint_id} is already closed")

        # Guard: require at least one QA-approved final delivery asset unless force=True.
        # Ensures sprints only close after a deliverable has been reviewed and approved.
        if not data.force:
            delivery_result = await session.execute(
                select(Asset).where(
                    Asset.sprint_id == sprint_uuid,
                    Asset.is_final_delivery.is_(True),
                    Asset.qa_status == "approved",
                )
            )
            if not delivery_result.scalars().first():
                raise VosError(
                    ErrorCode.VALIDATION_ERROR,
                    "Sprint cannot be closed: no QA-approved final delivery asset found. "
                    "Register an asset with is_final_delivery=True and run review_asset_quality "
                    "to approve it — or pass force=True to close without a delivery asset.",
                )

        sprint.sprint_status = "closed"
        await session.commit()
        product_name = sprint.product_name

    await emit_audit_event(
        action=AuditAction.SPRINT_CLOSED,
        entity_type="sprint",
        entity_id=data.sprint_id,
        result=AuditResult.SUCCESS,
    )
    log.info("sprint closed", extra={"sprint_id": data.sprint_id})
    return CloseSprintResponse(
        status="closed",
        sprint_id=data.sprint_id,
        sprint_status="closed",
        summary=f"Sprint for '{product_name}' closed. Use record_asset_performance to log results.",
        next_action="record_asset_performance",
    )


async def get_sprint_performance_summary(
    sprint_id: str,
) -> SprintPerformanceSummaryResponse:
    """Return per-stage asset quality and performance snapshot for a sprint."""
    sprint_uuid = uuid.UUID(sprint_id)
    async with get_session() as session:
        sprint = await session.get(Sprint, sprint_uuid)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {sprint_id} not found")
        assert_owns_client(str(sprint.client_id))

        result = await session.execute(select(Asset).where(Asset.sprint_id == sprint_uuid))
        assets = list(result.scalars().all())

    # Group assets by stage
    from collections import defaultdict

    by_stage: dict[str, list[Asset]] = defaultdict(list)
    for asset in assets:
        stage = asset.asset_stage or "untagged"
        by_stage[stage].append(asset)

    stage_summaries: list[StagePerformanceSummary] = []
    for stage, stage_assets in sorted(by_stage.items()):
        scores = [a.performance_score for a in stage_assets if a.performance_score is not None]
        stage_summaries.append(
            StagePerformanceSummary(
                asset_stage=stage,
                asset_stage_label=_ASSET_STAGE_LABELS.get(stage),
                total_assets=len(stage_assets),
                approved_count=sum(1 for a in stage_assets if a.qa_status == "approved"),
                needs_repair_count=sum(
                    1 for a in stage_assets if a.qa_status == "needs_repair"
                ),
                rejected_count=sum(1 for a in stage_assets if a.qa_status == "rejected"),
                avg_performance_score=sum(scores) / len(scores) if scores else None,
            )
        )

    has_approved = any(s.approved_count > 0 for s in stage_summaries)
    return SprintPerformanceSummaryResponse(
        status="ok",
        sprint_id=sprint_id,
        total_assets=len(assets),
        by_stage=stage_summaries,
        summary=(
            f"Sprint '{sprint.product_name}' has {len(assets)} asset(s) "
            f"across {len(stage_summaries)} stage(s)."
        ),
        next_action="close_sprint" if has_approved else "review_asset_quality",
    )


async def list_sprints(
    client_id: str,
    filters: SprintListFilters | None = None,
) -> SprintListResponse:
    """List all sprints for a client, newest first, with per-sprint asset count."""
    assert_owns_client(client_id)
    _filters = filters or SprintListFilters()
    async with get_session() as session:
        await set_tenant_context(session, client_id)
        query = (
            select(Sprint)
            .where(Sprint.client_id == uuid.UUID(client_id))
            .order_by(Sprint.created_at.desc())
            .limit(_filters.limit)
        )
        if _filters.status is not None:
            query = query.where(Sprint.sprint_status == _filters.status)

        result = await session.execute(query)
        sprints = list(result.scalars().all())

        counts: dict[uuid.UUID, int] = {}
        if sprints:
            sprint_ids = [s.id for s in sprints]
            count_result = await session.execute(
                select(Asset.sprint_id, func.count(Asset.id))
                .where(Asset.sprint_id.in_(sprint_ids))
                .group_by(Asset.sprint_id)
            )
            counts = {row[0]: row[1] for row in count_result.all()}

    items = [
        SprintListItem(
            sprint_id=str(s.id),
            product_name=s.product_name,
            sprint_status=s.sprint_status,
            mode=s.mode,
            spent_usd=s.spent_usd,
            max_spend_usd=s.max_spend_usd,
            asset_count=counts.get(s.id, 0),
            created_at=s.created_at.isoformat(),
        )
        for s in sprints
    ]
    return SprintListResponse(
        status="ok",
        client_id=client_id,
        total=len(items),
        sprints=items,
        next_action="get_sprint_status" if items else "create_creative_sprint",
    )
