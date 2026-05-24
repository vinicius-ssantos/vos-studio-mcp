"""Unit tests for the deliver_webhook Celery task (notify_webhook module).

Coverage targets:
- Successful delivery → no retry enqueued.
- Transient failure below max_retries → retry raised with exponential backoff countdown.
- Failure at max_retries → task abandoned, warning logged.
- enqueue_webhook_completed / enqueue_webhook_failed convenience helpers.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MODULE = "vos_studio_mcp.tasks.notify_webhook"
# _deliver is imported locally inside _deliver_async; patch at the source module.
_DELIVER_SRC = "vos_studio_mcp.services.webhook_notifier._deliver"

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_ASSET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_SPRINT_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_CLIENT_ID = "cccccccc-0000-0000-0000-000000000003"
_WEBHOOK_URL = "https://client.example.com/hooks/vos"

_COMMON_KWARGS = dict(
    event="asset.completed",
    webhook_url=_WEBHOOK_URL,
    asset_id=_ASSET_ID,
    sprint_id=_SPRINT_ID,
    client_id=_CLIENT_ID,
    generation_status="completed",
    storage_status="stored",
    storage_url="https://r2.example.com/video.mp4",
    provider_job_id="gen-xyz",
)


def _make_task_instance(retries: int = 0) -> MagicMock:
    """Return a fake Celery task instance (the 'self' for bind=True tasks)."""
    task = MagicMock()
    task.request = MagicMock()
    task.request.retries = retries
    # By default, .retry() just raises — override per-test as needed.
    task.retry = MagicMock(side_effect=RuntimeError("retry-not-expected"))
    return task


# ---------------------------------------------------------------------------
# _deliver_async helper (async, tested directly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_async_succeeds_without_retry() -> None:
    """On a successful _deliver call no retry should be scheduled."""
    task = _make_task_instance(retries=0)

    with patch(_DELIVER_SRC, new_callable=AsyncMock) as mock_deliver:
        from vos_studio_mcp.tasks.notify_webhook import _deliver_async

        await _deliver_async(task, **_COMMON_KWARGS)

    mock_deliver.assert_awaited_once()
    task.retry.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_async_retries_on_transient_failure() -> None:
    """On a transient failure (attempt < max_retries) the task must raise Retry."""
    from celery.exceptions import Retry

    task = _make_task_instance(retries=0)
    task.retry = MagicMock(side_effect=Retry())

    with (
        patch(_DELIVER_SRC, new_callable=AsyncMock, side_effect=ConnectionError("timeout")),
        pytest.raises(Retry),
    ):
        from vos_studio_mcp.tasks.notify_webhook import _deliver_async

        await _deliver_async(task, **_COMMON_KWARGS)

    task.retry.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_async_countdown_is_within_expected_range() -> None:
    """First attempt (retries=0): backoff = 30s + jitter → countdown should be in [20, 40]."""
    from celery.exceptions import Retry

    task = _make_task_instance(retries=0)
    task.retry = MagicMock(side_effect=Retry())

    with (
        patch(_DELIVER_SRC, new_callable=AsyncMock, side_effect=OSError("fail")),
        pytest.raises(Retry),
    ):
        from vos_studio_mcp.tasks.notify_webhook import _deliver_async

        await _deliver_async(task, **_COMMON_KWARGS)

    countdown = task.retry.call_args.kwargs["countdown"]
    # base = 30 * 2^0 = 30, jitter ±10, clamped to ≥1
    assert 20 <= countdown <= 40, f"Unexpected countdown for attempt 0: {countdown}"


@pytest.mark.asyncio
async def test_deliver_async_backoff_grows_exponentially() -> None:
    """Countdown for attempt N ≈ 30 * 2^N (±11 s tolerance for jitter)."""
    from celery.exceptions import Retry

    for attempt in range(1, 4):  # attempts 1, 2, 3 → base 60, 120, 240
        task = _make_task_instance(retries=attempt)
        task.retry = MagicMock(side_effect=Retry())
        expected_base = 30 * (2 ** attempt)

        with (
            patch(_DELIVER_SRC, new_callable=AsyncMock, side_effect=OSError("fail")),
            pytest.raises(Retry),
        ):
            from vos_studio_mcp.tasks.notify_webhook import _deliver_async

            await _deliver_async(task, **_COMMON_KWARGS)

        countdown = task.retry.call_args.kwargs["countdown"]
        assert expected_base - 11 <= countdown <= expected_base + 11, (
            f"Attempt {attempt}: expected ≈{expected_base}s, got {countdown:.1f}s"
        )


@pytest.mark.asyncio
async def test_deliver_async_abandons_at_max_retries(caplog: pytest.LogCaptureFixture) -> None:
    """After MAX_RETRIES (5) the task must log a warning and return without retrying."""
    task = _make_task_instance(retries=5)  # == _MAX_RETRIES

    with (
        patch(_DELIVER_SRC, new_callable=AsyncMock, side_effect=OSError("permanent")),
        caplog.at_level(logging.WARNING, logger="vos_studio_mcp.tasks.notify_webhook"),
    ):
        from vos_studio_mcp.tasks.notify_webhook import _deliver_async

        await _deliver_async(task, **_COMMON_KWARGS)  # must NOT raise

    task.retry.assert_not_called()
    assert any("abandoned" in r.getMessage() for r in caplog.records), (
        "Expected 'abandoned' warning log record"
    )


@pytest.mark.asyncio
async def test_deliver_async_warning_includes_asset_id(caplog: pytest.LogCaptureFixture) -> None:
    """The abandonment warning must include asset_id for traceability."""
    task = _make_task_instance(retries=5)

    with (
        patch(_DELIVER_SRC, new_callable=AsyncMock, side_effect=OSError("fail")),
        caplog.at_level(logging.WARNING, logger="vos_studio_mcp.tasks.notify_webhook"),
    ):
        from vos_studio_mcp.tasks.notify_webhook import _deliver_async

        await _deliver_async(task, **_COMMON_KWARGS)

    records_with_asset = [
        r for r in caplog.records if r.asset_id == _ASSET_ID  # type: ignore[attr-defined]
    ]
    assert records_with_asset, "Expected log record with asset_id in extras"


# ---------------------------------------------------------------------------
# deliver_webhook Celery task (sync entry-point, bind=True)
# ---------------------------------------------------------------------------


def test_deliver_webhook_task_runs_async_helper() -> None:
    """deliver_webhook.run() must delegate to _deliver_async with all kwargs."""
    from vos_studio_mcp.tasks.notify_webhook import deliver_webhook

    with patch(f"{_MODULE}._deliver_async", new_callable=AsyncMock) as mock_async:
        deliver_webhook.run(**_COMMON_KWARGS)

    mock_async.assert_awaited_once()
    _, called_kwargs = mock_async.call_args
    assert called_kwargs["asset_id"] == _ASSET_ID
    assert called_kwargs["event"] == "asset.completed"
    assert called_kwargs["webhook_url"] == _WEBHOOK_URL


# ---------------------------------------------------------------------------
# enqueue_webhook_completed convenience helper
# ---------------------------------------------------------------------------


def test_enqueue_webhook_completed_calls_delay() -> None:
    from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_completed

    with patch(f"{_MODULE}.deliver_webhook") as mock_task:
        enqueue_webhook_completed(
            asset_id=_ASSET_ID,
            sprint_id=_SPRINT_ID,
            client_id=_CLIENT_ID,
            webhook_url=_WEBHOOK_URL,
            storage_url="https://r2.example.com/video.mp4",
            provider_job_id="gen-xyz",
        )

    mock_task.delay.assert_called_once()
    kwargs = mock_task.delay.call_args.kwargs
    assert kwargs["event"] == "asset.completed"
    assert kwargs["generation_status"] == "completed"
    assert kwargs["storage_status"] == "stored"
    assert kwargs["storage_url"] == "https://r2.example.com/video.mp4"
    assert kwargs["asset_id"] == _ASSET_ID
    assert kwargs["sprint_id"] == _SPRINT_ID
    assert kwargs["client_id"] == _CLIENT_ID


def test_enqueue_webhook_completed_default_storage_status() -> None:
    """storage_status defaults to 'stored' when not supplied."""
    from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_completed

    with patch(f"{_MODULE}.deliver_webhook") as mock_task:
        enqueue_webhook_completed(
            asset_id=_ASSET_ID,
            sprint_id=_SPRINT_ID,
            client_id=_CLIENT_ID,
            webhook_url=_WEBHOOK_URL,
            storage_url=None,
            provider_job_id=None,
        )

    assert mock_task.delay.call_args.kwargs["storage_status"] == "stored"


def test_enqueue_webhook_completed_allows_null_storage_url() -> None:
    from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_completed

    with patch(f"{_MODULE}.deliver_webhook") as mock_task:
        enqueue_webhook_completed(
            asset_id=_ASSET_ID,
            sprint_id=_SPRINT_ID,
            client_id=_CLIENT_ID,
            webhook_url=_WEBHOOK_URL,
            storage_url=None,
            provider_job_id=None,
        )

    assert mock_task.delay.call_args.kwargs["storage_url"] is None


# ---------------------------------------------------------------------------
# enqueue_webhook_failed convenience helper
# ---------------------------------------------------------------------------


def test_enqueue_webhook_failed_default_event() -> None:
    from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_failed

    with patch(f"{_MODULE}.deliver_webhook") as mock_task:
        enqueue_webhook_failed(
            asset_id=_ASSET_ID,
            sprint_id=_SPRINT_ID,
            client_id=_CLIENT_ID,
            webhook_url=_WEBHOOK_URL,
            provider_job_id="gen-xyz",
        )

    mock_task.delay.assert_called_once()
    kwargs = mock_task.delay.call_args.kwargs
    assert kwargs["event"] == "asset.failed"
    assert kwargs["generation_status"] == "failed"
    assert kwargs["storage_status"] == "failed"
    assert kwargs["storage_url"] is None


def test_enqueue_webhook_failed_custom_event() -> None:
    """Callers may override the event name (e.g. asset.upload_failed)."""
    from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_failed

    with patch(f"{_MODULE}.deliver_webhook") as mock_task:
        enqueue_webhook_failed(
            asset_id=_ASSET_ID,
            sprint_id=_SPRINT_ID,
            client_id=_CLIENT_ID,
            webhook_url=_WEBHOOK_URL,
            provider_job_id=None,
            event="asset.upload_failed",
        )

    assert mock_task.delay.call_args.kwargs["event"] == "asset.upload_failed"


def test_enqueue_webhook_failed_forwards_all_ids() -> None:
    from vos_studio_mcp.tasks.notify_webhook import enqueue_webhook_failed

    with patch(f"{_MODULE}.deliver_webhook") as mock_task:
        enqueue_webhook_failed(
            asset_id=_ASSET_ID,
            sprint_id=_SPRINT_ID,
            client_id=_CLIENT_ID,
            webhook_url=_WEBHOOK_URL,
            provider_job_id="gen-abc",
        )

    kwargs = mock_task.delay.call_args.kwargs
    assert kwargs["asset_id"] == _ASSET_ID
    assert kwargs["sprint_id"] == _SPRINT_ID
    assert kwargs["client_id"] == _CLIENT_ID
    assert kwargs["webhook_url"] == _WEBHOOK_URL
    assert kwargs["provider_job_id"] == "gen-abc"
