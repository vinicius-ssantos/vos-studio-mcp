"""Client schemas."""

from pydantic import BaseModel, EmailStr, Field


class ClientInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    industry: str = Field(..., min_length=1, max_length=100)
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    notes: str | None = None


class ClientResponse(BaseModel):
    status: str
    client_id: str
    name: str
    summary: str
    next_action: str


# ---------------------------------------------------------------------------
# set_client_webhook
# ---------------------------------------------------------------------------


class SetClientWebhookInput(BaseModel):
    """Input for setting or clearing the client's outbound webhook URL.

    Set ``webhook_url`` to an HTTPS URL to enable job-completion notifications.
    Set it to ``null`` to disable notifications.
    """

    webhook_url: str | None = Field(
        None,
        max_length=2048,
        description=(
            "HTTPS endpoint that will receive signed job-completion events. "
            "Must be publicly reachable; private/local addresses are rejected. "
            "Set to null to disable notifications."
        ),
    )


class SetClientWebhookResponse(BaseModel):
    status: str
    client_id: str
    webhook_url: str | None
    summary: str
