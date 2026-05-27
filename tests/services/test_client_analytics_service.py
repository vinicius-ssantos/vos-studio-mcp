"""Unit tests for client_analytics_service (ADR-0025)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SERVICE = "vos_studio_mcp.services.client_analytics_service"
_GUARD = f"{_SERVICE}.assert_owns_client"
_GET_SESSION = f"{_SERVICE}.get_session"
_SET_TENANT = f"{_SERVICE}.set_tenant_context"

_CLIENT_ID = "00000000-0000-0000-0000-000000000001"


def _mock_record(
    *,
    platform: str = "meta",
    ctr: float | None = 0.04,
    roas: float | None = 2.5,
    performance_label: str = "top_performer",
) -> MagicMock:
    r = MagicMock()
    r.asset_id = uuid.uuid4()
    r.platform = platform
    r.ctr = ctr
    r.roas = roas
    r.performance_label = performance_label
    r.impressions = 10_000
    r.recorded_at = datetime(2026, 5, 1, tzinfo=UTC)
    return r


def _session_ctx(sprint_count: int, records: list[MagicMock]) -> MagicMock:
    session = AsyncMock()

    # First execute → sprint count scalar
    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=sprint_count)
    session.execute = AsyncMock(return_value=count_result)

    # scalars() → performance records
    session.scalars = AsyncMock(return_value=iter(records))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_returns_ok_status() -> None:
    from vos_studio_mcp.services.client_analytics_service import get_client_performance_summary

    ctx = _session_ctx(sprint_count=2, records=[_mock_record()])
    with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT, new_callable=AsyncMock):
        result = await get_client_performance_summary(_CLIENT_ID)

    assert result.status == "ok"
    assert result.client_id == _CLIENT_ID
    assert result.total_sprints == 2


@pytest.mark.asyncio
async def test_avg_ctr_calculated_correctly() -> None:
    from vos_studio_mcp.services.client_analytics_service import get_client_performance_summary

    records = [
        _mock_record(ctr=0.02),
        _mock_record(ctr=0.06),
    ]
    ctx = _session_ctx(sprint_count=1, records=records)
    with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT, new_callable=AsyncMock):
        result = await get_client_performance_summary(_CLIENT_ID)

    assert result.avg_ctr == pytest.approx(0.04)


@pytest.mark.asyncio
async def test_top_platform_is_most_common_top_performer_platform() -> None:
    from vos_studio_mcp.services.client_analytics_service import get_client_performance_summary

    records = [
        _mock_record(platform="meta", performance_label="top_performer"),
        _mock_record(platform="meta", performance_label="top_performer"),
        _mock_record(platform="tiktok", performance_label="top_performer"),
    ]
    ctx = _session_ctx(sprint_count=3, records=records)
    with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT, new_callable=AsyncMock):
        result = await get_client_performance_summary(_CLIENT_ID)

    assert result.top_platform == "meta"


@pytest.mark.asyncio
async def test_no_records_returns_none_metrics() -> None:
    from vos_studio_mcp.services.client_analytics_service import get_client_performance_summary

    ctx = _session_ctx(sprint_count=0, records=[])
    with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT, new_callable=AsyncMock):
        result = await get_client_performance_summary(_CLIENT_ID)

    assert result.avg_ctr is None
    assert result.avg_roas is None
    assert result.top_platform is None
    assert result.total_records == 0
    assert result.next_action == "record_performance_metrics"


@pytest.mark.asyncio
async def test_top_performing_assets_capped_at_5() -> None:
    from vos_studio_mcp.services.client_analytics_service import get_client_performance_summary

    records = [_mock_record() for _ in range(8)]
    ctx = _session_ctx(sprint_count=2, records=records)
    with patch(_GUARD), patch(_GET_SESSION, return_value=ctx), patch(_SET_TENANT, new_callable=AsyncMock):
        result = await get_client_performance_summary(_CLIENT_ID)

    assert len(result.top_performing_assets) <= 5


@pytest.mark.asyncio
async def test_invalid_period_days_raises() -> None:
    from vos_studio_mcp.errors import ErrorCode, VosError
    from vos_studio_mcp.services.client_analytics_service import get_client_performance_summary

    with patch(_GUARD), pytest.raises(VosError) as exc:
        await get_client_performance_summary(_CLIENT_ID, period_days=0)

    assert exc.value.error_code == ErrorCode.INVALID_INPUT
