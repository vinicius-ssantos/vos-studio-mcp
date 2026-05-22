"""Unit tests for client_service schemas."""

import uuid

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
