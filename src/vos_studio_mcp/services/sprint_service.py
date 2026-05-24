"""Sprint service — create and manage creative sprints (ADR-0005)."""

import logging
import uuid

from sqlalchemy import func, select

from db.models import Asset, BrandKit, Sprint, Variant, VariantGroup
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.performance_record import PerformanceContext
from vos_studio_mcp.schemas.sprint import (
    BudgetStatus,
    CloseSprintInput,
    CloseSprintResponse,
    LibrarySuggestion,
    SprintInput,
    SprintResponse,
    SprintStatusResponse,
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
        if sprint.sprint_status == "closed":
            raise VosError(ErrorCode.INVALID_INPUT, f"Sprint {data.sprint_id} is already closed")

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
