"""Unit tests for poll_video_job Celery task (Issue #6 item C)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.services.providers.base import JobStatus

_TASK_MODULE = "vos_studio_mcp.tasks.poll_video"
_GET_SESSION = f"{_TASK_MODULE}.get_session"
_GET_ADAPTER = f"{_TASK_MODULE}.get_adapter"
_GET_ASSET = f"{_TASK_MODULE}.get_asset_with_client"
_UPLOAD_TASK = "vos_studio_mcp.tasks.upload_video.upload_video_to_storage"


def _mock_asset(
    job_id: str = "gen-123",
    status: str = "pending",
) -> MagicMock:
    asset = MagicMock()
    asset.provider_job_id = job_id
    asset.generation_status = status
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
    assert asset.storage_url == "https://cdn.higgsfield.ai/video.mp4"
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
    ):
        from vos_studio_mcp.tasks.poll_video import _check_and_update
        result = await _check_and_update("asset-001")

    assert result == "done"
    assert asset.generation_status == "failed"


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
