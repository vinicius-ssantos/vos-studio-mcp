"""Unit tests for POST /webhooks/higgsfield (ADR-0028, Issue #6 item B)."""

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.routes.webhooks import router

_ADAPTER_PATCH = "vos_studio_mcp.routes.webhooks.get_adapter"
_SESSION_PATCH = "vos_studio_mcp.routes.webhooks.get_session"
_SETTINGS_PATCH = "vos_studio_mcp.services.providers.higgsfield.get_settings"
_UPLOAD_TASK_PATCH = "vos_studio_mcp.routes.webhooks.upload_video_to_storage"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _settings(secret: str = "wh-secret") -> Settings:
    return Settings(HIGGSFIELD_API_KEY="test-key", WEBHOOK_SECRET_HIGGSFIELD=secret)


def _payload(**kwargs: Any) -> bytes:
    base = {
        "generation_id": "gen-123",
        "status": "COMPLETED",
        "output": {"media_url": "https://cdn.higgsfield.ai/video.mp4", "media_type": "video"},
    }
    base.update(kwargs)
    return json.dumps(base).encode()


def _mock_session(found: bool = True, client_id: str = "00000000-0000-0000-0000-000000000001") -> MagicMock:
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
# signature verification
# ---------------------------------------------------------------------------


def test_invalid_signature_returns_403() -> None:
    body = _payload()
    with patch(_SETTINGS_PATCH, return_value=_settings()), TestClient(_app()) as c:
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": "sha256=badhash"},
        )
    assert resp.status_code == 403


def test_missing_signature_returns_403() -> None:
    body = _payload()
    with patch(_SETTINGS_PATCH, return_value=_settings()), TestClient(_app()) as c:
        resp = c.post("/webhooks/higgsfield", content=body)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# COMPLETED status
# ---------------------------------------------------------------------------


def test_completed_updates_generation_and_storage_status() -> None:
    """Webhook sets generation_status='completed' and storage_status='pending'.

    The CDN URL must NOT be written to storage_url — that belongs to the
    upload task (ADR-0031).
    """
    body = _payload(status="COMPLETED")
    session_ctx = _mock_session()
    asset = session_ctx.__aenter__.return_value.get.return_value

    with (
        patch(_SETTINGS_PATCH, return_value=_settings()),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_TASK_PATCH),
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200
    assert resp.json() == {"received": True}
    assert asset.generation_status == "completed"
    assert asset.storage_status == "pending"  # upload task will handle R2
    assert asset.storage_url is None  # not set by webhook


# ---------------------------------------------------------------------------
# FAILED / ERROR status
# ---------------------------------------------------------------------------


def test_failed_status_updates_generation_status() -> None:
    body = _payload(status="FAILED", output={})
    session_ctx = _mock_session()
    asset = session_ctx.__aenter__.return_value.get.return_value

    with (
        patch(_SETTINGS_PATCH, return_value=_settings()),
        patch(_SESSION_PATCH, return_value=session_ctx),TestClient(_app()) as c
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200
    assert asset.generation_status == "failed"
    assert asset.storage_url is None


def test_error_status_maps_to_failed() -> None:
    body = _payload(status="ERROR", output={})
    session_ctx = _mock_session()
    asset = session_ctx.__aenter__.return_value.get.return_value

    with (
        patch(_SETTINGS_PATCH, return_value=_settings()),
        patch(_SESSION_PATCH, return_value=session_ctx),TestClient(_app()) as c
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200
    assert asset.generation_status == "failed"


# ---------------------------------------------------------------------------
# PROCESSING status
# ---------------------------------------------------------------------------


def test_processing_status_updates_generation_status() -> None:
    body = _payload(status="PROCESSING", output={})
    session_ctx = _mock_session()
    asset = session_ctx.__aenter__.return_value.get.return_value

    with (
        patch(_SETTINGS_PATCH, return_value=_settings()),
        patch(_SESSION_PATCH, return_value=session_ctx),TestClient(_app()) as c
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200
    assert asset.generation_status == "processing"


# ---------------------------------------------------------------------------
# idempotency — unknown job
# ---------------------------------------------------------------------------


def test_unknown_job_id_returns_200() -> None:
    body = _payload(generation_id="gen-unknown")
    session_ctx = _mock_session(found=False)

    with (
        patch(_SETTINGS_PATCH, return_value=_settings()),
        patch(_SESSION_PATCH, return_value=session_ctx),TestClient(_app()) as c
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200
    assert resp.json() == {"received": True}


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------


def test_missing_generation_id_returns_200() -> None:
    body = json.dumps({"status": "COMPLETED"}).encode()
    with patch(_SETTINGS_PATCH, return_value=_settings()), TestClient(_app()) as c:
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )
    assert resp.status_code == 200


def test_unknown_status_returns_200() -> None:
    body = _payload(status="UNKNOWN_STATE")
    with patch(_SETTINGS_PATCH, return_value=_settings()), TestClient(_app()) as c:
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )
    assert resp.status_code == 200


def test_falls_back_to_id_field_for_job_id() -> None:
    """Support 'id' as an alternative to 'generation_id' in payload."""
    body = json.dumps({
        "id": "gen-alt-456",
        "status": "COMPLETED",
        "output": {"media_url": "https://cdn.higgsfield.ai/alt.mp4"},
    }).encode()
    session_ctx = _mock_session()

    with (
        patch(_SETTINGS_PATCH, return_value=_settings()),
        patch(_SESSION_PATCH, return_value=session_ctx),
        patch(_UPLOAD_TASK_PATCH),
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    assert resp.status_code == 200


def test_auth_middleware_skips_webhook_path() -> None:
    """Confirm /webhooks/ is exempt from Bearer token auth."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from vos_studio_mcp.auth.middleware import auth_middleware
    from vos_studio_mcp.config.env import Settings

    app = FastAPI()
    app.middleware("http")(auth_middleware)
    app.include_router(router)

    body = _payload(status="UNKNOWN_STATE")
    settings = Settings(DEV_BEARER_TOKEN="secret", WEBHOOK_SECRET_HIGGSFIELD="wh-secret")

    with (
        patch("vos_studio_mcp.auth.middleware.get_settings", return_value=settings),
        patch(_SETTINGS_PATCH, return_value=settings),
        TestClient(app, raise_server_exceptions=False) as c,
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )

    # No Authorization header needed — auth middleware skips /webhooks/
    assert resp.status_code == 200


def test_invalid_json_body_returns_200() -> None:
    """Body that fails JSON parsing should be tolerated (lines 47-49)."""
    body = b"not-valid-json{"
    with patch(_SETTINGS_PATCH, return_value=_settings()), TestClient(_app()) as c:
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}


def test_asset_none_after_db_lookup_returns_200() -> None:
    """When Asset row is gone by the time we fetch it, respond gracefully (line 90)."""
    body = _payload()

    session_ctx = _mock_session(found=True)
    # Override: row found but asset fetch returns None
    session_ctx.__aenter__.return_value.get = AsyncMock(return_value=None)

    with (
        patch(_SETTINGS_PATCH, return_value=_settings()),
        patch(_SESSION_PATCH, return_value=session_ctx),
        TestClient(_app()) as c,
    ):
        resp = c.post(
            "/webhooks/higgsfield",
            content=body,
            headers={"X-Higgsfield-Signature": _sig("wh-secret", body)},
        )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
