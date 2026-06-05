"""Unit tests for library_maintenance_service (ADR-0029)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SERVICE = "vos_studio_mcp.services.library_maintenance_service"
_GET_SESSION = f"{_SERVICE}.get_privileged_session"


def _mock_template(
    *,
    performance_tier: str = "experimental",
    derived_from_sprint_ids: list[str] | None = None,
    avg_ctr: float | None = None,
    usage_count: int = 0,
) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.performance_tier = performance_tier
    t.derived_from_sprint_ids = derived_from_sprint_ids or []
    t.avg_ctr = avg_ctr
    t.avg_roas = None
    t.usage_count = usage_count
    return t


def _mock_perf_record(*, sprint_id: uuid.UUID, ctr: float | None = None, roas: float | None = None) -> MagicMock:
    r = MagicMock()
    r.sprint_id = sprint_id
    r.ctr = ctr
    r.roas = roas
    return r


def _session_ctx(templates: list[MagicMock], records: list[MagicMock]) -> MagicMock:
    session = AsyncMock()

    # scalars() — first call returns templates iter, second returns records iter
    session.scalars = AsyncMock(side_effect=[iter(templates), iter(records)])
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_refresh_promotes_to_tested() -> None:
    """A template with 5+ records and avg_ctr ≥ 0.03 should become 'tested'."""
    from vos_studio_mcp.services.library_maintenance_service import refresh_library_tiers

    sprint_id = uuid.uuid4()
    template = _mock_template(derived_from_sprint_ids=[str(sprint_id)])
    records = [_mock_perf_record(sprint_id=sprint_id, ctr=0.04) for _ in range(5)]

    ctx = _session_ctx([template], records)
    with patch(_GET_SESSION, return_value=ctx):
        result = await refresh_library_tiers()

    assert template.performance_tier == "tested"
    assert result["promoted"] == 1
    assert result["updated"] == 1


@pytest.mark.asyncio
async def test_refresh_promotes_to_top_performer() -> None:
    """10+ records with avg_ctr ≥ 0.05 → top_performer."""
    from vos_studio_mcp.services.library_maintenance_service import refresh_library_tiers

    sprint_id = uuid.uuid4()
    template = _mock_template(derived_from_sprint_ids=[str(sprint_id)])
    records = [_mock_perf_record(sprint_id=sprint_id, ctr=0.06) for _ in range(10)]

    ctx = _session_ctx([template], records)
    with patch(_GET_SESSION, return_value=ctx):
        result = await refresh_library_tiers()

    assert template.performance_tier == "top_performer"
    assert result["promoted"] == 1


@pytest.mark.asyncio
async def test_refresh_stays_experimental_with_low_ctr() -> None:
    """5 records but avg_ctr < 0.03 → stays experimental."""
    from vos_studio_mcp.services.library_maintenance_service import refresh_library_tiers

    sprint_id = uuid.uuid4()
    template = _mock_template(derived_from_sprint_ids=[str(sprint_id)])
    records = [_mock_perf_record(sprint_id=sprint_id, ctr=0.01) for _ in range(5)]

    ctx = _session_ctx([template], records)
    with patch(_GET_SESSION, return_value=ctx):
        result = await refresh_library_tiers()

    assert template.performance_tier == "experimental"
    assert result["promoted"] == 0


@pytest.mark.asyncio
async def test_refresh_demotes_when_data_drops() -> None:
    """A 'tested' template with only 2 new records should be demoted to experimental."""
    from vos_studio_mcp.services.library_maintenance_service import refresh_library_tiers

    sprint_id = uuid.uuid4()
    template = _mock_template(
        performance_tier="tested",
        derived_from_sprint_ids=[str(sprint_id)],
    )
    records = [_mock_perf_record(sprint_id=sprint_id, ctr=0.04) for _ in range(2)]

    ctx = _session_ctx([template], records)
    with patch(_GET_SESSION, return_value=ctx):
        result = await refresh_library_tiers()

    assert template.performance_tier == "experimental"
    assert result["promoted"] == 1  # tier changed (even if downgrade)


@pytest.mark.asyncio
async def test_refresh_no_templates_returns_zero() -> None:
    from vos_studio_mcp.services.library_maintenance_service import refresh_library_tiers

    session = AsyncMock()
    session.scalars = AsyncMock(return_value=iter([]))
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_GET_SESSION, return_value=ctx):
        result = await refresh_library_tiers()

    assert result == {"updated": 0, "promoted": 0}


@pytest.mark.asyncio
async def test_refresh_updates_avg_ctr_and_roas() -> None:
    """avg_ctr and avg_roas should be calculated and written to the template."""
    from vos_studio_mcp.services.library_maintenance_service import refresh_library_tiers

    sprint_id = uuid.uuid4()
    template = _mock_template(derived_from_sprint_ids=[str(sprint_id)])
    records = [
        _mock_perf_record(sprint_id=sprint_id, ctr=0.04, roas=2.0),
        _mock_perf_record(sprint_id=sprint_id, ctr=0.06, roas=3.0),
    ]

    ctx = _session_ctx([template], records)
    with patch(_GET_SESSION, return_value=ctx):
        await refresh_library_tiers()

    assert template.avg_ctr == pytest.approx(0.05)
    assert template.avg_roas == pytest.approx(2.5)
    assert template.usage_count == 2
