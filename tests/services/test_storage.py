"""Unit tests for the storage service (ADR-0008).

Covers download_video and upload_video in isolation — no real network or S3
calls are made. The existing task-level tests in test_upload_video.py exercise
these functions through the Celery task; these tests target the service directly.
"""

from unittest.mock import MagicMock, patch

import pytest
import respx
from httpx import HTTPStatusError, Response

_STORAGE = "vos_studio_mcp.services.storage"
_SETTINGS = f"{_STORAGE}.get_settings"

_CDN_URL = "https://cdn.higgsfield.ai/video.mp4"
_ASSET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_CLIENT_ID = "cccccccc-0000-0000-0000-000000000003"


def _mock_settings() -> MagicMock:
    s = MagicMock()
    s.storage_endpoint = "https://r2.example.com"
    s.storage_access_key = "access-key"
    s.storage_secret_key = "secret-key"
    s.storage_bucket = "vos-assets"
    s.storage_public_base_url = "https://pub.example.com"
    return s


# ---------------------------------------------------------------------------
# download_video
# ---------------------------------------------------------------------------


@respx.mock
def test_download_video_returns_bytes() -> None:
    """download_video must return the raw response bytes on 200."""
    respx.get(_CDN_URL).mock(return_value=Response(200, content=b"fake-video"))

    from vos_studio_mcp.services.storage import download_video

    data = download_video(_CDN_URL)

    assert data == b"fake-video"


@respx.mock
def test_download_video_raises_on_4xx() -> None:
    """download_video must propagate HTTP errors (raise_for_status)."""
    respx.get(_CDN_URL).mock(return_value=Response(404))

    from vos_studio_mcp.services.storage import download_video

    with pytest.raises(HTTPStatusError):
        download_video(_CDN_URL)


@respx.mock
def test_download_video_raises_on_5xx() -> None:
    respx.get(_CDN_URL).mock(return_value=Response(503))

    from vos_studio_mcp.services.storage import download_video

    with pytest.raises(HTTPStatusError):
        download_video(_CDN_URL)


@respx.mock
def test_download_video_follows_redirects() -> None:
    """download_video must follow redirects (follow_redirects=True)."""
    final_url = "https://cdn2.higgsfield.ai/video.mp4"
    respx.get(_CDN_URL).mock(
        return_value=Response(301, headers={"location": final_url})
    )
    respx.get(final_url).mock(return_value=Response(200, content=b"redirected-bytes"))

    from vos_studio_mcp.services.storage import download_video

    data = download_video(_CDN_URL)

    assert data == b"redirected-bytes"


# ---------------------------------------------------------------------------
# upload_video
# ---------------------------------------------------------------------------


def test_upload_video_calls_put_object() -> None:
    """upload_video must invoke s3.put_object with the correct parameters."""
    s3_mock = MagicMock()
    s3_mock.put_object = MagicMock()

    with (
        patch("boto3.client", return_value=s3_mock),
        patch(_SETTINGS, return_value=_mock_settings()),
    ):
        from vos_studio_mcp.services.storage import upload_video

        upload_video(b"data", _ASSET_ID, _CLIENT_ID)

    s3_mock.put_object.assert_called_once()
    call_kwargs = s3_mock.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "vos-assets"
    assert call_kwargs["ContentType"] == "video/mp4"
    assert call_kwargs["Body"] == b"data"
    assert _ASSET_ID in call_kwargs["Key"]
    assert _CLIENT_ID in call_kwargs["Key"]


def test_upload_video_returns_public_url() -> None:
    """upload_video must return a URL rooted at storage_public_base_url."""
    s3_mock = MagicMock()

    with (
        patch("boto3.client", return_value=s3_mock),
        patch(_SETTINGS, return_value=_mock_settings()),
    ):
        from vos_studio_mcp.services.storage import upload_video

        url = upload_video(b"data", _ASSET_ID, _CLIENT_ID)

    assert url.startswith("https://pub.example.com/")
    assert _ASSET_ID in url


def test_upload_video_key_structure() -> None:
    """Object key must follow the videos/{client_id}/{asset_id}.mp4 pattern."""
    s3_mock = MagicMock()

    with (
        patch("boto3.client", return_value=s3_mock),
        patch(_SETTINGS, return_value=_mock_settings()),
    ):
        from vos_studio_mcp.services.storage import upload_video

        upload_video(b"data", _ASSET_ID, _CLIENT_ID)

    key = s3_mock.put_object.call_args.kwargs["Key"]
    assert key == f"videos/{_CLIENT_ID}/{_ASSET_ID}.mp4"


def test_upload_video_url_no_double_slash() -> None:
    """Public URL must not have a double-slash between base and key."""
    s3_mock = MagicMock()
    settings = _mock_settings()
    settings.storage_public_base_url = "https://pub.example.com/"  # trailing slash

    with (
        patch("boto3.client", return_value=s3_mock),
        patch(_SETTINGS, return_value=settings),
    ):
        from vos_studio_mcp.services.storage import upload_video

        url = upload_video(b"data", _ASSET_ID, _CLIENT_ID)

    assert "//" not in url.replace("https://", "")


def test_upload_video_propagates_s3_error() -> None:
    """If put_object raises, the exception propagates to the caller (task handles it)."""
    s3_mock = MagicMock()
    s3_mock.put_object.side_effect = OSError("S3 unreachable")

    with (
        patch("boto3.client", return_value=s3_mock),
        patch(_SETTINGS, return_value=_mock_settings()),
    ):
        from vos_studio_mcp.services.storage import upload_video

        with pytest.raises(OSError, match="S3 unreachable"):
            upload_video(b"data", _ASSET_ID, _CLIENT_ID)
