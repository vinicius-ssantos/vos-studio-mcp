"""Unit tests for client_service — schemas and service functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from vos_studio_mcp.schemas.client import ClientInput, ClientResponse


def test_client_input_validates_name_length():
    with pytest.raises(ValidationError):
        ClientInput(name="", industry="Tech")


def test_client_input_validates_industry_length():
    with pytest.raises(ValidationError):
        ClientInput(name="Acme", industry="")


def test_client_input_validates_email():
    with pytest.raises(ValidationError):
        ClientInput(name="Acme", industry="Tech", contact_email="not-an-email")


def test_client_input_accepts_valid_email():
    data = ClientInput(name="Acme", industry="Tech", contact_email="hello@example.com")
    assert str(data.contact_email) == "hello@example.com"


def test_client_input_optional_fields_default_none():
    data = ClientInput(name="Acme Corp", industry="Technology")
    assert data.contact_name is None
    assert data.contact_email is None
    assert data.notes is None


def test_client_input_name_max_length():
    with pytest.raises(ValidationError):
        ClientInput(name="x" * 201, industry="Tech")


def test_client_response_shape():
    resp = ClientResponse(
        status="created",
        client_id=str(uuid.uuid4()),
        name="Acme",
        summary="Client 'Acme' created in industry 'Tech'.",
        next_action="save_brand_kit",
    )
    assert resp.status == "created"
    assert resp.next_action == "save_brand_kit"


# ---------------------------------------------------------------------------
# Service function tests — mocked AsyncSession
# ---------------------------------------------------------------------------

_GET_SESSION = "vos_studio_mcp.services.client_service.get_session"


def _client_ctx(fixed_id: uuid.UUID | None = None) -> MagicMock:
    _id = fixed_id or uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", _id))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_create_client_success() -> None:
    from vos_studio_mcp.services.client_service import create_client

    fixed_id = uuid.uuid4()
    ctx = _client_ctx(fixed_id=fixed_id)

    with patch(_GET_SESSION, return_value=ctx):
        result = await create_client(ClientInput(name="Acme Corp", industry="Technology"))

    assert result.status == "created"
    assert result.client_id == str(fixed_id)
    assert result.name == "Acme Corp"
    assert "Acme Corp" in result.summary
    assert result.next_action == "save_brand_kit"


@pytest.mark.asyncio
async def test_create_client_with_contact_email() -> None:
    from vos_studio_mcp.services.client_service import create_client

    ctx = _client_ctx()

    data = ClientInput(
        name="Beta Corp",
        industry="Retail",
        contact_name="Jane Doe",
        contact_email="jane@beta.com",
    )

    with patch(_GET_SESSION, return_value=ctx):
        result = await create_client(data)

    assert result.status == "created"
    assert "Beta Corp" in result.summary
