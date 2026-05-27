"""Tests for server.py — FastAPI application wiring and entrypoint."""

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
