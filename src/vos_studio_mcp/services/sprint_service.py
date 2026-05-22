"""Sprint service — create and manage creative sprints (ADR-0005)."""

import logging
import uuid

from db.models import Sprint
from vos_studio_mcp.schemas.sprint import BudgetStatus, SprintInput, SprintResponse
from vos_studio_mcp.services.database import get_session, set_tenant_context

log = logging.getLogger(__name__)


async def create_creative_sprint(data: SprintInput) -> SprintResponse:
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
