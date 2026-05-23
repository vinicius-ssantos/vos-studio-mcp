"""Unit tests for performance_record_service (ADR-0025 Phase 2)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.performance_record import (
    DistributionContext,
    PerformanceMetrics,
    PerformanceRecordInput,
    TopPerformer,
)

_MODULE = "vos_studio_mcp.services.performance_record_service"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(**overrides) -> PerformanceRecordInput:
    defaults = dict(
        asset_id=str(uuid.uuid4()),
        distribution=DistributionContext(
            platform="meta",
            start_date="2026-05-01",
        ),
        metrics=PerformanceMetrics(
            impressions=50_000,
            clicks=1_250,
            ctr=0.025,
            roas=3.2,
        ),
        performance_label="top_performer",
        notes="Strong hook retention",
    )
    defaults.update(overrides)
    return PerformanceRecordInput(**defaults)


def _make_session_ctx(asset=None, sprint=None, record_id=None) -> MagicMock:
    """Return an async context manager mock for get_session."""
    _record_id = record_id or uuid.uuid4()

    asset_mock = asset or MagicMock()
    sprint_mock = sprint or MagicMock()

    if asset is None:
        asset_mock.sprint_id = uuid.uuid4()

    if sprint is None:
        sprint_mock.client_id = uuid.uuid4()
        sprint_mock.brand_kit_id = uuid.uuid4()

    session = AsyncMock()
    # .get returns the right ORM object by call order
    session.get = AsyncMock(side_effect=[asset_mock, sprint_mock])
    session.add = MagicMock()
    session.commit = AsyncMock()

    def _refresh_side_effect(obj):
        obj.id = _record_id

    session.refresh = AsyncMock(side_effect=_refresh_side_effect)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# create_performance_record — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_performance_record_returns_response() -> None:
    from vos_studio_mcp.services.performance_record_service import create_performance_record

    data = _make_input()
    record_id = uuid.uuid4()
    ctx = _make_session_ctx(record_id=record_id)

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
        patch(f"{_MODULE}.emit_audit_event", new_callable=AsyncMock),
    ):
        result = await create_performance_record(data)

    assert result.status == "recorded"
    assert result.record_id == str(record_id)
    assert result.asset_id == data.asset_id
    assert result.performance_label == "top_performer"
    assert result.next_action == "create_creative_sprint"
    assert "meta" in result.summary
    assert "top_performer" in result.summary


@pytest.mark.asyncio
async def test_create_performance_record_emits_audit_event() -> None:
    from vos_studio_mcp.services.performance_record_service import create_performance_record

    data = _make_input()
    ctx = _make_session_ctx()

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
        patch(f"{_MODULE}.emit_audit_event", new_callable=AsyncMock) as mock_emit,
    ):
        await create_performance_record(data)

    mock_emit.assert_awaited_once()
    call_kwargs = mock_emit.call_args.kwargs
    assert call_kwargs["action"] == "performance_recorded"
    assert call_kwargs["entity_type"] == "performance_record"


@pytest.mark.asyncio
async def test_create_performance_record_adds_orm_record_to_session() -> None:
    from vos_studio_mcp.services.performance_record_service import create_performance_record

    data = _make_input(performance_label="average")
    ctx = _make_session_ctx()
    session = ctx.__aenter__.return_value

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
        patch(f"{_MODULE}.emit_audit_event", new_callable=AsyncMock),
    ):
        await create_performance_record(data)

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.platform == "meta"
    assert added.performance_label == "average"
    assert added.start_date == "2026-05-01"
    assert added.impressions == 50_000
    assert added.ctr == pytest.approx(0.025)
    assert added.roas == pytest.approx(3.2)


# ---------------------------------------------------------------------------
# create_performance_record — asset/sprint not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_performance_record_asset_not_found() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.performance_record_service import create_performance_record

    data = _make_input()

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)  # asset not found
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        pytest.raises(VosError) as exc,
    ):
        await create_performance_record(data)

    assert exc.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_create_performance_record_sprint_not_found() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.performance_record_service import create_performance_record

    data = _make_input()
    asset_mock = MagicMock()
    asset_mock.sprint_id = uuid.uuid4()

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[asset_mock, None])  # sprint not found
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.bypass_rls", new_callable=AsyncMock),
        pytest.raises(VosError) as exc,
    ):
        await create_performance_record(data)

    assert exc.value.error_code == ErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# PerformanceRecordInput schema validation
# ---------------------------------------------------------------------------


def test_performance_record_input_valid_label():
    inp = _make_input(performance_label="top_performer")
    assert inp.performance_label == "top_performer"


def test_performance_record_input_invalid_label():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _make_input(performance_label="excellent")  # type: ignore[arg-type]


def test_performance_record_input_minimal():
    """Metrics and distribution extras are all optional."""
    inp = PerformanceRecordInput(
        asset_id=str(uuid.uuid4()),
        distribution=DistributionContext(platform="tiktok", start_date="2026-01-01"),
        metrics=PerformanceMetrics(),
        performance_label="underperformer",
    )
    assert inp.metrics.ctr is None
    assert inp.distribution.end_date is None
    assert inp.notes is None


# ---------------------------------------------------------------------------
# get_top_performers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_top_performers_returns_list() -> None:
    from vos_studio_mcp.services.performance_record_service import get_top_performers

    client_id = str(uuid.uuid4())
    brand_kit_id = str(uuid.uuid4())

    # Build fake ORM records
    def _fake_record(ctr: float, roas: float) -> MagicMock:
        r = MagicMock()
        r.asset_id = uuid.uuid4()
        r.platform = "meta"
        r.performance_label = "top_performer"
        r.ctr = ctr
        r.roas = roas
        r.impressions = 80_000
        r.recorded_at = None
        return r

    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[_fake_record(0.04, 4.1), _fake_record(0.03, 3.0)])

    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await get_top_performers(client_id, brand_kit_id)

    assert len(result) == 2
    assert all(isinstance(r, TopPerformer) for r in result)
    assert result[0].ctr == pytest.approx(0.04)
    assert result[0].platform == "meta"


@pytest.mark.asyncio
async def test_get_top_performers_returns_empty_list() -> None:
    from vos_studio_mcp.services.performance_record_service import get_top_performers

    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[])
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars_result)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(f"{_MODULE}.get_session", return_value=ctx),
        patch(f"{_MODULE}.set_tenant_context", new_callable=AsyncMock),
    ):
        result = await get_top_performers(str(uuid.uuid4()), str(uuid.uuid4()))

    assert result == []
