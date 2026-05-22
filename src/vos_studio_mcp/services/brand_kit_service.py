"""Brand kit service — save and version brand kits (ADR-0024)."""

import logging
import uuid

from db.models import BrandKit
from vos_studio_mcp.schemas.brand_kit import BrandKitInput, BrandKitResponse
from vos_studio_mcp.services.database import get_session, set_tenant_context

log = logging.getLogger(__name__)


async def save_brand_kit(data: BrandKitInput) -> BrandKitResponse:
    async with get_session() as session:
        await set_tenant_context(session, data.client_id)
        brand_kit = BrandKit(
            client_id=uuid.UUID(data.client_id),
            name=data.name,
            version="1.0",
            status="active",
            identity=data.identity.model_dump(),
            visual=data.visual.model_dump(),
            restrictions=data.restrictions.model_dump(),
        )
        session.add(brand_kit)
        await session.commit()
        await session.refresh(brand_kit)

    log.info(
        "brand kit saved",
        extra={"brand_kit_id": str(brand_kit.id), "client_id": data.client_id},
    )
    return BrandKitResponse(
        status="created",
        brand_kit_id=str(brand_kit.id),
        version=brand_kit.version,
        name=brand_kit.name,
        summary=f"Brand kit '{brand_kit.name}' v{brand_kit.version} saved.",
        next_action="create_creative_sprint",
    )
