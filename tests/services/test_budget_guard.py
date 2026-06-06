"""Unit tests for budget_guard service (ADR-0034, Issue #42)."""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.budget_guard import (
    check_provider_budget,
    get_provider_daily_summary,
    reconcile_actual_cost,
    release_reserved_budget,
)

_GET_SESSION = "vos_studio_mcp.services.budget_guard.get_privileged_session"
_GET_SETTINGS = "vos_studio_mcp.services.budget_guard.get_settings"

_PROVIDER = "higgsfield"
_CLIENT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_SPRINT_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_ESTIMATED_USD = 0.10


def _mock_settings(daily_limit: float = 0.0) -> MagicMock:
    s = MagicMock()
    s.provider_daily_limit_usd = daily_limit
    return s


def _make_session_ctx(today_spend: float = 0.0) -> MagicMock:
    """Return a mock async session context manager."""
    session = AsyncMock()

    # scalar_one returns today's sum
    scalar_result = MagicMock()
    scalar_result.scalar_one = MagicMock(return_value=today_spend)
    session.execute = AsyncMock(return_value=scalar_result)
    session.add = MagicMock()
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# check_provider_budget — no limit enforced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_limit_records_event_and_returns_id() -> None:
    """When daily_limit=0, the event should be recorded and a UUID returned."""
    ctx = _make_session_ctx(today_spend=0.0)

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings(daily_limit=0.0)),
        patch(_GET_SESSION, return_value=ctx),
    ):
        event_id = await check_provider_budget(
            _PROVIDER, _CLIENT_ID, _SPRINT_ID, _ESTIMATED_USD
        )

    assert isinstance(event_id, str)
    # Should be a valid UUID
    uuid.UUID(event_id)


@pytest.mark.asyncio
async def test_within_limit_records_event() -> None:
    """spend=0.5 + estimate=0.1 < limit=1.0 → succeeds and records event."""
    ctx = _make_session_ctx(today_spend=0.5)

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings(daily_limit=1.0)),
        patch(_GET_SESSION, return_value=ctx),
    ):
        event_id = await check_provider_budget(
            _PROVIDER, _CLIENT_ID, _SPRINT_ID, _ESTIMATED_USD
        )

    uuid.UUID(event_id)  # valid UUID


@pytest.mark.asyncio
async def test_exactly_at_limit_succeeds() -> None:
    """spend=0.90 + estimate=0.10 == limit=1.0 → should succeed (not exceed)."""
    ctx = _make_session_ctx(today_spend=0.90)

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings(daily_limit=1.0)),
        patch(_GET_SESSION, return_value=ctx),
    ):
        # 0.90 + 0.10 = 1.00, which is NOT > 1.0 so should succeed
        event_id = await check_provider_budget(
            _PROVIDER, _CLIENT_ID, _SPRINT_ID, _ESTIMATED_USD
        )
    uuid.UUID(event_id)


@pytest.mark.asyncio
async def test_quota_exceeded_raises() -> None:
    """spend=0.95 + estimate=0.10 > limit=1.0 → raises QUOTA_EXCEEDED."""
    ctx = _make_session_ctx(today_spend=0.95)

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings(daily_limit=1.0)),
        patch(_GET_SESSION, return_value=ctx),
        pytest.raises(VosError) as exc_info,
    ):
        await check_provider_budget(_PROVIDER, _CLIENT_ID, _SPRINT_ID, _ESTIMATED_USD)

    assert exc_info.value.error_code == ErrorCode.QUOTA_EXCEEDED
    assert "higgsfield" in exc_info.value.message


@pytest.mark.asyncio
async def test_quota_exceeded_does_not_record_event() -> None:
    """When quota is exceeded, no usage event should be written (session.add not called)."""
    ctx = _make_session_ctx(today_spend=0.95)
    session_mock: Any = ctx.__aenter__.return_value

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings(daily_limit=1.0)),
        patch(_GET_SESSION, return_value=ctx),
        pytest.raises(VosError),
    ):
        await check_provider_budget(_PROVIDER, _CLIENT_ID, _SPRINT_ID, _ESTIMATED_USD)

    session_mock.add.assert_not_called()
    session_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_large_budget_exceeded_message_contains_values() -> None:
    """Error message must include today's spend, limit, and estimate."""
    ctx = _make_session_ctx(today_spend=9.50)

    with (
        patch(_GET_SETTINGS, return_value=_mock_settings(daily_limit=10.0)),
        patch(_GET_SESSION, return_value=ctx),
        pytest.raises(VosError) as exc_info,
    ):
        await check_provider_budget(_PROVIDER, _CLIENT_ID, _SPRINT_ID, estimated_usd=1.00)

    msg = exc_info.value.message
    assert "9.50" in msg
    assert "10.00" in msg
    assert "1.00" in msg


# ---------------------------------------------------------------------------
# reconcile_actual_cost — billed-cost reconciliation on completion (ADR-0039 #5)
# ---------------------------------------------------------------------------


def _reconcile_ctx(*get_returns: object) -> tuple[MagicMock, AsyncMock]:
    """Privileged-session ctx whose .get() returns *get_returns* in call order
    (asset, then event, then sprint). Returns (ctx, session)."""
    session = AsyncMock()
    session.get = AsyncMock(side_effect=list(get_returns))
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, session


def _reconcile_asset() -> MagicMock:
    asset = MagicMock()
    asset.provider_usage_event_id = uuid.uuid4()
    asset.sprint_id = uuid.uuid4()
    return asset


@pytest.mark.asyncio
async def test_reconcile_affirms_estimate_when_provider_reports_no_cost() -> None:
    """No provider cost → actual = estimate, sprint spend unchanged (delta 0)."""
    asset = _reconcile_asset()
    event = MagicMock(estimated_usd=0.10, actual_usd=None)
    sprint = MagicMock(spent_usd=1.0)
    ctx, session = _reconcile_ctx(asset, event, sprint)

    with patch(_GET_SESSION, return_value=ctx):
        actual = await reconcile_actual_cost(str(uuid.uuid4()), None)

    assert actual == 0.10
    assert event.actual_usd == 0.10
    # delta is zero, so sprint is never fetched and spend is unchanged
    assert session.get.await_count == 2
    assert sprint.spent_usd == 1.0


@pytest.mark.asyncio
async def test_reconcile_corrects_sprint_when_billed_above_estimate() -> None:
    """Provider billed more than estimated → sprint spend rises by the delta."""
    asset = _reconcile_asset()
    event = MagicMock(estimated_usd=0.10, actual_usd=None)
    sprint = MagicMock(spent_usd=1.0)
    ctx, _session = _reconcile_ctx(asset, event, sprint)

    with patch(_GET_SESSION, return_value=ctx):
        actual = await reconcile_actual_cost(str(uuid.uuid4()), 0.18)

    assert actual == 0.18
    assert event.actual_usd == 0.18
    assert sprint.spent_usd == pytest.approx(1.08)  # +0.08 delta


@pytest.mark.asyncio
async def test_reconcile_refunds_sprint_when_billed_below_estimate() -> None:
    """Provider billed less than estimated → sprint spend drops by the delta."""
    asset = _reconcile_asset()
    event = MagicMock(estimated_usd=0.25, actual_usd=None)
    sprint = MagicMock(spent_usd=1.0)
    ctx, _session = _reconcile_ctx(asset, event, sprint)

    with patch(_GET_SESSION, return_value=ctx):
        actual = await reconcile_actual_cost(str(uuid.uuid4()), 0.10)

    assert actual == 0.10
    assert sprint.spent_usd == pytest.approx(0.85)  # -0.15 delta


@pytest.mark.asyncio
async def test_reconcile_never_drives_spend_negative() -> None:
    asset = _reconcile_asset()
    event = MagicMock(estimated_usd=0.10, actual_usd=None)
    sprint = MagicMock(spent_usd=0.05)  # less than the refund delta
    ctx, _session = _reconcile_ctx(asset, event, sprint)

    with patch(_GET_SESSION, return_value=ctx):
        await reconcile_actual_cost(str(uuid.uuid4()), 0.0)

    assert sprint.spent_usd == 0.0  # floored at zero, not negative


@pytest.mark.asyncio
async def test_reconcile_is_idempotent_when_already_reconciled() -> None:
    """If actual_usd is already set, the event was reconciled — do nothing."""
    asset = _reconcile_asset()
    event = MagicMock(estimated_usd=0.10, actual_usd=0.10)
    ctx, session = _reconcile_ctx(asset, event)

    with patch(_GET_SESSION, return_value=ctx):
        actual = await reconcile_actual_cost(str(uuid.uuid4()), 0.18)

    assert actual == 0.0
    assert session.get.await_count == 2  # asset + event; sprint never touched


@pytest.mark.asyncio
async def test_reconcile_returns_zero_when_no_usage_event_link() -> None:
    asset = MagicMock()
    asset.provider_usage_event_id = None
    ctx, session = _reconcile_ctx(asset)

    with patch(_GET_SESSION, return_value=ctx):
        actual = await reconcile_actual_cost(str(uuid.uuid4()), 0.10)

    assert actual == 0.0
    session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_swallows_errors_and_returns_zero() -> None:
    """Best-effort: a DB error must not propagate out of the poll workflow."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db gone"))
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_GET_SESSION, return_value=ctx):
        actual = await reconcile_actual_cost(str(uuid.uuid4()), 0.10)

    assert actual == 0.0


# ---------------------------------------------------------------------------
# get_provider_daily_summary
# ---------------------------------------------------------------------------


def _row(provider: str, total_est: float, total_act: float | None, count: int) -> MagicMock:
    r = MagicMock()
    r.provider = provider
    r.total_estimated = total_est
    r.total_actual = total_act
    r.event_count = count
    return r


@pytest.mark.asyncio
async def test_get_provider_daily_summary_returns_stats() -> None:
    rows = [
        _row("higgsfield", 1.5, 1.2, 10),
        _row("freepik", 0.5, None, 3),
    ]
    result_mock = MagicMock()
    result_mock.all = MagicMock(return_value=rows)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GET_SESSION, return_value=ctx),
    ):
        stats = await get_provider_daily_summary()

    assert len(stats) == 2
    higgsfield = next(s for s in stats if s.provider == "higgsfield")
    assert higgsfield.total_estimated_usd == 1.5
    assert higgsfield.total_actual_usd == 1.2
    assert higgsfield.event_count == 10

    freepik = next(s for s in stats if s.provider == "freepik")
    assert freepik.total_actual_usd is None


@pytest.mark.asyncio
async def test_get_provider_daily_summary_empty() -> None:
    result_mock = MagicMock()
    result_mock.all = MagicMock(return_value=[])

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GET_SESSION, return_value=ctx),
    ):
        stats = await get_provider_daily_summary()

    assert stats == []


@pytest.mark.asyncio
async def test_get_provider_daily_summary_provider_filter_used() -> None:
    """Passing a provider filter should not raise and should work as expected."""
    result_mock = MagicMock()
    result_mock.all = MagicMock(return_value=[_row("higgsfield", 0.2, None, 1)])

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GET_SESSION, return_value=ctx),
    ):
        stats = await get_provider_daily_summary(provider="higgsfield")

    assert len(stats) == 1
    assert stats[0].provider == "higgsfield"


# ---------------------------------------------------------------------------
# release_reserved_budget — failed/timed-out generation refunds (ADR-0039 #5)
# ---------------------------------------------------------------------------


def _release_ctx(*get_returns: object) -> tuple[MagicMock, AsyncMock]:
    """Privileged-session ctx whose .get() returns *get_returns* in call order
    (asset, then event, then sprint). Returns (ctx, session)."""
    session = AsyncMock()
    session.get = AsyncMock(side_effect=list(get_returns))
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, session


def _mock_asset(*, event_linked: bool = True) -> MagicMock:
    asset = MagicMock()
    asset.provider_usage_event_id = uuid.uuid4() if event_linked else None
    asset.sprint_id = uuid.uuid4()
    return asset


@pytest.mark.asyncio
async def test_release_returns_zero_when_no_usage_event_link() -> None:
    asset = _mock_asset(event_linked=False)
    ctx, session = _release_ctx(asset)

    with patch(_GET_SESSION, return_value=ctx):
        released = await release_reserved_budget(str(uuid.uuid4()))

    assert released == 0.0
    # only the asset was fetched; no event/sprint lookup
    session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_refunds_estimate_to_sprint() -> None:
    asset = _mock_asset()
    event = MagicMock(estimated_usd=0.25, actual_usd=None)
    sprint = MagicMock(spent_usd=1.0)
    ctx, session = _release_ctx(asset, event, sprint)

    with patch(_GET_SESSION, return_value=ctx):
        released = await release_reserved_budget(str(uuid.uuid4()))

    assert released == 0.25
    assert sprint.spent_usd == pytest.approx(0.75)
    # Marked reconciled so a second call is a no-op.
    assert event.actual_usd == 0.0
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_is_idempotent_when_already_reconciled() -> None:
    """If actual_usd is already set, the event was reconciled — do nothing."""
    asset = _mock_asset()
    event = MagicMock(estimated_usd=0.25, actual_usd=0.0)
    ctx, session = _release_ctx(asset, event)

    with patch(_GET_SESSION, return_value=ctx):
        released = await release_reserved_budget(str(uuid.uuid4()))

    assert released == 0.0
    # asset + event fetched, but sprint never (guarded before any refund)
    assert session.get.await_count == 2


@pytest.mark.asyncio
async def test_release_never_drives_spend_negative() -> None:
    asset = _mock_asset()
    event = MagicMock(estimated_usd=5.0, actual_usd=None)
    sprint = MagicMock(spent_usd=2.0)  # reserved more than current spend
    ctx, _session = _release_ctx(asset, event, sprint)

    with patch(_GET_SESSION, return_value=ctx):
        released = await release_reserved_budget(str(uuid.uuid4()))

    assert released == 5.0
    assert sprint.spent_usd == 0.0  # floored at zero, not negative


@pytest.mark.asyncio
async def test_release_swallows_errors_and_returns_zero() -> None:
    """Best-effort: a DB error must not propagate out of the poll workflow."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db gone"))
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_GET_SESSION, return_value=ctx):
        released = await release_reserved_budget(str(uuid.uuid4()))

    assert released == 0.0
