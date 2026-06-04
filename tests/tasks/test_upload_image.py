"""Unit tests for upload_image_to_storage Celery task (Issue #63)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_TASK_MODULE = "vos_studio_mcp.tasks.upload_image"
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
        from vos_studio_mcp.tasks.upload_image import _get_client_id
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
        from vos_studio_mcp.tasks.upload_image import _get_client_id
        result = await _get_client_id("asset-001")

    assert result == "cli-001"


@pytest.mark.asyncio
async def test_update_storage_url_sets_fields_and_needs_review() -> None:
    """_update_storage_url must set storage_url + storage_status='stored' (ADR-0031).

    When the asset has not been reviewed yet (qa_status is None), it must be
    marked 'needs_review' so agents can locate freshly-stored assets awaiting QA.
    generation_status must NOT be touched — it belongs to the provider lifecycle.
    """
    asset = MagicMock()
    asset.storage_url = None
    asset.storage_status = "pending"
    asset.generation_status = "completed"  # already set by webhook/poll — must stay
    asset.qa_status = None
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
        from vos_studio_mcp.tasks.upload_image import _update_storage_url
        await _update_storage_url("asset-001", "https://r2.example.com/image.png")

    assert asset.storage_url == "https://r2.example.com/image.png"
    assert asset.storage_status == "stored"
    assert asset.qa_status == "needs_review"
    assert asset.generation_status == "completed"  # unchanged
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_storage_url_preserves_existing_qa_status() -> None:
    """If the asset was already reviewed, _update_storage_url must not overwrite qa_status."""
    asset = MagicMock()
    asset.storage_url = None
    asset.storage_status = "pending"
    asset.qa_status = "approved"
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
        from vos_studio_mcp.tasks.upload_image import _update_storage_url
        await _update_storage_url("asset-001", "https://r2.example.com/image.png")

    assert asset.qa_status == "approved"  # unchanged


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
        from vos_studio_mcp.tasks.upload_image import _mark_upload_failed
        await _mark_upload_failed("asset-001")

    assert asset.storage_status == "failed"
    assert asset.generation_status == "completed"  # unchanged


# ---------------------------------------------------------------------------
# upload_image_to_storage Celery task — main body (sync, bind=True)
# ---------------------------------------------------------------------------


def test_upload_image_to_storage_success() -> None:
    from vos_studio_mcp.tasks.upload_image import upload_image_to_storage

    with (
        patch(_GET_CLIENT_ID, new=AsyncMock(return_value="cli-001")),
        patch(_UPDATE_URL, new=AsyncMock()) as mock_update,
        patch(f"{_TASK_MODULE}.emit_audit_event", new=AsyncMock()) as mock_audit,
        patch(f"{_TASK_MODULE}.storage") as mock_storage,
        patch(_NOTIFY_COMPLETED),
    ):
        mock_storage.download_media.return_value = b"image-data"
        mock_storage.upload_image.return_value = "https://r2.example.com/image.png"

        upload_image_to_storage.run("asset-001", "https://cdn.higgsfield.ai/i.png")

    mock_storage.download_media.assert_called_once_with("https://cdn.higgsfield.ai/i.png")
    mock_storage.upload_image.assert_called_once_with(b"image-data", "asset-001", "cli-001")
    mock_update.assert_awaited_once_with("asset-001", "https://r2.example.com/image.png")
    mock_audit.assert_awaited_once()


def test_upload_image_to_storage_skips_when_no_client_id() -> None:
    from vos_studio_mcp.tasks.upload_image import upload_image_to_storage

    with (
        patch(_GET_CLIENT_ID, new=AsyncMock(return_value=None)),
        patch(f"{_TASK_MODULE}.storage") as mock_storage,
    ):
        upload_image_to_storage.run("asset-missing", "https://cdn.higgsfield.ai/i.png")

    mock_storage.download_media.assert_not_called()


def test_upload_image_to_storage_marks_failed_after_max_retries() -> None:
    """When max retries are exhausted the asset must be marked failed."""
    from celery.exceptions import MaxRetriesExceededError

    from vos_studio_mcp.tasks.upload_image import upload_image_to_storage

    mock_mark = AsyncMock()

    with (
        patch(_GET_CLIENT_ID, new=AsyncMock(return_value="cli-001")),
        patch(_MARK_FAILED, new=mock_mark),
        patch(f"{_TASK_MODULE}.emit_audit_event", new=AsyncMock()),
        patch(_NOTIFY_UPLOAD_FAILED),
        patch(f"{_TASK_MODULE}.storage") as mock_storage,
        patch.object(upload_image_to_storage, "retry", side_effect=MaxRetriesExceededError()),
    ):
        mock_storage.download_media.side_effect = OSError("CDN unreachable")
        upload_image_to_storage.run("asset-001", "https://cdn.higgsfield.ai/i.png")

    mock_mark.assert_awaited_once_with("asset-001")


def test_upload_image_to_storage_retries_on_transient_error() -> None:
    """On the first few failures the task should reschedule itself (Retry raised).

    Retry is a subclass of Exception so it gets caught by the inner except-clause;
    _mark_upload_failed runs but must also be patched so no real DB call happens.
    """
    from celery.exceptions import Retry

    from vos_studio_mcp.tasks.upload_image import upload_image_to_storage

    mock_mark = AsyncMock()

    with (
        patch(_GET_CLIENT_ID, new=AsyncMock(return_value="cli-001")),
        patch(_MARK_FAILED, new=mock_mark),
        patch(f"{_TASK_MODULE}.emit_audit_event", new=AsyncMock()),
        patch(_NOTIFY_UPLOAD_FAILED),
        patch(f"{_TASK_MODULE}.storage") as mock_storage,
        patch.object(upload_image_to_storage, "retry", side_effect=Retry()),
    ):
        mock_storage.download_media.side_effect = OSError("transient")
        upload_image_to_storage.run("asset-001", "https://cdn.higgsfield.ai/i.png")

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
    storage_url = "https://r2.example.com/image.png"

    with (
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=(_SPRINT_ID, _CLIENT_ID, _WEBHOOK_URL),
        ),
        patch(_ENQUEUE_COMPLETED) as mock_enqueue,
    ):
        from vos_studio_mcp.tasks.upload_image import _notify_completed
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
        from vos_studio_mcp.tasks.upload_image import _notify_completed
        _notify_completed(_ASSET_ID, "https://r2.example.com/image.png")

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
        from vos_studio_mcp.tasks.upload_image import _notify_upload_failed
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
        from vos_studio_mcp.tasks.upload_image import _notify_upload_failed
        _notify_upload_failed(_ASSET_ID)

    mock_enqueue.assert_not_called()


def test_notify_completed_swallows_broker_error() -> None:
    """If enqueue_webhook_completed raises (e.g. broker down), _notify_completed must not
    propagate the error — a broker outage must not corrupt a successful upload."""
    with (
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=(_SPRINT_ID, _CLIENT_ID, _WEBHOOK_URL),
        ),
        patch(_ENQUEUE_COMPLETED, side_effect=RuntimeError("broker unavailable")),
    ):
        from vos_studio_mcp.tasks.upload_image import _notify_completed

        # Must not raise
        _notify_completed(_ASSET_ID, "https://r2.example.com/image.png")


def test_notify_upload_failed_swallows_broker_error() -> None:
    """If enqueue_webhook_failed raises (e.g. broker down), _notify_upload_failed must not
    propagate the error — a broker outage must not obscure the real failure reason."""
    with (
        patch(
            _GET_NOTIFY_CTX,
            new_callable=AsyncMock,
            return_value=(_SPRINT_ID, _CLIENT_ID, _WEBHOOK_URL),
        ),
        patch(_ENQUEUE_FAILED, side_effect=RuntimeError("broker unavailable")),
    ):
        from vos_studio_mcp.tasks.upload_image import _notify_upload_failed

        # Must not raise
        _notify_upload_failed(_ASSET_ID)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_session_ctx(session: Any | None = None) -> MagicMock:
    if session is None:
        session = AsyncMock()
        session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx
