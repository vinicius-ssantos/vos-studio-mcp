"""Asset service — register manually produced assets (ADR-0008)."""

import logging
import uuid

from db.models import Asset
from vos_studio_mcp.schemas.asset import AssetInput, AssetResponse
from vos_studio_mcp.services.database import get_session

log = logging.getLogger(__name__)


async def register_manual_asset(data: AssetInput) -> AssetResponse:
    async with get_session() as session:
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
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)

    log.info(
        "asset registered",
        extra={"asset_id": str(asset.id), "sprint_id": data.sprint_id},
    )
    return AssetResponse(
        status="registered",
        asset_id=str(asset.id),
        sprint_id=data.sprint_id,
        summary=f"Asset registered for sprint {data.sprint_id} via {data.provider}.",
        next_action="register_manual_asset",
    )
