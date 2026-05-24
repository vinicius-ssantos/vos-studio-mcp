"""Unit tests for upload_video_to_storage Celery task (Issue #6 item D)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_TASK_MODULE = "vos_studio_mcp.tasks.upload_video"
_STORAGE = "vos_studio_mcp.tasks.upload_video.storage"
_GET_CLIENT_ID = f"{_TASK_MODULE}._get_client_id"
_UPDATE_URL = f"{_TASK_MODULE}._update_storage_url"
_MARK_FAILED = f"{_TASK_MODULE}._mark_upload_failed"
_NOTIFY_COMPLETED = f"{_TASK_MODULE}._notify_completed"
_NOTIFY_UPLOAD_FAILED = f"{_TASK_MODULE}._notify_upload_failed"


# ---------------------------------------------------------------------------
# async helpers tested directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_client_id_returns_none_when_asset_missing() -> None:
    with patch(
        f"{_TASK_MODULE}.get_session",
        return_value=_make_session_ctx(),
    ), patch(
        f"{_TASK_MODULE}.get_asset_with_client",
        new_callable=AsyncMock,
        return_value=(None, None),
    ):
        from vos_studio_mcp.tasks.upload_video import _get_client_id
        result = await _get_client_id("missing-asset")

    assert result is None


@pytest.mark.asyncio
async def test_get_client_id_returns_client_id() -> None:
    asset = MagicMock()
    with patch(
        f"{_TASK_MODULE}.get_session",
        return_value=_make_session_ctx(),
    ), patch(
        f"{_TASK_MODULE}.get_asset_with_client",
        new_callable=AsyncMock,
        return_value=(asset, "cli-001"),
    ):
        from vos_studio_mcp.tasks.upload_video import _get_client_id
        result = await _get_client_id("asset-001")

    assert result == "cli-001"


@pytest.mark.asyncio
async def test_update_storage_url_sets_fields() -> None:
    """_update_storage_url must set storage_url and storage_status='stored' (ADR-0031).

    generation_status must NOT be touched — that field belongs to the provider
    lifecycle, not the upload lifecycle.
    """
    asset = MagicMock()
    asset.storage_url = None
    asset.storage_status = "pending"
    asset.generation_status = "completed"  # already set by webhook/poll — must stay
    session = AsyncMock()
    session.commit = AsyncMock()

    with patch(
        f"{_TASK_MODULE}.get_session",
        return_value=_make_session_ctx(session),
    ), patch(
        f"{_TASK_MODULE}.get_asset_with_client",
        new_callable=AsyncMock,
        return_value=(asset, "cli-001"),
    ):
        from vos_studio_mcp.tasks.upload_video import _update_storage_url
        await _update_storage_url("asset-001", "https://r2.example.com/video.mp4")

    assert asset.storage_url == "https://r2.example.com/video.mp4"
    assert asset.storage_status == "stored"
    assert asset.generation_status == "completed"  # unchanged
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_upload_failed_sets_storage_status() -> None:
    """_mark_upload_failed must set storage_status='failed' (ADR-0031).

    generation_status must NOT be touched — generation succeeded; only the
    upload step failed.
    """
    asset = MagicMock()
    asset.storage_status = "pending"
    asset.generation_status = "completed"  # must stay unchanged
    session = AsyncMock()
    session.commit = AsyncMock()

    with patch(
        f"{_TASK_MODULE}.get_session",
        return_value=_make_session_ctx(session),
    ), patch(
        f"{_TASK_MODULE}.get_asset_with_client",
        new_callable=AsyncMock,
        return_value=(asset, "cli-001"),
    ):
        from vos_studio_mcp.tasks.upload_video import _mark_upload_failed
        await _mark_upload_failed("asset-001")

    assert asset.storage_status == "failed"
    assert asset.generation_status == "completed"  # unchanged


# ---------------------------------------------------------------------------
# storage functions
# ---------------------------------------------------------------------------


def test_download_video_returns_bytes(respx_mock: "Any") -> None:
    import respx
    from httpx import Response

    with respx.mock:
        respx.get("https://cdn.higgsfield.ai/video.mp4").mock(
            return_value=Response(200, content=b"fake-video-bytes")
        )
        from vos_studio_mcp.services.storage import download_video
        data = download_video("https://cdn.higgsfield.ai/video.mp4")

    assert data == b"fake-video-bytes"


def test_upload_video_calls_s3_put_object() -> None:
    s3_mock = MagicMock()
    s3_mock.put_object = MagicMock()

    with patch("boto3.client", return_value=s3_mock), patch(
        "vos_studio_mcp.services.storage.get_settings",
        return_value=MagicMock(
            storage_endpoint="https://r2.example.com",
            storage_access_key="key",
            storage_secret_key="secret",
            storage_bucket="assets",
            storage_public_base_url="https://pub.example.com",
        ),
    ):
        from vos_studio_mcp.services.storage import upload_video
        url = upload_video(b"data", "asset-001", "client-001")

    s3_mock.put_object.assert_called_once()
    assert "asset-001" in url
    assert url.startswith("https://pub.example.com")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_session_ctx(session: AsyncMock | None = None) -> MagicMock:
    if session is None:
        session = AsyncMock()
        session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# type: ignore helper for respx_mock fixture
from typing import Any  # noqa: E402

# ---------------------------------------------------------------------------
# upload_video_to_storage Celery task — main body (sync, bind=True)
# ---------------------------------------------------------------------------


def test_upload_video_to_storage_success() -> None:
    from vos_studio_mcp.tasks.upload_video import upload_video_to_storage

    with (
        patch(
            "vos_studio_mcp.tasks.upload_video._get_client_id",
            new=AsyncMock(return_value="cli-001"),
        ),
        patch(
            "vos_studio_mcp.tasks.upload_video._update_storage_url",
            new=AsyncMock(),
        ) as mock_update,
        patch("vos_studio_mcp.tasks.upload_video.storage") as mock_storage,
        patch(_NOTIFY_COMPLETED),
    ):
        mock_storage.download_video.return_value = b"video-data"
        mock_storage.upload_video.return_value = "https://r2.example.com/video.mp4"

        upload_video_to_storage.run("asset-001", "https://cdn.higgsfield.ai/v.mp4")

    mock_storage.download_video.assert_called_once_with("https://cdn.higgsfield.ai/v.mp4")
    mock_storage.upload_video.assert_called_once_with(b"video-data", "asset-001", "cli-001")
    mock_update.assert_awaited_once_with("asset-001", "https://r2.example.com/video.mp4")


def test_upload_video_to_storage_skips_when_no_client_id() -> None:
    from vos_studio_mcp.tasks.upload_video import upload_video_to_storage

    with (
        patch(
            "vos_studio_mcp.tasks.upload_video._get_client_id",
            new=AsyncMock(return_value=None),
        ),
        patch("vos_studio_mcp.tasks.upload_video.storage") as mock_storage,
    ):
        upload_video_to_storage.run("asset-missing", "https://cdn.higgsfield.ai/v.mp4")

    mock_storage.download_video.assert_not_called()


def test_upload_video_to_storage_marks_failed_after_max_retries() -> None:
    """When max retries are exhausted the asset must be marked failed."""
    from celery.exceptions import MaxRetriesExceededError

    from vos_studio_mcp.tasks.upload_video import upload_video_to_storage

    mock_mark = AsyncMock()

    with (
        patch(
            "vos_studio_mcp.tasks.upload_video._get_client_id",
            new=AsyncMock(return_value="cli-001"),
        ),
        patch(
            "vos_studio_mcp.tasks.upload_video._mark_upload_failed",
            new=mock_mark,
        ),
        patch(_NOTIFY_UPLOAD_FAILED),
        patch("vos_studio_mcp.tasks.upload_video.storage") as mock_storage,
        patch.object(upload_video_to_storage, "retry", side_effect=MaxRetriesExceededError()),
    ):
        mock_storage.download_video.side_effect = OSError("CDN unreachable")
        upload_video_to_storage.run("asset-001", "https://cdn.higgsfield.ai/v.mp4")

    mock_mark.assert_awaited_once_with("asset-001")


def test_upload_video_to_storage_retries_on_transient_error() -> None:
    """On the first few failures the task should reschedule itself (Retry raised).

    Retry is a subclass of Exception so it gets caught by the inner
    except-clause; _mark_upload_failed runs but must also be patched so no
    real DB connection is attempted.
    """
    from celery.exceptions import Retry

    from vos_studio_mcp.tasks.upload_video import upload_video_to_storage

    mock_mark = AsyncMock()

    with (
        patch(
            "vos_studio_mcp.tasks.upload_video._get_client_id",
            new=AsyncMock(return_value="cli-001"),
        ),
        patch(
            "vos_studio_mcp.tasks.upload_video._mark_upload_failed",
            new=mock_mark,
        ),
        patch(_NOTIFY_UPLOAD_FAILED),
        patch("vos_studio_mcp.tasks.upload_video.storage") as mock_storage,
        patch.object(upload_video_to_storage, "retry", side_effect=Retry()),
    ):
        mock_storage.download_video.side_effect = OSError("transient")
        upload_video_to_storage.run("asset-001", "https://cdn.higgsfield.ai/v.mp4")

    # task completed without raising; _mark_upload_failed was invoked because
    # Retry (a subclass of Exception) was caught by the inner except block
    mock_mark.assert_awaited_once_with("asset-001")


# ---------------------------------------------------------------------------
# _notify_completed and _notify_upload_failed — direct async helpers
# ---------------------------------------------------------------------------

_GET_NOTIFY_CTX = f"{_TASK_MODULE}.get_asset_notification_context"
_ENQUEUE_COMPLETED = f"{_TASK_MODULE}.enqueue_webhook_completed"
_ENQUEUE_FAILED = f"{_TASK_MODULE}.enqueue_webhook_failed"

_ASSET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_SPRINT_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_CLIENT_ID = "cccccccc-0000-0000-0000-000000000003"
_WEBHOOK_URL = "https://client.example.com/hook"


def test_notify_completed_enqueues_when_webhook_url_set() -> None:
    """_notify_completed must call enqueue_webhook_completed when all context is present."""
    storage_url = "https://r2.example.com/video.mp4"

    with (
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=(_SPRINT_ID, _CLIENT_ID, _WEBHOOK_URL),
        ),
        patch(_ENQUEUE_COMPLETED) as mock_enqueue,
    ):
        from vos_studio_mcp.tasks.upload_video import _notify_completed
        _notify_completed(_ASSET_ID, storage_url)

    mock_enqueue.assert_called_once()
    kwargs = mock_enqueue.call_args.kwargs
    assert kwargs["asset_id"] == _ASSET_ID
    assert kwargs["storage_url"] == storage_url
    assert kwargs["webhook_url"] == _WEBHOOK_URL
    assert kwargs["sprint_id"] == _SPRINT_ID
    assert kwargs["client_id"] == _CLIENT_ID


def test_notify_completed_skips_when_no_webhook_url() -> None:
    """_notify_completed must not call enqueue when webhook_url is None."""
    with (
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=(None, None, None),
        ),
        patch(_ENQUEUE_COMPLETED) as mock_enqueue,
    ):
        from vos_studio_mcp.tasks.upload_video import _notify_completed
        _notify_completed(_ASSET_ID, "https://r2.example.com/video.mp4")

    mock_enqueue.assert_not_called()


def test_notify_upload_failed_enqueues_when_webhook_url_set() -> None:
    """_notify_upload_failed must call enqueue_webhook_failed with asset.upload_failed event."""
    with (
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=(_SPRINT_ID, _CLIENT_ID, _WEBHOOK_URL),
        ),
        patch(_ENQUEUE_FAILED) as mock_enqueue,
    ):
        from vos_studio_mcp.tasks.upload_video import _notify_upload_failed
        _notify_upload_failed(_ASSET_ID)

    mock_enqueue.assert_called_once()
    kwargs = mock_enqueue.call_args.kwargs
    assert kwargs["asset_id"] == _ASSET_ID
    assert kwargs["event"] == "asset.upload_failed"
    assert kwargs["webhook_url"] == _WEBHOOK_URL


def test_notify_upload_failed_skips_when_no_context() -> None:
    """_notify_upload_failed must not call enqueue when context lookup returns None."""
    with (
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=(None, None, None),
        ),
        patch(_ENQUEUE_FAILED) as mock_enqueue,
    ):
        from vos_studio_mcp.tasks.upload_video import _notify_upload_failed
        _notify_upload_failed(_ASSET_ID)

    mock_enqueue.assert_not_called()
