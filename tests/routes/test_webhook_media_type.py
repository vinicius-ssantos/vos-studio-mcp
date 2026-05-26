"""Unit tests for provider → media_type routing in webhooks (Issue #63)."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.routes.webhooks import router

_SESSION_PATCH = "vos_studio_mcp.routes.webhooks.get_session"
_UPLOAD_VIDEO_PATCH = "vos_studio_mcp.routes.webhooks.upload_video_to_storage"
_UPLOAD_IMAGE_PATCH = "vos_studio_mcp.routes.webhooks.upload_image_to_storage"
_HIGGSFIELD_SETTINGS_PATCH = "vos_studio_mcp.services.providers.higgsfield.get_settings"
_FREEPIK_SETTINGS_PATCH = "vos_studio_mcp.services.providers.freepik.get_settings"
_MAGNIFIC_SETTINGS_PATCH = "vos_studio_mcp.services.providers.magnific.get_settings"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _mock_session(
    found: bool = True,
    client_id: str = "00000000-0000-0000-0000-000000000001",
) -> MagicMock:
    asset = MagicMock()
    asset.generation_status = "pending"
    asset.storage_status = "not_required"
    asset.storage_url = None

    row = MagicMock()
    row.__iter__ = MagicMock(return_value=iter(["asset-uuid-001", client_id]))

    execute_result = MagicMock()
    execute_result.first = MagicMock(return_value=row if found else None)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.get = AsyncMock(return_value=asset)
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Higgsfield (video) → upload_video_to_storage
# ---------------------------------------------------------------------------


def test_higgsfield_completion_triggers_video_upload() -> None:
    """Higgsfield completion must route to upload_video_to_storage, not image."""
    body = json.dumps({
        "generation_id": "gen-hf-001",
        "status": "COMPLETED",
        "output": {"media_url": "https://cdn.higgsfield.ai/video.mp4"},
    }).encode()
    settings = Settings(HIGGSFIELD_API_KEY="test-key", WEBHOOK_SECRET_HIGGSFIELD="wh-secret")
    session_ctx = _mock_session()

    with (
        patch(_HIGGSFIELD_SETTINGS_PATCH, return_value=settings),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_VIDEO_PATCH) as mock_video,
        patch(_UPLOAD_IMAGE_PATCH) as mock_image,
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200
    mock_video.delay.assert_called_once()
    mock_image.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Freepik (image) → upload_image_to_storage
# ---------------------------------------------------------------------------


def test_freepik_completion_triggers_image_upload() -> None:
    """Freepik completion must route to upload_image_to_storage, not video."""
    body = json.dumps({
        "id": "fpk-task-001",
        "status": "COMPLETED",
        "generated": [{"url": "https://cdn.freepik.com/image.jpg"}],
    }).encode()
    settings = Settings(FREEPIK_API_KEY="test-key", WEBHOOK_SECRET_FREEPIK="freepik-secret")
    session_ctx = _mock_session()

    with (
        patch(_FREEPIK_SETTINGS_PATCH, return_value=settings),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_VIDEO_PATCH) as mock_video,
        patch(_UPLOAD_IMAGE_PATCH) as mock_image,
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/freepik",
            content=body,
            headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
        )

    assert resp.status_code == 200
    mock_image.delay.assert_called_once()
    mock_video.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Magnific (image) → upload_image_to_storage
# ---------------------------------------------------------------------------


def test_magnific_completion_triggers_image_upload() -> None:
    """Magnific completion must route to upload_image_to_storage, not video."""
    body = json.dumps({
        "id": "mag-job-001",
        "status": "completed",
        "output_url": "https://cdn.magnific.ai/upscaled.jpg",
    }).encode()
    settings = Settings(MAGNIFIC_API_KEY="test-key", WEBHOOK_SECRET_MAGNIFIC="magnific-secret")
    session_ctx = _mock_session()

    with (
        patch(_MAGNIFIC_SETTINGS_PATCH, return_value=settings),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_VIDEO_PATCH) as mock_video,
        patch(_UPLOAD_IMAGE_PATCH) as mock_image,
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/magnific",
            content=body,
            headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
        )

    assert resp.status_code == 200
    mock_image.delay.assert_called_once()
    mock_video.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Unknown provider defaults to video
# ---------------------------------------------------------------------------


def test_unknown_provider_defaults_to_video() -> None:
    """The _PROVIDER_MEDIA_TYPE mapping defaults to 'video' for unknown providers."""
    from vos_studio_mcp.routes.webhooks import _PROVIDER_MEDIA_TYPE

    media_type = _PROVIDER_MEDIA_TYPE.get("unknown_provider", "video")
    assert media_type == "video"


# ---------------------------------------------------------------------------
# Failed status does NOT trigger any upload task
# ---------------------------------------------------------------------------


def test_higgsfield_failed_does_not_trigger_upload() -> None:
    """Failed status must not enqueue any upload task."""
    body = json.dumps({
        "generation_id": "gen-hf-002",
        "status": "FAILED",
        "output": {},
    }).encode()
    settings = Settings(HIGGSFIELD_API_KEY="test-key", WEBHOOK_SECRET_HIGGSFIELD="wh-secret")
    session_ctx = _mock_session()

    with (
        patch(_HIGGSFIELD_SETTINGS_PATCH, return_value=settings),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_VIDEO_PATCH) as mock_video,
        patch(_UPLOAD_IMAGE_PATCH) as mock_image,
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200
    mock_video.delay.assert_not_called()
    mock_image.delay.assert_not_called()


def test_freepik_failed_does_not_trigger_upload() -> None:
    """Failed Freepik status must not enqueue any upload task."""
    body = json.dumps({
        "id": "fpk-task-002",
        "status": "FAILED",
        "generated": [],
    }).encode()
    settings = Settings(FREEPIK_API_KEY="test-key", WEBHOOK_SECRET_FREEPIK="freepik-secret")
    session_ctx = _mock_session()

    with (
        patch(_FREEPIK_SETTINGS_PATCH, return_value=settings),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_VIDEO_PATCH) as mock_video,
        patch(_UPLOAD_IMAGE_PATCH) as mock_image,
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/freepik",
            content=body,
            headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
        )

    assert resp.status_code == 200
    mock_video.delay.assert_not_called()
    mock_image.delay.assert_not_called()


def test_magnific_failed_does_not_trigger_upload() -> None:
    """Failed Magnific status must not enqueue any upload task."""
    body = json.dumps({
        "id": "mag-job-002",
        "status": "failed",
        "output_url": None,
    }).encode()
    settings = Settings(MAGNIFIC_API_KEY="test-key", WEBHOOK_SECRET_MAGNIFIC="magnific-secret")
    session_ctx = _mock_session()

    with (
        patch(_MAGNIFIC_SETTINGS_PATCH, return_value=settings),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_VIDEO_PATCH) as mock_video,
        patch(_UPLOAD_IMAGE_PATCH) as mock_image,
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/magnific",
            content=body,
            headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
        )

    assert resp.status_code == 200
    mock_video.delay.assert_not_called()
    mock_image.delay.assert_not_called()
