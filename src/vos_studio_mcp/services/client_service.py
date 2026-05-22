"""Client service — create and manage client records."""

import logging

from db.models import Client
from vos_studio_mcp.schemas.client import ClientInput, ClientResponse
from vos_studio_mcp.services.database import get_session

log = logging.getLogger(__name__)


async def create_client(data: ClientInput) -> ClientResponse:
    async with get_session() as session:
        client = Client(
            name=data.name,
            industry=data.industry,
            contact_name=data.contact_name,
            contact_email=str(data.contact_email) if data.contact_email else None,
            notes=data.notes,
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

    log.info("client created", extra={"client_id": str(client.id)})
    return ClientResponse(
        status="created",
        client_id=str(client.id),
        name=client.name,
        summary=f"Client '{client.name}' created in industry '{client.industry}'.",
        next_action="save_brand_kit",
    )
