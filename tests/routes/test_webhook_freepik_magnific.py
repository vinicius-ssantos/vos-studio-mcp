"""Unit tests for POST /webhooks/freepik and /webhooks/magnific (ADR-0028, Issue #27)."""

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.routes.webhooks import router

_SESSION_PATCH = "vos_studio_mcp.routes.webhooks.get_session"
_UPLOAD_TASK_PATCH = "vos_studio_mcp.routes.webhooks.upload_video_to_storage"
_FREEPIK_SETTINGS_PATCH = "vos_studio_mcp.services.providers.freepik.get_settings"
_MAGNIFIC_SETTINGS_PATCH = "vos_studio_mcp.services.providers.magnific.get_settings"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _freepik_settings(secret: str = "freepik-secret") -> Settings:
    return Settings(FREEPIK_API_KEY="test-key", WEBHOOK_SECRET_FREEPIK=secret)


def _magnific_settings(secret: str = "magnific-secret") -> Settings:
    return Settings(MAGNIFIC_API_KEY="test-key", WEBHOOK_SECRET_MAGNIFIC=secret)


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


# ===========================================================================
# FREEPIK
# ===========================================================================


def _freepik_payload(**kwargs: Any) -> bytes:
    base: dict[str, Any] = {
        "id": "fpk-task-123",
        "status": "COMPLETED",
        "generated": [{"url": "https://cdn.freepik.com/image.jpg"}],
    }
    base.update(kwargs)
    return json.dumps(base).encode()


class TestFreepikWebhook:
    def test_invalid_signature_returns_403(self) -> None:
        body = _freepik_payload()
        with patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()), TestClient(_app()) as c:
            resp = c.post(
                "/webhooks/freepik",
                content=body,
                headers={"X-Freepik-Signature": "sha256=badhash"},
            )
        assert resp.status_code == 403

    def test_missing_signature_returns_403(self) -> None:
        body = _freepik_payload()
        with patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()), TestClient(_app()) as c:
            resp = c.post("/webhooks/freepik", content=body)
        assert resp.status_code == 403

    def test_completed_updates_status_and_enqueues_upload(self) -> None:
        body = _freepik_payload(status="COMPLETED")
        session_ctx = _mock_session()
        asset = session_ctx.__aenter__.return_value.get.return_value

        with (
            patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            patch(_UPLOAD_TASK_PATCH) as mock_upload,
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/freepik",
                content=body,
                headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
            )

        assert resp.status_code == 200
        assert resp.json() == {"received": True}
        assert asset.generation_status == "completed"
        assert asset.storage_status == "pending"
        mock_upload.delay.assert_called_once()

    def test_failed_status_updates_generation_status(self) -> None:
        body = _freepik_payload(status="FAILED", generated=[])
        session_ctx = _mock_session()
        asset = session_ctx.__aenter__.return_value.get.return_value

        with (
            patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/freepik",
                content=body,
                headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
            )

        assert resp.status_code == 200
        assert asset.generation_status == "failed"
        assert asset.storage_url is None

    def test_uses_taskid_field_as_fallback(self) -> None:
        """Support 'taskId' as an alternative to 'id' in Freepik payload."""
        body = json.dumps({
            "taskId": "fpk-alt-456",
            "status": "COMPLETED",
            "generated": [{"url": "https://cdn.freepik.com/alt.jpg"}],
        }).encode()
        session_ctx = _mock_session()

        with (
            patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            patch(_UPLOAD_TASK_PATCH),
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/freepik",
                content=body,
                headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
            )

        assert resp.status_code == 200

    def test_unknown_job_returns_200(self) -> None:
        body = _freepik_payload()
        session_ctx = _mock_session(found=False)

        with (
            patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/freepik",
                content=body,
                headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
            )

        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_invalid_json_returns_200(self) -> None:
        body = b"not-valid-json{"
        with patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()), TestClient(_app()) as c:
            resp = c.post(
                "/webhooks/freepik",
                content=body,
                headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
            )
        assert resp.status_code == 200

    def test_unknown_status_returns_200(self) -> None:
        body = _freepik_payload(status="UNKNOWN_STATE")
        with patch(_FREEPIK_SETTINGS_PATCH, return_value=_freepik_settings()), TestClient(_app()) as c:
            resp = c.post(
                "/webhooks/freepik",
                content=body,
                headers={"X-Freepik-Signature": _sig("freepik-secret", body)},
            )
        assert resp.status_code == 200


# ===========================================================================
# MAGNIFIC
# ===========================================================================


def _magnific_payload(**kwargs: Any) -> bytes:
    base: dict[str, Any] = {
        "id": "mag-job-789",
        "status": "completed",
        "output_url": "https://cdn.magnific.ai/upscaled.jpg",
    }
    base.update(kwargs)
    return json.dumps(base).encode()


class TestMagnificWebhook:
    def test_invalid_signature_returns_403(self) -> None:
        body = _magnific_payload()
        with patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()), TestClient(_app()) as c:
            resp = c.post(
                "/webhooks/magnific",
                content=body,
                headers={"X-Magnific-Signature": "sha256=badhash"},
            )
        assert resp.status_code == 403

    def test_missing_signature_returns_403(self) -> None:
        body = _magnific_payload()
        with patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()), TestClient(_app()) as c:
            resp = c.post("/webhooks/magnific", content=body)
        assert resp.status_code == 403

    def test_completed_updates_status_and_enqueues_upload(self) -> None:
        body = _magnific_payload(status="completed")
        session_ctx = _mock_session()
        asset = session_ctx.__aenter__.return_value.get.return_value

        with (
            patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            patch(_UPLOAD_TASK_PATCH) as mock_upload,
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/magnific",
                content=body,
                headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
            )

        assert resp.status_code == 200
        assert resp.json() == {"received": True}
        assert asset.generation_status == "completed"
        assert asset.storage_status == "pending"
        mock_upload.delay.assert_called_once()

    def test_failed_status_updates_generation_status(self) -> None:
        body = _magnific_payload(status="failed", output_url=None)
        session_ctx = _mock_session()
        asset = session_ctx.__aenter__.return_value.get.return_value

        with (
            patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/magnific",
                content=body,
                headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
            )

        assert resp.status_code == 200
        assert asset.generation_status == "failed"
        assert asset.storage_url is None

    def test_uses_url_field_as_fallback(self) -> None:
        """Support 'url' as an alternative to 'output_url' in Magnific payload."""
        body = json.dumps({
            "id": "mag-alt-999",
            "status": "completed",
            "url": "https://cdn.magnific.ai/alt.jpg",
        }).encode()
        session_ctx = _mock_session()

        with (
            patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            patch(_UPLOAD_TASK_PATCH),
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/magnific",
                content=body,
                headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
            )

        assert resp.status_code == 200

    def test_uses_job_id_field_as_fallback(self) -> None:
        """Support 'job_id' as an alternative to 'id' in Magnific payload."""
        body = json.dumps({
            "job_id": "mag-jobid-111",
            "status": "completed",
            "output_url": "https://cdn.magnific.ai/img.jpg",
        }).encode()
        session_ctx = _mock_session()

        with (
            patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            patch(_UPLOAD_TASK_PATCH),
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/magnific",
                content=body,
                headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
            )

        assert resp.status_code == 200

    def test_unknown_job_returns_200(self) -> None:
        body = _magnific_payload()
        session_ctx = _mock_session(found=False)

        with (
            patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()),
            patch(_SESSION_PATCH, return_value=session_ctx),
            TestClient(_app()) as c,
        ):
            resp = c.post(
                "/webhooks/magnific",
                content=body,
                headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
            )

        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_invalid_json_returns_200(self) -> None:
        body = b"not-valid-json{"
        with patch(_MAGNIFIC_SETTINGS_PATCH, return_value=_magnific_settings()), TestClient(_app()) as c:
            resp = c.post(
                "/webhooks/magnific",
                content=body,
                headers={"X-Magnific-Signature": _sig("magnific-secret", body)},
            )
        assert resp.status_code == 200
