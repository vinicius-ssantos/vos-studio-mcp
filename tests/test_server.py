"""Tests for server.py — FastAPI application wiring and entrypoint."""

import base64
import hashlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from vos_studio_mcp.errors import ErrorCode, VosError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(**kwargs: object) -> MagicMock:
    s = MagicMock()
    s.mcp_server_name = "test-mcp"
    s.debug = False
    s.log_level = "WARNING"
    s.sentry_dsn = None
    s.sentry_environment = "test"
    s.sentry_traces_sample_rate = 0.0
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_status() -> None:
    from vos_studio_mcp.server import app

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "service" in body


def test_oauth_protected_resource_metadata() -> None:
    from vos_studio_mcp.server import app

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/.well-known/oauth-protected-resource")

    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"].startswith("http")
    assert "authorization_servers" in body
    assert "header" in body["bearer_methods_supported"]
    assert body["resource_name"] == "VOS Studio MCP"


def test_oauth_protected_mcp_resource_metadata() -> None:
    from vos_studio_mcp.server import app

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/.well-known/oauth-protected-resource/mcp")

    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"].endswith("/mcp")
    assert "authorization_servers" in body


def test_oauth_authorization_server_metadata() -> None:
    from vos_studio_mcp.server import app

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/.well-known/oauth-authorization-server")

    assert resp.status_code == 200
    body = resp.json()
    assert "authorization_endpoint" in body
    assert "token_endpoint" in body


def test_native_oauth_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    from vos_studio_mcp.server import app, settings

    monkeypatch.setattr(settings, "mcp_public_base_url", "https://vos.example.com")
    monkeypatch.setattr(settings, "mcp_oauth_issuer_url", "https://vos.example.com")
    monkeypatch.setattr(settings, "mcp_oauth_signing_key", "test-signing-key")

    with TestClient(app, raise_server_exceptions=False) as c:
        protected = c.get("/.well-known/oauth-protected-resource/mcp").json()
        auth_server = c.get("/.well-known/oauth-authorization-server").json()

    assert protected["resource"] == "https://vos.example.com/mcp"
    assert protected["authorization_servers"] == ["https://vos.example.com"]
    assert protected["scopes_supported"] == ["mcp"]
    assert auth_server["registration_endpoint"] == "https://vos.example.com/oauth/register"
    assert auth_server["token_endpoint_auth_methods_supported"] == ["none"]


def test_native_oauth_register_authorize_token_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    from vos_studio_mcp.server import app, settings

    monkeypatch.setattr(settings, "mcp_public_base_url", "https://vos.example.com")
    monkeypatch.setattr(settings, "mcp_oauth_issuer_url", "https://vos.example.com")
    monkeypatch.setattr(settings, "mcp_oauth_signing_key", "test-signing-key")
    monkeypatch.setattr(settings, "mcp_oauth_authorization_secret", "approve-me")
    monkeypatch.setattr(
        settings,
        "mcp_oauth_allowed_redirect_uris",
        "https://chatgpt.com/connector/oauth/*",
    )

    redirect_uri = "https://chatgpt.com/connector/oauth/test"
    code_verifier = "verifier-value-for-test"
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    with TestClient(app, raise_server_exceptions=False) as c:
        registered = c.post(
            "/oauth/register",
            json={
                "redirect_uris": [redirect_uri],
                "token_endpoint_auth_method": "none",
            },
        )
        assert registered.status_code == 201
        client_id = registered.json()["client_id"]

        authorize = c.post(
            "/oauth/authorize",
            data={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "mcp",
                "resource": "https://vos.example.com/mcp",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": "state-123",
                "approval": "approve-me",
            },
            follow_redirects=False,
        )
        assert authorize.status_code == 302
        location = authorize.headers["location"]
        assert location.startswith(f"{redirect_uri}?")
        code = location.split("code=", 1)[1].split("&", 1)[0]

        token = c.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code": code,
                "code_verifier": code_verifier,
                "resource": "https://vos.example.com/mcp",
            },
        )

    assert token.status_code == 200
    assert token.json()["access_token"].startswith("mcp.")


# ---------------------------------------------------------------------------
# VosError exception handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vos_error_handler_returns_400() -> None:
    """vos_error_handler must translate VosError into a 400 JSONResponse."""
    from unittest.mock import MagicMock

    from vos_studio_mcp.server import vos_error_handler

    exc = VosError(ErrorCode.NOT_FOUND, "thing not found")
    response = await vos_error_handler(MagicMock(), exc)

    assert response.status_code == 400
    import json
    body = json.loads(response.body)
    assert body["error_code"] == ErrorCode.NOT_FOUND
    assert "not found" in body["message"]


# ---------------------------------------------------------------------------
# _mount_mcp_app — mounts when method is callable
# ---------------------------------------------------------------------------


def test_mount_mcp_app_uses_streamable_http_if_available() -> None:
    from fastapi import FastAPI

    from vos_studio_mcp.server import _mount_mcp_app

    fastapi_app = FastAPI()
    mcp_server = MagicMock()
    mcp_server.streamable_http_app = MagicMock(return_value=MagicMock())

    _mount_mcp_app(fastapi_app, mcp_server)

    mcp_server.streamable_http_app.assert_called_once()


def test_mount_mcp_app_falls_back_to_sse_app() -> None:
    from fastapi import FastAPI

    from vos_studio_mcp.server import _mount_mcp_app

    fastapi_app = FastAPI()
    mcp_server = MagicMock(spec=[])  # no attributes by default
    mcp_server.sse_app = MagicMock(return_value=MagicMock())
    # streamable_http_app not present
    del mcp_server.streamable_http_app

    _mount_mcp_app(fastapi_app, mcp_server)

    mcp_server.sse_app.assert_called_once()


def test_mount_mcp_app_does_nothing_when_no_method_available() -> None:
    from fastapi import FastAPI

    from vos_studio_mcp.server import _mount_mcp_app

    fastapi_app = FastAPI()
    mcp_server = MagicMock(spec=[])  # no methods at all

    # Should not raise
    _mount_mcp_app(fastapi_app, mcp_server)
