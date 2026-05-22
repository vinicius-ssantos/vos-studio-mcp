"""Unit tests for brand_kit_service — schemas and service functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# Service function tests — mocked AsyncSession
# ---------------------------------------------------------------------------

_GUARD = "vos_studio_mcp.services.brand_kit_service.assert_owns_client"
_GET_SESSION = "vos_studio_mcp.services.brand_kit_service.get_session"
_SET_TENANT = "vos_studio_mcp.services.brand_kit_service.set_tenant_context"


def _bk_ctx(fixed_id: uuid.UUID | None = None) -> MagicMock:
    _id = fixed_id or uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    def _refresh(obj: object) -> None:
        obj.id = _id  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_save_brand_kit_success() -> None:
    from vos_studio_mcp.services.brand_kit_service import save_brand_kit

    fixed_id = uuid.uuid4()
    ctx = _bk_ctx(fixed_id=fixed_id)

    data = _make_brand_kit_input(
        client_id="00000000-0000-0000-0000-000000000001",
        name="Acme Kit",
    )

    with (
        patch(_GUARD),
        patch(_GET_SESSION, return_value=ctx),
        patch(_SET_TENANT, new_callable=AsyncMock),
    ):
        result = await save_brand_kit(data)

    assert result.status == "created"
    assert result.brand_kit_id == str(fixed_id)
    assert result.version == "1.0"
    assert result.name == "Acme Kit"
    assert result.next_action == "create_creative_sprint"


@pytest.mark.asyncio
async def test_save_brand_kit_calls_guard() -> None:
    from vos_studio_mcp.errors import VosError
    from vos_studio_mcp.services.brand_kit_service import save_brand_kit

    data = _make_brand_kit_input(client_id="00000000-0000-0000-0000-000000000099")

    with (
        patch(_GUARD, side_effect=VosError("forbidden", "access denied")),
        patch(_GET_SESSION, return_value=_bk_ctx()),
        patch(_SET_TENANT, new_callable=AsyncMock),
        pytest.raises(VosError),
    ):
        await save_brand_kit(data)
