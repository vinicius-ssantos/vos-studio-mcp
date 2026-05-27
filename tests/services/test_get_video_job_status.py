"""Unit tests for get_video_job_status service (Issue #6 item E)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.generation_service import get_video_job_status

_GET_SESSION = "vos_studio_mcp.services.generation_service.get_session"
_GET_ASSET = "vos_studio_mcp.services.generation_service.get_asset_with_client"
_GUARD = "vos_studio_mcp.services.generation_service.assert_owns_client"


def _make_session_ctx() -> MagicMock:
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_asset(
    generation_status: str = "pending",
    storage_status: str = "not_required",
    storage_url: str | None = None,
    provider_job_id: str | None = "gen-123",
) -> MagicMock:
    asset = MagicMock()
    asset.generation_status = generation_status
    asset.storage_status = storage_status
    asset.storage_url = storage_url
    asset.provider_job_id = provider_job_id
    return asset


# ---------------------------------------------------------------------------
# not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_not_found_raises_not_found() -> None:
    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(None, None)),
        patch(_GUARD),
        pytest.raises(VosError) as exc_info,
    ):
        await get_video_job_status("missing-asset")

    assert exc_info.value.error_code == ErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# ownership guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_client_raises() -> None:
    asset = _make_asset()
    from vos_studio_mcp.errors import VosError as _VE

    def _bad_guard(_: str) -> None:
        raise _VE(ErrorCode.INVALID_INPUT, "mismatch")

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-other")),
        patch(_GUARD, side_effect=_bad_guard),
        pytest.raises(VosError) as exc_info,
    ):
        await get_video_job_status("asset-001")

    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


# ---------------------------------------------------------------------------
# status-specific responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_status_returns_correct_fields() -> None:
    asset = _make_asset(generation_status="pending")

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.status == "ok"
    assert result.generation_status == "pending"
    assert result.next_action == "get_video_job_status"
    assert result.storage_url is None
    assert result.provider_job_id == "gen-123"


@pytest.mark.asyncio
async def test_processing_status_returns_poll_next_action() -> None:
    asset = _make_asset(generation_status="processing")

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.generation_status == "processing"
    assert result.next_action == "get_video_job_status"


@pytest.mark.asyncio
async def test_completed_returns_storage_url_and_pack_next_action() -> None:
    asset = _make_asset(
        generation_status="completed",
        storage_status="stored",
        storage_url="https://r2.example.com/videos/cli-001/asset-001.mp4",
    )

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.generation_status == "completed"
    assert result.storage_status == "stored"
    assert result.storage_url == "https://r2.example.com/videos/cli-001/asset-001.mp4"
    assert result.next_action == "prepare_dashboard_pack"


@pytest.mark.asyncio
async def test_failed_status_suggests_retry() -> None:
    asset = _make_asset(generation_status="failed")

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.generation_status == "failed"
    assert result.next_action == "request_api_video"


@pytest.mark.asyncio
async def test_manual_asset_returns_list_next_action() -> None:
    asset = _make_asset(generation_status="manual", provider_job_id=None)

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.generation_status == "manual"
    assert result.next_action == "list_sprint_assets"
    assert result.provider_job_id is None


# ---------------------------------------------------------------------------
# Fix #65 — storage-status-aware summary and next_action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completed_storage_pending_returns_poll_next_action() -> None:
    """completed + storage_status=pending → still uploading, poll again."""
    asset = _make_asset(
        generation_status="completed",
        storage_status="pending",
    )

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.generation_status == "completed"
    assert result.storage_status == "pending"
    assert result.next_action == "get_video_job_status"
    assert "upload to storage in progress" in result.summary


@pytest.mark.asyncio
async def test_completed_storage_failed_returns_poll_next_action() -> None:
    """completed + storage_status=failed → upload failed, poll again."""
    asset = _make_asset(
        generation_status="completed",
        storage_status="failed",
    )

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.generation_status == "completed"
    assert result.storage_status == "failed"
    assert result.next_action == "get_video_job_status"
    assert "storage upload failed" in result.summary


@pytest.mark.asyncio
async def test_completed_stored_returns_prepare_dashboard_pack() -> None:
    """completed + storage_status=stored → ready, move to pack prep."""
    asset = _make_asset(
        generation_status="completed",
        storage_status="stored",
        storage_url="https://r2.example.com/v.mp4",
    )

    with (
        patch(_GET_SESSION, return_value=_make_session_ctx()),
        patch(_GET_ASSET, new_callable=AsyncMock, return_value=(asset, "cli-001")),
        patch(_GUARD),
    ):
        result = await get_video_job_status("asset-001")

    assert result.next_action == "prepare_dashboard_pack"
    assert "ready in storage" in result.summary
