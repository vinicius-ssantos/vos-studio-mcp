"""Variant service — A/B test conclusion (ADR-0027)."""

import datetime
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.models import VariantGroup
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.variant import (
    ConcludeVariantTestInput,
    ConcludeVariantTestResponse,
    VariantSummary,
)
from vos_studio_mcp.services.database import get_session, set_tenant_context_from_sprint

log = logging.getLogger(__name__)


async def conclude_variant_test(data: ConcludeVariantTestInput) -> ConcludeVariantTestResponse:
    async with get_session() as session:
        group = await session.scalar(
            select(VariantGroup)
            .where(VariantGroup.id == uuid.UUID(data.group_id))
            .options(selectinload(VariantGroup.variants))
        )
        if group is None:
            raise VosError(ErrorCode.NOT_FOUND, f"VariantGroup {data.group_id} not found")

        await set_tenant_context_from_sprint(session, str(group.sprint_id))

        if group.status != "running":
            raise VosError(
                ErrorCode.INVALID_INPUT,
                f"VariantGroup {data.group_id} is already {group.status}",
            )

        if data.winner_variant_id is not None:
            winner_ids = {str(v.id) for v in group.variants}
            if data.winner_variant_id not in winner_ids:
                raise VosError(
                    ErrorCode.INVALID_INPUT,
                    f"Variant {data.winner_variant_id} does not belong to group {data.group_id}",
                )

        if not data.confirmed:
            outcome: str = "concluded" if data.winner_variant_id else "inconclusive"
            return _preview_response(group, outcome, data.winner_variant_id)

        outcome = "concluded" if data.winner_variant_id else "inconclusive"
        group.status = outcome
        group.winner_variant_id = (
            uuid.UUID(data.winner_variant_id) if data.winner_variant_id else None
        )
        group.concluded_at = datetime.datetime.now(datetime.UTC)
        await session.commit()
        await session.refresh(group)

    log.info(
        "variant_test.concluded",
        extra={
            "group_id": data.group_id,
            "outcome": outcome,
            "winner_variant_id": data.winner_variant_id,
        },
    )
    return _build_response(group, outcome, data.winner_variant_id)


def _preview_response(
    group: VariantGroup, outcome: str, winner_variant_id: str | None
) -> ConcludeVariantTestResponse:
    return _build_response(group, outcome, winner_variant_id, preview=True)


def _build_response(
    group: VariantGroup,
    outcome: str,
    winner_variant_id: str | None,
    preview: bool = False,
) -> ConcludeVariantTestResponse:
    variants = [
        VariantSummary(
            variant_id=str(v.id),
            label=v.label,
            prompt_version=v.prompt_version,
            preset_version=v.preset_version,
        )
        for v in group.variants
    ]
    if preview:
        summary = (
            f"Preview: group '{group.variable}' would be marked {outcome}. "
            "Set confirmed=True to commit."
        )
        next_action = "conclude_variant_test"
    elif outcome == "concluded":
        summary = (
            f"Variant test on '{group.variable}' concluded. "
            f"Winner: {winner_variant_id}. Consider updating the brand kit's proven angles."
        )
        next_action = "save_brand_kit"
    else:
        summary = (
            f"Variant test on '{group.variable}' marked inconclusive. "
            "Run more assets to gather sufficient signal before concluding."
        )
        next_action = "list_sprint_assets"

    return ConcludeVariantTestResponse(
        status="ok" if not preview else "preview",
        group_id=str(group.id),
        outcome=outcome,
        winner_variant_id=winner_variant_id,
        hypothesis=group.hypothesis,
        variable=group.variable,
        variants=variants,
        summary=summary,
        next_action=next_action,
    )
