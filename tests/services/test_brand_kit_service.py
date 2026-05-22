"""Unit tests for brand_kit_service schemas."""

import uuid

import pytest
from pydantic import ValidationError

from vos_studio_mcp.schemas.brand_kit import (
    BrandIdentity,
    BrandKitInput,
    BrandKitResponse,
    BrandRestrictions,
    BrandVisualSystem,
)


def _make_brand_kit_input(**overrides):
    defaults = dict(
        client_id=str(uuid.uuid4()),
        name="Acme Brand Kit",
        identity=BrandIdentity(
            brand_name="Acme",
            target_audience="Professionals",
            positioning="Premium quality",
        ),
        visual=BrandVisualSystem(primary_colors=["#FF0000"]),
        restrictions=BrandRestrictions(),
    )
    defaults.update(overrides)
    return BrandKitInput(**defaults)


def test_brand_kit_input_requires_name():
    with pytest.raises(ValidationError):
        _make_brand_kit_input(name="")


def test_brand_kit_identity_defaults():
    identity = BrandIdentity(
        brand_name="Test",
        target_audience="All",
        positioning="Value",
    )
    assert identity.voice == []
    assert identity.tone == []
    assert identity.tagline is None


def test_brand_kit_restrictions_defaults():
    r = BrandRestrictions()
    assert r.forbidden_elements == []
    assert r.platform_rules == {}


def test_brand_kit_response_shape():
    resp = BrandKitResponse(
        status="created",
        brand_kit_id="bk-123",
        version="1.0",
        name="Acme Brand Kit",
        summary="Saved.",
        next_action="create_creative_sprint",
    )
    assert resp.version == "1.0"
    assert resp.next_action == "create_creative_sprint"


def test_brand_kit_identity_serialization():
    data = _make_brand_kit_input()
    dumped = data.identity.model_dump()
    assert dumped["brand_name"] == "Acme"
    assert "voice" in dumped
