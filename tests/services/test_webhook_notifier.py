"""Unit tests for outbound webhook notifier (Issue #33)."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.services.webhook_notifier import (
    _build_payload,
    _sign_payload,
    notify_job_completed,
    notify_job_failed,
)

_WEBHOOK_URL = "https://example.com/hooks/vos"
_ASSET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_SPRINT_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_CLIENT_ID = "cccccccc-0000-0000-0000-000000000003"
_SECRET = "test-secret-abc123"

_SETTINGS_PATH = "vos_studio_mcp.services.webhook_notifier.get_settings"


class TestBuildPayload:
    def test_event_and_schema_version(self) -> None:
        p = _build_payload("asset.completed", _ASSET_ID, _SPRINT_ID, _CLIENT_ID, "completed", "stored", "https://r2/vid.mp4", "job-123")
        assert p["event"] == "asset.completed"
        assert p["schema_version"] == "1"

    def test_all_fields_present(self) -> None:
        p = _build_payload("asset.failed", _ASSET_ID, _SPRINT_ID, _CLIENT_ID, "failed", "failed", None, "job-456")
        assert p["asset_id"] == _ASSET_ID
        assert p["sprint_id"] == _SPRINT_ID
        assert p["client_id"] == _CLIENT_ID
        assert p["generation_status"] == "failed"
        assert p["storage_status"] == "failed"
        assert p["storage_url"] is None
        assert p["provider_job_id"] == "job-456"
        assert "timestamp" in p


class TestSignPayload:
    def test_produces_sha256_prefix(self) -> None:
        sig = _sign_payload(b"hello", "secret")
        assert sig.startswith("sha256=")

    def test_hmac_is_correct(self) -> None:
        body = b'{"event":"test"}'
        secret = "my-secret"
        expected_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        sig = _sign_payload(body, secret)
        assert sig == f"sha256={expected_hex}"


class TestNotifyJobCompleted:
    @pytest.mark.asyncio
    async def test_posts_to_webhook_url(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock()
        settings.outbound_webhook_secret = _SECRET

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID,
                sprint_id=_SPRINT_ID,
                client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL,
                storage_url="https://r2/vid.mp4",
                provider_job_id="job-123",
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[0][0] == _WEBHOOK_URL

    @pytest.mark.asyncio
    async def test_payload_contains_completed_event(self) -> None:
        captured_body: list[bytes] = []

        mock_response = MagicMock(is_success=True)
        mock_client = AsyncMock()

        async def _post(url: str, content: bytes, headers: dict) -> MagicMock:
            captured_body.append(content)
            return mock_response

        mock_client.post = _post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret=_SECRET)

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url="https://r2/v.mp4",
                provider_job_id="job-1",
            )

        payload = json.loads(captured_body[0])
        assert payload["event"] == "asset.completed"
        assert payload["generation_status"] == "completed"
        assert payload["storage_status"] == "stored"

    @pytest.mark.asyncio
    async def test_signature_header_is_sent_when_secret_configured(self) -> None:
        captured_headers: list[dict] = []

        mock_response = MagicMock(is_success=True)
        mock_client = AsyncMock()

        async def _post(url: str, content: bytes, headers: dict) -> MagicMock:
            captured_headers.append(headers)
            return mock_response

        mock_client.post = _post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret=_SECRET)

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url=None, provider_job_id=None,
            )

        assert "X-VOS-Signature" in captured_headers[0]
        assert captured_headers[0]["X-VOS-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_no_signature_header_when_secret_empty(self) -> None:
        captured_headers: list[dict] = []

        mock_response = MagicMock(is_success=True)
        mock_client = AsyncMock()

        async def _post(url: str, content: bytes, headers: dict) -> MagicMock:
            captured_headers.append(headers)
            return mock_response

        mock_client.post = _post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret="")

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url=None, provider_job_id=None,
            )

        assert "X-VOS-Signature" not in captured_headers[0]

    @pytest.mark.asyncio
    async def test_network_error_is_swallowed(self) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret=_SECRET)

        # Must not raise
        with patch(_SETTINGS_PATH, return_value=settings), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url=None, provider_job_id=None,
            )


class TestNotifyJobFailed:
    @pytest.mark.asyncio
    async def test_payload_event_is_asset_failed(self) -> None:
        captured_body: list[bytes] = []

        mock_response = MagicMock(is_success=True)
        mock_client = AsyncMock()

        async def _post(url: str, content: bytes, headers: dict) -> MagicMock:
            captured_body.append(content)
            return mock_response

        mock_client.post = _post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret="")

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_failed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, provider_job_id="job-456",
            )

        payload = json.loads(captured_body[0])
        assert payload["event"] == "asset.failed"
        assert payload["generation_status"] == "failed"


# ---------------------------------------------------------------------------
# SSRF guard integration (Issue #47)
# ---------------------------------------------------------------------------


class TestSsrfGuardIntegration:
    """_deliver must call check_webhook_url and swallow the error gracefully."""

    @pytest.mark.asyncio
    async def test_private_ip_url_is_swallowed_in_notify_completed(self) -> None:
        """notify_job_completed must swallow VosError from the SSRF guard."""
        from vos_studio_mcp.errors import ErrorCode, VosError
        from vos_studio_mcp.services.webhook_notifier import notify_job_completed

        with patch(
            "vos_studio_mcp.services.webhook_notifier.check_webhook_url",
            side_effect=VosError(ErrorCode.INVALID_INPUT, "SSRF blocked"),
        ):
            # Must NOT raise — SSRF violation is treated like a delivery error
            await notify_job_completed(
                asset_id=_ASSET_ID,
                sprint_id=_SPRINT_ID,
                client_id=_CLIENT_ID,
                webhook_url="https://10.0.0.1/hook",
                storage_url=None,
                provider_job_id=None,
            )

    @pytest.mark.asyncio
    async def test_ssrf_guard_called_before_http_request(self) -> None:
        """The SSRF guard must run before any HTTP request is attempted."""
        from vos_studio_mcp.errors import ErrorCode, VosError
        from vos_studio_mcp.services.webhook_notifier import notify_job_completed

        mock_http = AsyncMock()

        with patch(
            "vos_studio_mcp.services.webhook_notifier.check_webhook_url",
            side_effect=VosError(ErrorCode.INVALID_INPUT, "SSRF blocked"),
        ), patch(
            "vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient",
            return_value=mock_http,
        ):
            await notify_job_completed(
                asset_id=_ASSET_ID,
                sprint_id=_SPRINT_ID,
                client_id=_CLIENT_ID,
                webhook_url="https://10.0.0.1/hook",
                storage_url=None,
                provider_job_id=None,
            )

        # HTTP client must never be used when SSRF guard blocks
        mock_http.__aenter__ = AsyncMock()
        mock_http.post.assert_not_called()
