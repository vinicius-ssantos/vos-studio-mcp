"""set_client_webhook MCP tool (Issue #47)."""

from mcp.server.fastmcp import FastMCP

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.client import SetClientWebhookInput, SetClientWebhookResponse
from vos_studio_mcp.services.client_service import set_client_webhook as set_webhook_service
from vos_studio_mcp.tools._instrumentation import instrument


def register_set_client_webhook_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    @instrument
    async def set_client_webhook(data: SetClientWebhookInput) -> SetClientWebhookResponse:
        """Set or clear the outbound webhook URL for the authenticated client.

        When set, VOS Studio posts a signed JSON payload to this URL when a
        video generation job completes or fails (see event schema in ADR-0033).

        URL requirements:
        - Must use HTTPS.
        - Must resolve to a publicly routable IP address.
        - Private/local/cloud-metadata addresses are rejected.

        Pass ``webhook_url: null`` to disable outbound notifications.
        """
        client_id = get_current_client_id()
        if not client_id:
            raise VosError(
                ErrorCode.AUTH_REQUIRED,
                "Authentication required to set webhook URL.",
            )
        return await set_webhook_service(client_id, data)
