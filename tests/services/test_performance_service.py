"""Unit tests for performance schemas, error types, and service functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from vos_studio_mcp.errors import ErrorCode, VosError  # noqa: E402
from vos_studio_mcp.schemas.performance import PerformanceInput, PerformanceResponse
from vos_studio_mcp.schemas.sprint import CloseSprintInput, CloseSprintResponse

# --- VosError ---

def test_vos_error_stores_error_code():
    err = VosError(ErrorCode.NOT_FOUND, "sprint xyz not found")
    assert err.error_code == ErrorCode.NOT_FOUND
    assert "not_found" in str(err)
    assert "sprint xyz" in str(err)


def test_vos_error_is_exception():
    err = VosError(ErrorCode.SPRINT_CLOSED, "sprint is closed")
    with pytest.raises(VosError, match="sprint is closed"):
        raise err


def test_error_codes_are_strings():
    assert ErrorCode.NOT_FOUND == "not_found"
    assert ErrorCode.SPRINT_CLOSED == "sprint_closed"
    assert ErrorCode.BUDGET_EXCEEDED == "budget_exceeded"
    assert ErrorCode.INVALID_INPUT == "invalid_input"
    assert ErrorCode.PROVIDER_ERROR == "provider_error"


# --- PerformanceInput ---

def test_performance_input_score_bounds():
    with pytest.raises(ValidationError):
        PerformanceInput(asset_id="a", sprint_id="s", score=0)
    with pytest.raises(ValidationError):
        PerformanceInput(asset_id="a", sprint_id="s", score=6)


def test_performance_input_valid():
    data = PerformanceInput(
        asset_id="a1",
        sprint_id="s1",
        score=5,
        label="top_performer",
        hook_label="bold headline",
        angle_label="summer vibes",
    )
    assert data.score == 5
    assert data.label == "top_performer"
    assert data.hook_label == "bold headline"


def test_performance_input_label_default():
    data = PerformanceInput(asset_id="a", sprint_id="s", score=3)
    assert data.label == "neutral"


def test_performance_input_invalid_label():
    with pytest.raises(ValidationError):
        PerformanceInput(asset_id="a", sprint_id="s", score=3, label="unknown")  # type: ignore[arg-type]


def test_performance_response_shape():
    resp = PerformanceResponse(
        status="recorded",
        asset_id="asset-1",
        brand_kit_updated=True,
        summary="Asset recorded as top_performer (score 5/5). Brand kit memory updated.",
        next_action="record_asset_performance",
    )
    assert resp.brand_kit_updated is True
    assert resp.next_action == "record_asset_performance"


# --- CloseSprintInput ---

def test_close_sprint_input_optional_reason():
    data = CloseSprintInput(sprint_id="sprint-1")
    assert data.reason is None


def test_close_sprint_input_with_reason():
    data = CloseSprintInput(sprint_id="sprint-1", reason="campaign ended")
    assert data.reason == "campaign ended"


def test_close_sprint_response_shape():
    resp = CloseSprintResponse(
        status="closed",
        sprint_id="sprint-1",
        sprint_status="closed",
        summary="Sprint closed.",
        next_action="record_asset_performance",
    )
    assert resp.sprint_status == "closed"
    assert resp.next_action == "record_asset_performance"


# ---------------------------------------------------------------------------
# Service function tests — mocked AsyncSession
# ---------------------------------------------------------------------------

_GET_SESSION = "vos_studio_mcp.services.performance_service.get_session"


def _perf_session_ctx(
    asset: object = None,
    sprint: object = None,
    brand_kit: object = None,
) -> MagicMock:
    from db.models import Asset as AssetModel
    from db.models import BrandKit as BrandKitModel
    from db.models import Sprint as SprintModel

    def _get_side_effect(model_class: type, pk: object) -> object:
        if model_class is AssetModel:
            return asset
        if model_class is SprintModel:
            return sprint
        if model_class is BrandKitModel:
            return brand_kit
        return None

    session = AsyncMock()
    session.get = AsyncMock(side_effect=_get_side_effect)
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_asset(sprint_id: uuid.UUID) -> MagicMock:
    a = MagicMock()
    a.sprint_id = sprint_id
    a.performance_score = None
    a.performance_label = None
    a.performance_notes = None
    a.variant_id = None
    return a


def _mock_sprint(brand_kit_id: uuid.UUID | None = None) -> MagicMock:
    s = MagicMock()
    s.brand_kit_id = brand_kit_id or uuid.uuid4()
    return s


def _mock_brand_kit(memory: dict | None = None) -> MagicMock:
    bk = MagicMock()
    bk.performance_memory = dict(memory or {})
    return bk


@pytest.mark.asyncio
async def test_record_asset_performance_neutral() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    sprint_id = uuid.uuid4()
    asset = _mock_asset(sprint_id=sprint_id)
    sprint = _mock_sprint()
    bk = _mock_brand_kit()

    ctx = _perf_session_ctx(asset=asset, sprint=sprint, brand_kit=bk)
    data = PerformanceInput(asset_id=str(uuid.uuid4()), sprint_id=str(sprint_id), score=3)

    with patch(_GET_SESSION, return_value=ctx):
        result = await record_asset_performance(data)

    assert result.status == "recorded"
    assert result.brand_kit_updated is True


@pytest.mark.asyncio
async def test_record_asset_performance_top_performer_updates_memory() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    sprint_id = uuid.uuid4()
    asset = _mock_asset(sprint_id=sprint_id)
    sprint = _mock_sprint()
    bk = _mock_brand_kit(memory={"proven_angles": [], "proven_hooks": []})

    ctx = _perf_session_ctx(asset=asset, sprint=sprint, brand_kit=bk)
    data = PerformanceInput(
        asset_id=str(uuid.uuid4()),
        sprint_id=str(sprint_id),
        score=5,
        label="top_performer",
        angle_label="summer vibes",
        hook_label="bold headline",
    )

    with patch(_GET_SESSION, return_value=ctx):
        result = await record_asset_performance(data)

    assert result.brand_kit_updated is True
    assert "summer vibes" in bk.performance_memory["proven_angles"]
    assert "bold headline" in bk.performance_memory["proven_hooks"]


@pytest.mark.asyncio
async def test_record_asset_performance_failed_updates_failed_approaches() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    sprint_id = uuid.uuid4()
    asset = _mock_asset(sprint_id=sprint_id)
    sprint = _mock_sprint()
    bk = _mock_brand_kit()

    ctx = _perf_session_ctx(asset=asset, sprint=sprint, brand_kit=bk)
    data = PerformanceInput(
        asset_id=str(uuid.uuid4()),
        sprint_id=str(sprint_id),
        score=1,
        label="failed",
        notes="Too generic",
    )

    with patch(_GET_SESSION, return_value=ctx):
        result = await record_asset_performance(data)

    assert result.brand_kit_updated is True
    assert "Too generic" in bk.performance_memory["failed_approaches"]


@pytest.mark.asyncio
async def test_record_asset_performance_asset_not_found() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    ctx = _perf_session_ctx(asset=None)
    data = PerformanceInput(asset_id=str(uuid.uuid4()), sprint_id=str(uuid.uuid4()), score=3)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await record_asset_performance(data)

    assert exc.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_record_asset_performance_wrong_sprint() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    asset = _mock_asset(sprint_id=uuid.uuid4())  # different sprint
    ctx = _perf_session_ctx(asset=asset)
    data = PerformanceInput(asset_id=str(uuid.uuid4()), sprint_id=str(uuid.uuid4()), score=3)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await record_asset_performance(data)

    assert exc.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_record_asset_performance_sprint_not_found() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    sprint_id = uuid.uuid4()
    asset = _mock_asset(sprint_id=sprint_id)
    ctx = _perf_session_ctx(asset=asset, sprint=None)
    data = PerformanceInput(asset_id=str(uuid.uuid4()), sprint_id=str(sprint_id), score=3)

    with patch(_GET_SESSION, return_value=ctx), pytest.raises(VosError) as exc:
        await record_asset_performance(data)

    assert exc.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_record_asset_performance_no_brand_kit() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    sprint_id = uuid.uuid4()
    asset = _mock_asset(sprint_id=sprint_id)
    sprint = _mock_sprint()
    ctx = _perf_session_ctx(asset=asset, sprint=sprint, brand_kit=None)
    data = PerformanceInput(
        asset_id=str(uuid.uuid4()),
        sprint_id=str(sprint_id),
        score=5,
        label="top_performer",
        angle_label="bold angle",
    )

    with patch(_GET_SESSION, return_value=ctx):
        result = await record_asset_performance(data)

    assert result.brand_kit_updated is False


@pytest.mark.asyncio
async def test_record_asset_performance_top_performer_deduplicates_memory() -> None:
    from vos_studio_mcp.services.performance_service import record_asset_performance

    sprint_id = uuid.uuid4()
    asset = _mock_asset(sprint_id=sprint_id)
    sprint = _mock_sprint()
    bk = _mock_brand_kit(memory={"proven_angles": ["summer vibes"]})

    ctx = _perf_session_ctx(asset=asset, sprint=sprint, brand_kit=bk)
    data = PerformanceInput(
        asset_id=str(uuid.uuid4()),
        sprint_id=str(sprint_id),
        score=5,
        label="top_performer",
        angle_label="summer vibes",
    )

    with patch(_GET_SESSION, return_value=ctx):
        await record_asset_performance(data)

    assert bk.performance_memory["proven_angles"].count("summer vibes") == 1


@pytest.mark.asyncio
async def test_record_asset_performance_sets_variant_id() -> None:
    """Passing variant_id in input should set asset.variant_id (line 39)."""
    import uuid

    sprint_id = uuid.uuid4()
    variant_id = str(uuid.uuid4())
    asset = _mock_asset(sprint_id=sprint_id)
    sprint = _mock_sprint()
    bk = _mock_brand_kit()

    ctx = _perf_session_ctx(asset=asset, sprint=sprint, brand_kit=bk)
    data = PerformanceInput(
        asset_id=str(uuid.uuid4()),
        sprint_id=str(sprint_id),
        score=3,
        variant_id=variant_id,
    )

    with patch(_GET_SESSION, return_value=ctx):
        from vos_studio_mcp.services.performance_service import record_asset_performance
        result = await record_asset_performance(data)

    assert result.status == "recorded"
    assert asset.variant_id == uuid.UUID(variant_id)
