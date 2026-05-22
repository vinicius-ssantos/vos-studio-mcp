"""Unit tests for asset_service schemas."""

import uuid

from vos_studio_mcp.schemas.asset import AssetInput, AssetResponse


def _make_asset_input(**overrides):
    defaults = dict(
        sprint_id=str(uuid.uuid4()),
        provider="manual_dashboard",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://cdn.example.com/asset.png",
    )
    defaults.update(overrides)
    return AssetInput(**defaults)


def test_asset_input_optional_fields_default_none():
    data = _make_asset_input()
    assert data.preview_url is None
    assert data.width is None
    assert data.height is None
    assert data.format is None
    assert data.notes is None


def test_asset_input_with_dimensions():
    data = _make_asset_input(width=1920, height=1080, format="png")
    assert data.width == 1920
    assert data.height == 1080
    assert data.format == "png"


def test_asset_response_shape():
    resp = AssetResponse(
        status="registered",
        asset_id="asset-123",
        sprint_id="sprint-456",
        summary="Asset registered.",
        next_action="register_manual_asset",
    )
    assert resp.status == "registered"
    assert resp.next_action == "register_manual_asset"
