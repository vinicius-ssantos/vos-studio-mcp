"""Unit tests for Celery Beat scheduled tasks (Issue #28)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SESSION_PATCH = "vos_studio_mcp.tasks.scheduled.get_privileged_session"


def _mock_session_ctx(
    brand_kit_ids: list[uuid.UUID] | None = None,
    top_records: list[MagicMock] | None = None,
    loser_records: list[MagicMock] | None = None,
    brand_kit: MagicMock | None = None,
    deleted_rows: int = 0,
) -> MagicMock:
    """Build a reusable async session context mock."""
    if brand_kit_ids is None:
        brand_kit_ids = []

    # First execute: distinct brand_kit_ids
    bk_rows = [(bk_id,) for bk_id in brand_kit_ids]
    first_result = MagicMock()
    first_result.all = MagicMock(return_value=bk_rows)

    # Second execute: top_performer records
    top_scalars = MagicMock()
    top_scalars.all = MagicMock(return_value=top_records or [])
    top_result = MagicMock()
    top_result.scalars = MagicMock(return_value=top_scalars)

    # Third execute: loser records
    loser_scalars = MagicMock()
    loser_scalars.all = MagicMock(return_value=loser_records or [])
    loser_result = MagicMock()
    loser_result.scalars = MagicMock(return_value=loser_scalars)

    # Delete execute
    delete_result = MagicMock()
    delete_result.fetchall = MagicMock(return_value=[MagicMock()] * deleted_rows)

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[first_result, top_result, loser_result, delete_result]
    )
    session.get = AsyncMock(return_value=brand_kit or MagicMock())
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# rollup_performance_memory
# ---------------------------------------------------------------------------


class TestRollupPerformanceMemory:
    @pytest.mark.asyncio
    async def test_no_brand_kits_returns_zero(self) -> None:
        from vos_studio_mcp.tasks.scheduled import _do_rollup

        session_ctx = _mock_session_ctx(brand_kit_ids=[])

        with patch(_SESSION_PATCH, return_value=session_ctx):
            result = await _do_rollup()

        assert result == {"updated": 0, "skipped": 0}

    @pytest.mark.asyncio
    async def test_updates_brand_kit_memory(self) -> None:
        from vos_studio_mcp.tasks.scheduled import _do_rollup

        bk_id = uuid.uuid4()

        top_record = MagicMock()
        top_record.notes = "Strong opening hook"
        top_record.hook_retention_rate = 0.75

        loser_record = MagicMock()
        loser_record.notes = "Too long intro"

        brand_kit = MagicMock()

        # Need 3 separate session contexts: 1 for distinct query, 1 for rollup
        bk_rows = [(bk_id,)]
        first_result = MagicMock()
        first_result.all = MagicMock(return_value=bk_rows)

        top_scalars = MagicMock()
        top_scalars.all = MagicMock(return_value=[top_record])
        top_result = MagicMock()
        top_result.scalars = MagicMock(return_value=top_scalars)

        loser_scalars = MagicMock()
        loser_scalars.all = MagicMock(return_value=[loser_record])
        loser_result = MagicMock()
        loser_result.scalars = MagicMock(return_value=loser_scalars)

        # Session 1: distinct brand_kit_ids
        session1 = AsyncMock()
        session1.execute = AsyncMock(return_value=first_result)
        ctx1 = MagicMock()
        ctx1.__aenter__ = AsyncMock(return_value=session1)
        ctx1.__aexit__ = AsyncMock(return_value=False)

        # Session 2: brand kit rollup queries
        session2 = AsyncMock()
        session2.execute = AsyncMock(side_effect=[top_result, loser_result])
        session2.get = AsyncMock(return_value=brand_kit)
        session2.commit = AsyncMock()
        ctx2 = MagicMock()
        ctx2.__aenter__ = AsyncMock(return_value=session2)
        ctx2.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(_SESSION_PATCH, side_effect=[ctx1, ctx2]),
        ):
            result = await _do_rollup()

        assert result == {"updated": 1, "skipped": 0}
        memory = brand_kit.performance_memory
        assert "proven_angles" in memory
        assert "failed_approaches" in memory
        assert "last_rollup_at" in memory

    @pytest.mark.asyncio
    async def test_brand_kit_not_found_skips_gracefully(self) -> None:
        from vos_studio_mcp.tasks.scheduled import _do_rollup

        bk_id = uuid.uuid4()
        bk_rows = [(bk_id,)]

        first_result = MagicMock()
        first_result.all = MagicMock(return_value=bk_rows)

        top_scalars = MagicMock()
        top_scalars.all = MagicMock(return_value=[])
        top_result = MagicMock()
        top_result.scalars = MagicMock(return_value=top_scalars)

        loser_scalars = MagicMock()
        loser_scalars.all = MagicMock(return_value=[])
        loser_result = MagicMock()
        loser_result.scalars = MagicMock(return_value=loser_scalars)

        session1 = AsyncMock()
        session1.execute = AsyncMock(return_value=first_result)
        ctx1 = MagicMock()
        ctx1.__aenter__ = AsyncMock(return_value=session1)
        ctx1.__aexit__ = AsyncMock(return_value=False)

        session2 = AsyncMock()
        session2.execute = AsyncMock(side_effect=[top_result, loser_result])
        session2.get = AsyncMock(return_value=None)  # brand kit not found
        session2.commit = AsyncMock()
        ctx2 = MagicMock()
        ctx2.__aenter__ = AsyncMock(return_value=session2)
        ctx2.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(_SESSION_PATCH, side_effect=[ctx1, ctx2]),
        ):
            result = await _do_rollup()

        # brand kit not found → no update, no error
        assert result["updated"] == 0


# ---------------------------------------------------------------------------
# cleanup_stale_jobs
# ---------------------------------------------------------------------------


class TestCleanupStaleJobs:
    @pytest.mark.asyncio
    async def test_returns_deleted_count(self) -> None:
        from vos_studio_mcp.tasks.scheduled import _do_cleanup

        delete_result = MagicMock()
        delete_result.fetchall = MagicMock(return_value=[MagicMock(), MagicMock(), MagicMock()])

        session = AsyncMock()
        session.execute = AsyncMock(return_value=delete_result)
        session.commit = AsyncMock()

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(_SESSION_PATCH, return_value=ctx):
            result = await _do_cleanup()

        assert result == {"deleted": 3}
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_stale_jobs_returns_zero(self) -> None:
        from vos_studio_mcp.tasks.scheduled import _do_cleanup

        delete_result = MagicMock()
        delete_result.fetchall = MagicMock(return_value=[])

        session = AsyncMock()
        session.execute = AsyncMock(return_value=delete_result)
        session.commit = AsyncMock()

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(_SESSION_PATCH, return_value=ctx):
            result = await _do_cleanup()

        assert result == {"deleted": 0}

    def test_cutoff_is_30_days_ago(self) -> None:
        """Verify the STALE_DAYS constant and cutoff calculation."""
        from vos_studio_mcp.tasks.scheduled import _STALE_DAYS

        assert _STALE_DAYS == 30
        cutoff = datetime.now(UTC) - timedelta(days=_STALE_DAYS)
        assert (datetime.now(UTC) - cutoff).days == 30


# ---------------------------------------------------------------------------
# beat schedule registration
# ---------------------------------------------------------------------------


def test_beat_schedule_is_registered() -> None:
    """Verify both tasks appear in the Celery beat schedule."""
    from vos_studio_mcp.tasks.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    task_names = {entry["task"] for entry in schedule.values()}

    assert "tasks.rollup_performance_memory" in task_names
    assert "tasks.cleanup_stale_jobs" in task_names


def test_beat_timezone_is_utc() -> None:
    from vos_studio_mcp.tasks.celery_app import celery_app

    assert celery_app.conf.timezone == "UTC"


# ---------------------------------------------------------------------------
# Retry / error paths — task-level (lines 52-56, 166-170)
# ---------------------------------------------------------------------------


def test_rollup_performance_memory_retries_on_exception() -> None:
    """When _do_rollup raises, the task must call self.retry with countdown=300."""
    from celery.exceptions import Retry

    from vos_studio_mcp.tasks.scheduled import rollup_performance_memory

    with (
        patch(
            "vos_studio_mcp.tasks.scheduled._do_rollup",
            side_effect=RuntimeError("db gone"),
        ),
        patch.object(rollup_performance_memory, "retry", side_effect=Retry()),
        pytest.raises(Retry),
    ):  # noqa: SIM117
        rollup_performance_memory.run()


def test_rollup_performance_memory_retry_max_exceeded() -> None:
    """When retries are exhausted MaxRetriesExceededError propagates."""
    from celery.exceptions import MaxRetriesExceededError

    from vos_studio_mcp.tasks.scheduled import rollup_performance_memory

    with (
        patch(
            "vos_studio_mcp.tasks.scheduled._do_rollup",
            side_effect=RuntimeError("persistent failure"),
        ),
        patch.object(
            rollup_performance_memory, "retry", side_effect=MaxRetriesExceededError()
        ),
        pytest.raises(MaxRetriesExceededError),
    ):  # noqa: SIM117
        rollup_performance_memory.run()


def test_cleanup_stale_jobs_retries_on_exception() -> None:
    """When _do_cleanup raises, the task must call self.retry with countdown=600."""
    from celery.exceptions import Retry

    from vos_studio_mcp.tasks.scheduled import cleanup_stale_jobs

    with (
        patch(
            "vos_studio_mcp.tasks.scheduled._do_cleanup",
            side_effect=RuntimeError("db gone"),
        ),
        patch.object(cleanup_stale_jobs, "retry", side_effect=Retry()),
        pytest.raises(Retry),
    ):  # noqa: SIM117
        cleanup_stale_jobs.run()


def test_cleanup_stale_jobs_retry_max_exceeded() -> None:
    """When retries are exhausted MaxRetriesExceededError propagates."""
    from celery.exceptions import MaxRetriesExceededError

    from vos_studio_mcp.tasks.scheduled import cleanup_stale_jobs

    with (
        patch(
            "vos_studio_mcp.tasks.scheduled._do_cleanup",
            side_effect=RuntimeError("persistent failure"),
        ),
        patch.object(
            cleanup_stale_jobs, "retry", side_effect=MaxRetriesExceededError()
        ),
        pytest.raises(MaxRetriesExceededError),
    ):  # noqa: SIM117
        cleanup_stale_jobs.run()


# ---------------------------------------------------------------------------
# Per-brand-kit exception handler (lines 81-86)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_do_rollup_skips_brand_kit_on_exception() -> None:
    """When _rollup_brand_kit raises for one brand kit, it is counted as skipped."""
    import uuid as uuid_mod

    bk_id = uuid_mod.uuid4()
    bk_rows = [(bk_id,)]

    first_result = MagicMock()
    first_result.all = MagicMock(return_value=bk_rows)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=first_result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_SESSION_PATCH, return_value=ctx),
        patch(
            "vos_studio_mcp.tasks.scheduled._rollup_brand_kit",
            side_effect=RuntimeError("transient db error"),
        ),
    ):
        from vos_studio_mcp.tasks.scheduled import _do_rollup

        result = await _do_rollup()

    assert result == {"updated": 0, "skipped": 1}
