"""Performance feedback service — record results and update brand kit memory (ADR-0025)."""

import logging
import uuid

from db.models import Asset, BrandKit, Sprint
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.performance import PerformanceInput, PerformanceResponse
from vos_studio_mcp.services.database import get_session

log = logging.getLogger(__name__)


def _get_list(memory: dict[str, object], key: str) -> list[str]:
    value = memory.get(key)
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


async def record_asset_performance(data: PerformanceInput) -> PerformanceResponse:
    asset_uuid = uuid.UUID(data.asset_id)
    sprint_uuid = uuid.UUID(data.sprint_id)

    async with get_session() as session:
        asset = await session.get(Asset, asset_uuid)
        if asset is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Asset {data.asset_id} not found")
        if asset.sprint_id != sprint_uuid:
            raise VosError(
                ErrorCode.INVALID_INPUT,
                f"Asset {data.asset_id} does not belong to sprint {data.sprint_id}",
            )

        asset.performance_score = data.score
        asset.performance_label = data.label
        asset.performance_notes = data.notes
        if data.variant_id is not None:
            asset.variant_id = uuid.UUID(data.variant_id)

        sprint = await session.get(Sprint, sprint_uuid)
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")

        brand_kit_updated = False
        brand_kit = await session.get(BrandKit, sprint.brand_kit_id)
        if brand_kit is not None:
            memory: dict[str, object] = dict(brand_kit.performance_memory)

            if data.label == "top_performer":
                if data.angle_label:
                    angles = _get_list(memory, "proven_angles")
                    if data.angle_label not in angles:
                        angles.append(data.angle_label)
                    memory["proven_angles"] = angles
                if data.hook_label:
                    hooks = _get_list(memory, "proven_hooks")
                    if data.hook_label not in hooks:
                        hooks.append(data.hook_label)
                    memory["proven_hooks"] = hooks
            elif data.label == "failed":
                description = data.notes or data.angle_label or data.hook_label
                if description:
                    failed = _get_list(memory, "failed_approaches")
                    if description not in failed:
                        failed.append(description)
                    memory["failed_approaches"] = failed

            brand_kit.performance_memory = memory
            brand_kit_updated = True

        await session.commit()

    log.info(
        "performance recorded",
        extra={
            "asset_id": data.asset_id,
            "label": data.label,
            "score": data.score,
            "brand_kit_updated": brand_kit_updated,
        },
    )
    return PerformanceResponse(
        status="recorded",
        asset_id=data.asset_id,
        brand_kit_updated=brand_kit_updated,
        summary=(
            f"Asset {data.asset_id} recorded as {data.label} (score {data.score}/5)."
            + (" Brand kit memory updated." if brand_kit_updated else "")
        ),
        next_action="record_asset_performance",
    )
