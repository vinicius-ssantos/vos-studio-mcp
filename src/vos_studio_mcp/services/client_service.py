"""Client service — create and manage client records."""

import logging
import uuid

from db.models import Client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.client import (
    ClientInput,
    ClientResponse,
    SetClientWebhookInput,
    SetClientWebhookResponse,
)
from vos_studio_mcp.services.database import get_session, set_tenant_context
from vos_studio_mcp.services.webhook_ssrf_guard import validate_webhook_url

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


async def set_client_webhook(
    client_id: str,
    data: SetClientWebhookInput,
) -> SetClientWebhookResponse:
    """Set or clear the outbound webhook URL for a client (Issue #47).

    URL is validated with the SSRF guard before persisting so private/local
    addresses are rejected at registration time, not only at delivery time.

    Requires the caller to supply a valid *client_id* (UUID string).
    """
    if data.webhook_url is not None:
        validate_webhook_url(data.webhook_url)

    try:
        cid = uuid.UUID(client_id)
    except ValueError as exc:
        raise VosError(ErrorCode.INVALID_INPUT, f"Invalid client_id: {client_id!r}") from exc

    async with get_session() as session:
        # client_id comes from the authenticated context (never caller input),
        # so scope the session to it and let RLS enforce that we can only read
        # and mutate this client's own row — no bypass_rls (ADR-0040).
        await set_tenant_context(session, client_id)
        client = await session.get(Client, cid)

        if client is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Client {client_id!r} not found.")

        client.webhook_url = data.webhook_url
        await session.commit()

    action = "set" if data.webhook_url else "cleared"
    log.info(
        f"client_webhook.{action}",
        extra={"client_id": client_id, "webhook_url": data.webhook_url},
    )
    return SetClientWebhookResponse(
        status="updated",
        client_id=client_id,
        webhook_url=data.webhook_url,
        summary=(
            f"Webhook URL {action} for client {client_id}."
            if data.webhook_url
            else f"Webhook URL cleared for client {client_id}."
        ),
    )
