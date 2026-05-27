"""Unit tests for asset_service — schemas and service functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# Service function tests — mocked AsyncSession
# ---------------------------------------------------------------------------

_GET_SESSION = "vos_studio_mcp.services.asset_service.get_session"


def _asset_session_ctx(fixed_id: uuid.UUID | None = None, asset_list: list | None = None) -> MagicMock:
    _id = fixed_id or uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", _id))

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all = MagicMock(return_value=asset_list or [])
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    session.execute = AsyncMock(return_value=mock_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_register_manual_asset_success() -> None:
    from vos_studio_mcp.services.asset_service import register_manual_asset

    fixed_id = uuid.uuid4()
    sprint_id = str(uuid.uuid4())
    ctx = _asset_session_ctx(fixed_id=fixed_id)

    data = AssetInput(
        sprint_id=sprint_id,
        provider="manual_dashboard",
        prompt_version="v1",
        preset_version="p1",
        storage_url="https://cdn.example.com/asset.png",
    )

    with patch(_GET_SESSION, return_value=ctx):
        result = await register_manual_asset(data)

    assert result.status == "registered"
    assert result.asset_id == str(fixed_id)
    assert result.sprint_id == sprint_id
    assert result.next_action == "register_manual_asset"


@pytest.mark.asyncio
async def test_list_sprint_assets_empty() -> None:
    from vos_studio_mcp.services.asset_service import list_sprint_assets

    sprint_id = str(uuid.uuid4())
    ctx = _asset_session_ctx(asset_list=[])

    with patch(_GET_SESSION, return_value=ctx):
        result = await list_sprint_assets(sprint_id)

    assert result.status == "ok"
    assert result.total == 0
    assert result.assets == []
    assert result.sprint_id == sprint_id


@pytest.mark.asyncio
async def test_list_sprint_assets_returns_items() -> None:
    from vos_studio_mcp.services.asset_service import list_sprint_assets

    asset1 = MagicMock()
    asset1.id = uuid.uuid4()
    asset1.provider = "manual_dashboard"
    asset1.prompt_version = "v1"
    asset1.preset_version = "p1"
    asset1.storage_url = "https://cdn.example.com/a1.png"
    asset1.preview_url = None
    asset1.width = 1920
    asset1.height = 1080
    asset1.format = "png"
    asset1.created_at = None
    # Stage / lineage fields (Issue #53)
    asset1.asset_stage = None
    asset1.asset_kind = "manual"
    asset1.source_asset_id = None
    asset1.approved_as_reference = False
    asset1.is_final_delivery = False
    asset1.generation_status = "manual"
    asset1.storage_status = "not_required"
    asset1.qa_status = None

    ctx = _asset_session_ctx(asset_list=[asset1])
    sprint_id = str(uuid.uuid4())

    with patch(_GET_SESSION, return_value=ctx):
        result = await list_sprint_assets(sprint_id)

    assert result.total == 1
    assert result.assets[0].asset_id == str(asset1.id)
    assert result.assets[0].provider == "manual_dashboard"
    assert result.assets[0].width == 1920


# ---------------------------------------------------------------------------
# list_sprint_assets — filters
# ---------------------------------------------------------------------------


def _mock_asset_full(
    asset_stage: str | None = None,
    qa_status: str | None = None,
) -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.provider = "manual_dashboard"
    a.prompt_version = "v1"
    a.preset_version = "p1"
    a.storage_url = "https://cdn.example.com/a.mp4"
    a.preview_url = None
    a.width = 1920
    a.height = 1080
    a.format = "mp4"
    a.created_at = None
    a.asset_stage = asset_stage
    a.asset_kind = "manual"
    a.source_asset_id = None
    a.approved_as_reference = False
    a.is_final_delivery = False
    a.generation_status = "manual"
    a.storage_status = "not_required"
    a.qa_status = qa_status
    return a


@pytest.mark.asyncio
async def test_list_sprint_assets_filter_by_asset_stage() -> None:
    from vos_studio_mcp.schemas.asset import AssetListFilters
    from vos_studio_mcp.services.asset_service import list_sprint_assets

    assets = [_mock_asset_full(asset_stage="stage_c", qa_status="approved")]
    ctx = _asset_session_ctx(asset_list=assets)
    sprint_id = str(uuid.uuid4())
    filters = AssetListFilters(asset_stage="stage_c")

    with patch(_GET_SESSION, return_value=ctx):
        result = await list_sprint_assets(sprint_id, filters)

    assert result.total == 1
    assert result.assets[0].asset_stage == "stage_c"


@pytest.mark.asyncio
async def test_list_sprint_assets_filter_by_qa_status() -> None:
    from vos_studio_mcp.schemas.asset import AssetListFilters
    from vos_studio_mcp.services.asset_service import list_sprint_assets

    assets = [_mock_asset_full(qa_status="approved")]
    ctx = _asset_session_ctx(asset_list=assets)
    sprint_id = str(uuid.uuid4())
    filters = AssetListFilters(qa_status="approved")

    with patch(_GET_SESSION, return_value=ctx):
        result = await list_sprint_assets(sprint_id, filters)

    assert result.total == 1
    assert result.assets[0].qa_status == "approved"


@pytest.mark.asyncio
async def test_list_sprint_assets_no_filters_returns_all() -> None:
    from vos_studio_mcp.services.asset_service import list_sprint_assets

    assets = [
        _mock_asset_full(asset_stage="stage_b", qa_status=None),
        _mock_asset_full(asset_stage="stage_c", qa_status="approved"),
    ]
    ctx = _asset_session_ctx(asset_list=assets)
    sprint_id = str(uuid.uuid4())

    with patch(_GET_SESSION, return_value=ctx):
        result = await list_sprint_assets(sprint_id)

    assert result.total == 2
