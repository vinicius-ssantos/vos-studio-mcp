"""Unit tests for outbound webhook notifier (Issue #33, ADR-0040)."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from vos_studio_mcp.services.webhook_notifier import (
    _build_payload,
    _pin_url_to_ip,
    _sign_payload,
    notify_job_completed,
    notify_job_failed,
)

_WEBHOOK_URL = "https://example.com/hooks/vos"
_ASSET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_SPRINT_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_CLIENT_ID = "cccccccc-0000-0000-0000-000000000003"
_SECRET = "test-secret-abc123"
_PINNED_IP = "93.184.216.34"

_SETTINGS_PATH = "vos_studio_mcp.services.webhook_notifier.get_settings"
_SSRF_GUARD = "vos_studio_mcp.services.webhook_notifier.check_webhook_url"


def _mock_client(response: MagicMock | None = None) -> MagicMock:
    """Return an httpx.AsyncClient mock whose .send() returns *response*."""
    resp = response or MagicMock(is_success=True)
    client = AsyncMock()
    client.send = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


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


class TestPinUrlToIp:
    def test_ipv4_replaces_hostname(self) -> None:
        url, host = _pin_url_to_ip("https://example.com/hook", "93.184.216.34")
        assert url == "https://93.184.216.34/hook"
        assert host == "example.com"

    def test_ipv4_preserves_port(self) -> None:
        url, host = _pin_url_to_ip("https://example.com:8443/hook", "93.184.216.34")
        assert url == "https://93.184.216.34:8443/hook"
        assert host == "example.com"

    def test_ipv6_is_bracketed_in_url(self) -> None:
        url, host = _pin_url_to_ip("https://example.com/hook", "2607:f8b0:4004:800::200e")
        assert url == "https://[2607:f8b0:4004:800::200e]/hook"
        assert host == "example.com"

    def test_preserves_path_and_query(self) -> None:
        url, _ = _pin_url_to_ip("https://example.com/v1/hook?token=abc", "93.184.216.34")
        assert url == "https://93.184.216.34/v1/hook?token=abc"


class TestNotifyJobCompleted:
    @pytest.mark.asyncio
    async def test_posts_to_webhook_url_via_send(self) -> None:
        mock_client = _mock_client()
        settings = MagicMock(outbound_webhook_secret=_SECRET)

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch(_SSRF_GUARD, new=AsyncMock(return_value=_PINNED_IP)), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url="https://r2/vid.mp4",
                provider_job_id="job-123",
            )

        mock_client.send.assert_called_once()
        sent_request: httpx.Request = mock_client.send.call_args[0][0]
        # URL host must be the pinned IP, not the original hostname
        assert sent_request.url.host == _PINNED_IP
        # Host header must still carry the original hostname (ADR-0040)
        assert sent_request.headers["host"] == "example.com"
        # sni_hostname extension for TLS cert verification (ADR-0040)
        assert sent_request.extensions.get("sni_hostname") == b"example.com"

    @pytest.mark.asyncio
    async def test_payload_contains_completed_event(self) -> None:
        captured: list[httpx.Request] = []

        async def _send(req: httpx.Request) -> MagicMock:
            captured.append(req)
            return MagicMock(is_success=True)

        mock_client = AsyncMock()
        mock_client.send = _send
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret=_SECRET)

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch(_SSRF_GUARD, new=AsyncMock(return_value=_PINNED_IP)), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url="https://r2/v.mp4",
                provider_job_id="job-1",
            )

        payload = json.loads(captured[0].content)
        assert payload["event"] == "asset.completed"
        assert payload["generation_status"] == "completed"
        assert payload["storage_status"] == "stored"

    @pytest.mark.asyncio
    async def test_signature_header_is_sent_when_secret_configured(self) -> None:
        captured: list[httpx.Request] = []

        async def _send(req: httpx.Request) -> MagicMock:
            captured.append(req)
            return MagicMock(is_success=True)

        mock_client = AsyncMock()
        mock_client.send = _send
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret=_SECRET)

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch(_SSRF_GUARD, new=AsyncMock(return_value=_PINNED_IP)), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url=None, provider_job_id=None,
            )

        assert "x-vos-signature" in captured[0].headers
        assert captured[0].headers["x-vos-signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_no_signature_header_when_secret_empty(self) -> None:
        captured: list[httpx.Request] = []

        async def _send(req: httpx.Request) -> MagicMock:
            captured.append(req)
            return MagicMock(is_success=True)

        mock_client = AsyncMock()
        mock_client.send = _send
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret="")

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch(_SSRF_GUARD, new=AsyncMock(return_value=_PINNED_IP)), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url=None, provider_job_id=None,
            )

        assert "x-vos-signature" not in captured[0].headers

    @pytest.mark.asyncio
    async def test_network_error_is_swallowed(self) -> None:
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret=_SECRET)

        # Must not raise
        with patch(_SETTINGS_PATH, return_value=settings), \
             patch(_SSRF_GUARD, new=AsyncMock(return_value=_PINNED_IP)), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url=None, provider_job_id=None,
            )


class TestNotifyJobFailed:
    @pytest.mark.asyncio
    async def test_payload_event_is_asset_failed(self) -> None:
        captured: list[httpx.Request] = []

        async def _send(req: httpx.Request) -> MagicMock:
            captured.append(req)
            return MagicMock(is_success=True)

        mock_client = AsyncMock()
        mock_client.send = _send
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret="")

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch(_SSRF_GUARD, new=AsyncMock(return_value=_PINNED_IP)), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_failed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, provider_job_id="job-456",
            )

        payload = json.loads(captured[0].content)
        assert payload["event"] == "asset.failed"
        assert payload["generation_status"] == "failed"


# ---------------------------------------------------------------------------
# SSRF guard integration (Issue #47, ADR-0040)
# ---------------------------------------------------------------------------


class TestSsrfGuardIntegration:
    @pytest.mark.asyncio
    async def test_private_ip_url_is_swallowed_in_notify_completed(self) -> None:
        """notify_job_completed must swallow VosError from the SSRF guard."""
        from vos_studio_mcp.errors import ErrorCode, VosError

        with patch(_SSRF_GUARD, side_effect=VosError(ErrorCode.INVALID_INPUT, "SSRF blocked")):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url="https://10.0.0.1/hook", storage_url=None, provider_job_id=None,
            )

    @pytest.mark.asyncio
    async def test_ssrf_guard_called_before_http_request(self) -> None:
        """The SSRF guard must run before any HTTP request is attempted."""
        from vos_studio_mcp.errors import ErrorCode, VosError

        mock_http = AsyncMock()

        with patch(_SSRF_GUARD, side_effect=VosError(ErrorCode.INVALID_INPUT, "SSRF blocked")), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_http):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url="https://10.0.0.1/hook", storage_url=None, provider_job_id=None,
            )

        mock_http.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_dns_rebinding_mitigated_by_ip_pinning(self) -> None:
        """Delivery must use the IP returned by check_webhook_url, not re-resolve.

        This is the DNS-rebinding regression test required by ADR-0040:
        check_webhook_url validates the hostname and returns a pinned IP;
        _deliver must connect to that IP.  Even if the hostname would resolve
        to a private IP on a second DNS query, the connection uses the
        pre-validated public IP.
        """
        sent_requests: list[httpx.Request] = []
        rebinding_ip = "10.0.0.1"  # what a second DNS lookup could return

        async def _send(req: httpx.Request) -> MagicMock:
            sent_requests.append(req)
            return MagicMock(is_success=True)

        mock_client = AsyncMock()
        mock_client.send = _send
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        settings = MagicMock(outbound_webhook_secret="")

        # SSRF guard validates and returns the public IP (first DNS resolution)
        public_ip = "93.184.216.34"

        with patch(_SETTINGS_PATH, return_value=settings), \
             patch(_SSRF_GUARD, new=AsyncMock(return_value=public_ip)), \
             patch("vos_studio_mcp.services.webhook_notifier.httpx.AsyncClient", return_value=mock_client):
            await notify_job_completed(
                asset_id=_ASSET_ID, sprint_id=_SPRINT_ID, client_id=_CLIENT_ID,
                webhook_url=_WEBHOOK_URL, storage_url=None, provider_job_id=None,
            )

        assert len(sent_requests) == 1
        req = sent_requests[0]
        # The request must target the pinned public IP, not the rebinding IP
        assert req.url.host == public_ip
        assert req.url.host != rebinding_ip
        # And SNI must still reference the original hostname for TLS
        assert req.extensions.get("sni_hostname") == b"example.com"
