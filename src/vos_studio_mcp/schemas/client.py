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
