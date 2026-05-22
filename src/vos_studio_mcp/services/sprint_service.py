"""Sprint service — create and manage creative sprints (ADR-0005)."""

import logging
import uuid

from sqlalchemy import func, select

from db.models import Asset, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.sprint import (
    BudgetStatus,
    CloseSprintInput,
    CloseSprintResponse,
    SprintInput,
    SprintResponse,
    SprintStatusResponse,
)
from vos_studio_mcp.services.database import get_session, set_tenant_context

log = logging.getLogger(__name__)


async def create_creative_sprint(data: SprintInput) -> SprintResponse:
    assert_owns_client(data.client_id)
    async with get_session() as session:
        await set_tenant_context(session, data.client_id)
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
        )
        session.add(sprint)
        await session.commit()
        await session.refresh(sprint)

    log.info(
        "sprint created",
        extra={
            "sprint_id": str(sprint.id),
            "client_id": data.client_id,
            "mode": sprint.mode,
        },
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

    log.info("sprint closed", extra={"sprint_id": data.sprint_id})
    return CloseSprintResponse(
        status="closed",
        sprint_id=data.sprint_id,
        sprint_status="closed",
        summary=f"Sprint for '{product_name}' closed. Use record_asset_performance to log results.",
        next_action="record_asset_performance",
    )
