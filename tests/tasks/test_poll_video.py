"""Unit tests for poll_video_job Celery task (Issue #6 item C)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.services.providers.base import JobStatus

_TASK_MODULE = "vos_studio_mcp.tasks.poll_video"
_GET_SESSION = f"{_TASK_MODULE}.get_session"
_GET_ADAPTER = f"{_TASK_MODULE}.get_adapter"
_GET_ASSET = f"{_TASK_MODULE}.get_asset_with_client"
_GET_NOTIFY_CTX = f"{_TASK_MODULE}.get_asset_notification_context"
_ENQUEUE_WEBHOOK_FAILED = f"{_TASK_MODULE}.enqueue_webhook_failed"
_UPLOAD_TASK = "vos_studio_mcp.tasks.upload_video.upload_video_to_storage"


def _mock_asset(
    job_id: str = "gen-123",
    status: str = "pending",
    storage_status: str = "not_required",
) -> MagicMock:
    asset = MagicMock()
    asset.provider_job_id = job_id
    asset.generation_status = status
    asset.storage_status = storage_status
    asset.storage_url = None
    return asset


def _session_ctx(asset: MagicMock | None, client_id: str = "cli-001") -> MagicMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# _check_and_update helper (async, tested directly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_returns_retry_when_job_queued() -> None:
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(
        return_value=JobStatus(job_id="gen-123", status="queued")
    )

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "retry"


@pytest.mark.asyncio
async def test_check_returns_retry_when_job_running() -> None:
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(
        return_value=JobStatus(job_id="gen-123", status="running")
    )

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "retry"


@pytest.mark.asyncio
async def test_check_completes_and_dispatches_upload() -> None:
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(
        return_value=JobStatus(
            job_id="gen-123",
            status="completed",
            media_url="https://cdn.higgsfield.ai/video.mp4",
        )
    )
    upload_task = MagicMock()
    upload_task.delay = MagicMock()

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
        patch(f"{_TASK_MODULE}.upload_video_to_storage", upload_task),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "done"
    assert asset.generation_status == "completed"
    assert asset.storage_status == "pending"  # upload enqueued (ADR-0031)
    assert asset.storage_url is None  # upload task sets this, not poll task
    upload_task.delay.assert_called_once_with("asset-001", "https://cdn.higgsfield.ai/video.mp4")


@pytest.mark.asyncio
async def test_check_marks_failed_on_job_failure() -> None:
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(
        return_value=JobStatus(job_id="gen-123", status="failed", error="content violation")
    )

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
        patch(_GET_NOTIFY_CTX, new_callable=AsyncMock, return_value=(None, None, None)),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "done"
    assert asset.generation_status == "failed"


@pytest.mark.asyncio
async def test_check_enqueues_webhook_on_job_failure_with_webhook_url() -> None:
    """When the job fails AND a webhook_url is configured, enqueue_webhook_failed
    must be called with the correct event and IDs."""
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(
        return_value=JobStatus(job_id="gen-123", status="failed", error="content violation")
    )

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=("sprint-1", "cli-001", "https://client.example.com/hook"),
        ),
        patch(_ENQUEUE_WEBHOOK_FAILED) as mock_enqueue,
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "done"
    mock_enqueue.assert_called_once()
    kwargs = mock_enqueue.call_args.kwargs
    assert kwargs["event"] == "asset.failed"
    assert kwargs["asset_id"] == "asset-001"
    assert kwargs["webhook_url"] == "https://client.example.com/hook"


@pytest.mark.asyncio
async def test_check_skips_enqueue_when_no_webhook_url() -> None:
    """When get_asset_notification_context returns None values, no enqueue call is made."""
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(
        return_value=JobStatus(job_id="gen-123", status="failed")
    )

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
        patch(_GET_NOTIFY_CTX, new_callable=AsyncMock, return_value=(None, None, None)),
        patch(_ENQUEUE_WEBHOOK_FAILED) as mock_enqueue,
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        await _check_and_update("asset-001")

    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_check_skips_already_completed_asset() -> None:
    asset = _mock_asset(status="completed")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock()

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "done"
    adapter.check_job_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_returns_retry_on_adapter_exception() -> None:
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(side_effect=Exception("network error"))

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "retry"


@pytest.mark.asyncio
async def test_check_returns_done_when_asset_not_found() -> None:
    with (
        patch(_GET_SESSION, return_value=_session_ctx(None)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(None, None)),
        patch(_GET_ADAPTER, return_value=MagicMock()),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-missing")

    assert result == "done"


@pytest.mark.asyncio
async def test_check_completes_without_media_url_skips_upload() -> None:
    asset = _mock_asset(status="pending")
    adapter = MagicMock()
    adapter.check_job_status = AsyncMock(
        return_value=JobStatus(job_id="gen-123", status="completed", media_url=None)
    )
    upload_task = MagicMock()

    with (
        patch(_GET_SESSION, return_value=_session_ctx(asset)),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GET_ADAPTER, return_value=adapter),
        patch(f"{_TASK_MODULE}.upload_video_to_storage", upload_task),
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "done"
    upload_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# poll_video_job.run() — main task body (sync, bind=True)
# ---------------------------------------------------------------------------


def test_poll_video_job_marks_failed_when_max_retries_exceeded() -> None:
    """When retries are exhausted the asset must be marked failed."""
    from celery.exceptions import MaxRetriesExceededError

    from vos_studio_mcp.tasks.poll_video import poll_video_job

    mock_mark = AsyncMock()

    with (
        patch(
            f"{_TASK_MODULE}._check_and_update",
            new=AsyncMock(return_value="retry"),
        ),
        patch(
            f"{_TASK_MODULE}._mark_status",
            new=mock_mark,
        ),
        patch.object(poll_video_job, "retry", side_effect=MaxRetriesExceededError()),
    ):
        poll_video_job.run("asset-001")

    mock_mark.assert_awaited_once_with("asset-001", "failed")


def test_poll_video_job_raises_retry_on_transient_outcome() -> None:
    """On the first few retries Celery's Retry exception propagates normally."""
    from celery.exceptions import Retry

    from vos_studio_mcp.tasks.poll_video import poll_video_job

    with (
        patch(
            f"{_TASK_MODULE}._check_and_update",
            new=AsyncMock(return_value="retry"),
        ),
        patch.object(poll_video_job, "retry", side_effect=Retry()),
        pytest.raises(Retry),
    ):
        poll_video_job.run("asset-001")


def test_poll_video_job_done_outcome_returns_normally() -> None:
    """When _check_and_update returns 'done' the task exits cleanly."""
    from vos_studio_mcp.tasks.poll_video import poll_video_job

    with patch(
        f"{_TASK_MODULE}._check_and_update",
        new=AsyncMock(return_value="done"),
    ):
        poll_video_job.run("asset-001")  # must not raise


# ---------------------------------------------------------------------------
# _mark_status helper (async, tested directly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_status_sets_generation_status() -> None:
    asset = _mock_asset(status="pending")
    session = AsyncMock()
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GET_SESSION, return_value=ctx),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
    ):
        from vos_studio_mcp.tasks.poll_video import _mark_status
        await _mark_status("asset-001", "failed")

    assert asset.generation_status == "failed"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_status_skips_commit_when_asset_not_found() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_GET_SESSION, return_value=ctx),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(None, None)),
    ):
        from vos_studio_mcp.tasks.poll_video import _mark_status
        await _mark_status("missing-asset", "failed")

    session.commit.assert_not_awaited()
