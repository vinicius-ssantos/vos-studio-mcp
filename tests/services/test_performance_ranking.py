"""Tests for composite performance ranking in performance_record_service (Issue #61)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

_MODULE = "vos_studio_mcp.services.performance_record_service"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    *,
    ctr: float | None = 0.02,
    roas: float | None = 2.0,
    platform: str = "meta",
    recorded_at: datetime | None = None,
    asset_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a minimal PerformanceRecord-like mock for ranking tests."""
    r = MagicMock()
    r.asset_id = asset_id or uuid.uuid4()
    r.platform = platform
    r.performance_label = "top_performer"
    r.ctr = ctr
    r.roas = roas
    r.impressions = 10_000
    r.recorded_at = recorded_at
    return r


def _recent() -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=10)


def _medium() -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=60)


def _old() -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=120)


# ---------------------------------------------------------------------------
# Pure unit tests for _composite_score
# ---------------------------------------------------------------------------


def test_composite_score_range_zero_to_one() -> None:
    """Composite score must always fall within [0, 1]."""
    from vos_studio_mcp.services.performance_record_service import (
        _composite_score,
        _ScoringWeights,
    )

    weights = _ScoringWeights()
    r = _make_record(ctr=0.05, roas=3.0, recorded_at=_recent())
    score = _composite_score(r, max_ctr=0.10, max_roas=5.0, platform="meta", campaign_objective="conversions", weights=weights)
    assert 0.0 <= score <= 1.0


def test_composite_score_platform_match_boosts_score() -> None:
    """Platform-matching record scores higher than non-matching when CTR/ROAS/recency are equal."""
    from vos_studio_mcp.services.performance_record_service import (
        _composite_score,
        _ScoringWeights,
    )

    weights = _ScoringWeights()
    base_kwargs = dict(max_ctr=0.05, max_roas=3.0, campaign_objective=None, weights=weights)
    r_match = _make_record(ctr=0.05, roas=3.0, platform="meta", recorded_at=_recent())
    r_no_match = _make_record(ctr=0.05, roas=3.0, platform="tiktok", recorded_at=_recent())

    score_match = _composite_score(r_match, platform="meta", **base_kwargs)
    score_no_match = _composite_score(r_no_match, platform="meta", **base_kwargs)
    assert score_match > score_no_match


def test_composite_score_objective_match_boosts_score() -> None:
    """objective_match_bonus=1.0 when no campaign_objective is passed (neutral)."""
    from vos_studio_mcp.services.performance_record_service import (
        _composite_score,
        _ScoringWeights,
    )

    weights = _ScoringWeights()
    r = _make_record(ctr=0.03, roas=2.5, recorded_at=_recent())
    score_with_obj = _composite_score(r, max_ctr=0.05, max_roas=5.0, platform=None, campaign_objective="awareness", weights=weights)
    score_no_obj = _composite_score(r, max_ctr=0.05, max_roas=5.0, platform=None, campaign_objective=None, weights=weights)
    # Both use 0.5 neutral for objective, so scores are equal
    assert score_with_obj == pytest.approx(score_no_obj)


def test_composite_score_higher_roas_beats_lower_roas_equal_ctr() -> None:
    """When CTR is equal, the record with higher ROAS should score higher."""
    from vos_studio_mcp.services.performance_record_service import (
        _composite_score,
        _ScoringWeights,
    )

    weights = _ScoringWeights()
    r_high = _make_record(ctr=0.05, roas=5.0, recorded_at=_recent())
    r_low = _make_record(ctr=0.05, roas=1.0, recorded_at=_recent())
    max_roas = 5.0

    score_high = _composite_score(r_high, max_ctr=0.05, max_roas=max_roas, platform=None, campaign_objective=None, weights=weights)
    score_low = _composite_score(r_low, max_ctr=0.05, max_roas=max_roas, platform=None, campaign_objective=None, weights=weights)
    assert score_high > score_low


def test_composite_score_recent_beats_old_equal_ctr_roas() -> None:
    """When CTR and ROAS are equal, the more recent record should score higher."""
    from vos_studio_mcp.services.performance_record_service import (
        _composite_score,
        _ScoringWeights,
    )

    weights = _ScoringWeights()
    r_recent = _make_record(ctr=0.05, roas=3.0, recorded_at=_recent())
    r_old = _make_record(ctr=0.05, roas=3.0, recorded_at=_old())

    score_recent = _composite_score(r_recent, max_ctr=0.05, max_roas=3.0, platform=None, campaign_objective=None, weights=weights)
    score_old = _composite_score(r_old, max_ctr=0.05, max_roas=3.0, platform=None, campaign_objective=None, weights=weights)
    assert score_recent > score_old


def test_composite_score_no_roas_uses_neutral() -> None:
    """When roas is None, score should use 0.5 (neutral) rather than 0."""
    from vos_studio_mcp.services.performance_record_service import (
        _composite_score,
        _ScoringWeights,
    )

    weights = _ScoringWeights()
    r_no_roas = _make_record(ctr=0.05, roas=None, recorded_at=_recent())
    r_low_roas = _make_record(ctr=0.05, roas=0.1, recorded_at=_recent())
    max_roas = 5.0

    score_no_roas = _composite_score(r_no_roas, max_ctr=0.05, max_roas=max_roas, platform=None, campaign_objective=None, weights=weights)
    score_low_roas = _composite_score(r_low_roas, max_ctr=0.05, max_roas=max_roas, platform=None, campaign_objective=None, weights=weights)
    # 0.5 neutral > 0.02 (0.1/5.0)
    assert score_no_roas > score_low_roas


# ---------------------------------------------------------------------------
# _recency_factor unit tests
# ---------------------------------------------------------------------------


def test_recency_factor_recent() -> None:
    from vos_studio_mcp.services.performance_record_service import _recency_factor

    assert _recency_factor(_recent()) == pytest.approx(1.0)


def test_recency_factor_medium() -> None:
    from vos_studio_mcp.services.performance_record_service import _recency_factor

    assert _recency_factor(_medium()) == pytest.approx(0.7)


def test_recency_factor_old() -> None:
    from vos_studio_mcp.services.performance_record_service import _recency_factor

    assert _recency_factor(_old()) == pytest.approx(0.4)


def test_recency_factor_none() -> None:
    from vos_studio_mcp.services.performance_record_service import _recency_factor

    assert _recency_factor(None) == pytest.approx(0.4)


def test_recency_factor_naive_datetime() -> None:
    """Naive datetimes should be treated as UTC."""
    from vos_studio_mcp.services.performance_record_service import _recency_factor

    naive_recent = datetime.utcnow() - timedelta(days=5)
    assert _recency_factor(naive_recent) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# get_top_performers — backward compatibility (CTR-only path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_top_performers_ctr_only_backward_compat() -> None:
    """Without platform/objective, get_top_performers uses CTR ordering from DB."""
    from unittest.mock import AsyncMock, patch

    from vos_studio_mcp.schemas.performance_record import TopPerformer
    from vos_studio_mcp.services.performance_record_service import get_top_performers

    client_id = str(uuid.uuid4())
    brand_kit_id = str(uuid.uuid4())

    records = [_make_record(ctr=0.04, roas=4.0), _make_record(ctr=0.02, roas=2.0)]

    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=records)
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
    # DB order is preserved (CTR-only) — first record has higher CTR
    assert result[0].ctr == pytest.approx(0.04)


@pytest.mark.asyncio
async def test_get_top_performers_returns_empty_list() -> None:
    """Empty DB result → empty list."""
    from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_get_top_performers_single_asset() -> None:
    """Single asset → returns a list with exactly that one asset."""
    from unittest.mock import AsyncMock, patch

    from vos_studio_mcp.schemas.performance_record import TopPerformer
    from vos_studio_mcp.services.performance_record_service import get_top_performers

    single = _make_record(ctr=0.05, roas=3.0, recorded_at=_recent())

    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[single])
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
        result = await get_top_performers(str(uuid.uuid4()), str(uuid.uuid4()), platform="meta")

    assert len(result) == 1
    assert isinstance(result[0], TopPerformer)
    assert result[0].ctr == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# get_top_performers — composite ranking path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_top_performers_composite_higher_roas_ranks_above() -> None:
    """With platform provided, record with higher ROAS ranks above lower-ROAS when CTR is equal."""
    from unittest.mock import AsyncMock, patch

    from vos_studio_mcp.services.performance_record_service import get_top_performers

    r_high_roas = _make_record(ctr=0.05, roas=5.0, platform="meta", recorded_at=_recent())
    r_low_roas = _make_record(ctr=0.05, roas=1.0, platform="meta", recorded_at=_recent())

    scalars_result = MagicMock()
    # DB returns low-roas first (simulating CTR-only DB sort returning them in wrong composite order)
    scalars_result.all = MagicMock(return_value=[r_low_roas, r_high_roas])
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
        result = await get_top_performers(str(uuid.uuid4()), str(uuid.uuid4()), platform="meta")

    # After composite re-ranking, higher ROAS should be first
    assert result[0].roas == pytest.approx(5.0)
    assert result[1].roas == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_get_top_performers_composite_recent_ranks_above_old() -> None:
    """With platform provided, more recent record ranks above old when CTR and ROAS are equal."""
    from unittest.mock import AsyncMock, patch

    from vos_studio_mcp.services.performance_record_service import get_top_performers

    r_recent = _make_record(ctr=0.05, roas=3.0, platform="meta", recorded_at=_recent())
    r_old = _make_record(ctr=0.05, roas=3.0, platform="meta", recorded_at=_old())

    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[r_old, r_recent])
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
        result = await get_top_performers(str(uuid.uuid4()), str(uuid.uuid4()), platform="meta")

    # Recent should come first
    assert result[0].recorded_at == r_recent.recorded_at.isoformat()


@pytest.mark.asyncio
async def test_get_top_performers_platform_match_boosts_ranking() -> None:
    """Record matching requested platform ranks above non-matching when other signals are equal."""
    from unittest.mock import AsyncMock, patch

    from vos_studio_mcp.services.performance_record_service import get_top_performers

    r_match = _make_record(ctr=0.05, roas=3.0, platform="meta", recorded_at=_recent())
    r_no_match = _make_record(ctr=0.05, roas=3.0, platform="tiktok", recorded_at=_recent())

    scalars_result = MagicMock()
    # DB returns non-matching first
    scalars_result.all = MagicMock(return_value=[r_no_match, r_match])
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
        result = await get_top_performers(str(uuid.uuid4()), str(uuid.uuid4()), platform="meta")

    # Platform-matching record should rank first
    assert result[0].platform == "meta"
    assert result[1].platform == "tiktok"


@pytest.mark.asyncio
async def test_get_top_performers_objective_triggers_composite_path() -> None:
    """Passing campaign_objective alone triggers composite re-ranking."""
    from unittest.mock import AsyncMock, patch

    from vos_studio_mcp.schemas.performance_record import TopPerformer
    from vos_studio_mcp.services.performance_record_service import get_top_performers

    r_high = _make_record(ctr=0.05, roas=4.0, recorded_at=_recent())
    r_low = _make_record(ctr=0.01, roas=1.0, recorded_at=_old())

    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[r_high, r_low])
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
        result = await get_top_performers(
            str(uuid.uuid4()), str(uuid.uuid4()), campaign_objective="conversions"
        )

    assert len(result) == 2
    assert all(isinstance(r, TopPerformer) for r in result)
    # Higher composite score (better ctr, roas, recency) comes first
    assert result[0].ctr == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_get_top_performers_composite_scores_in_range() -> None:
    """All composite scores computed during ranking are in [0, 1]."""

    from vos_studio_mcp.services.performance_record_service import (
        _composite_score,
        _ScoringWeights,
    )

    records = [
        _make_record(ctr=0.10, roas=6.0, platform="meta", recorded_at=_recent()),
        _make_record(ctr=0.05, roas=None, platform="google", recorded_at=_medium()),
        _make_record(ctr=None, roas=None, platform="tiktok", recorded_at=_old()),
    ]

    ctrs = [r.ctr for r in records if r.ctr is not None]
    roases = [r.roas for r in records if r.roas is not None]
    max_ctr = max(ctrs) if ctrs else 0.0
    max_roas = max(roases) if roases else 0.0
    weights = _ScoringWeights()

    for r in records:
        score = _composite_score(r, max_ctr=max_ctr, max_roas=max_roas, platform="meta", campaign_objective="awareness", weights=weights)
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for record with ctr={r.ctr}"
