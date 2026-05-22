"""Unit tests for auth middleware and guards (ADR-0019)."""

import contextvars
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vos_studio_mcp.auth.context import get_current_client_id, set_current_client_id
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.auth.middleware import auth_middleware
from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.errors import ErrorCode, VosError

_PATCH = "vos_studio_mcp.auth.middleware.get_settings"


def _app(routes: bool = True) -> FastAPI:
    app = FastAPI()
    app.middleware("http")(auth_middleware)
    if routes:

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/protected")
        async def protected() -> dict[str, str | None]:
            return {"client_id": get_current_client_id()}

    return app


# ---------------------------------------------------------------------------
# /health — always open
# ---------------------------------------------------------------------------


def test_health_no_token_is_open() -> None:
    s = Settings(DEV_BEARER_TOKEN="secret")
    with patch(_PATCH, return_value=s), TestClient(_app(), raise_server_exceptions=False) as c:
        assert c.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# auth disabled (neither issuer nor dev token configured)
# ---------------------------------------------------------------------------


def test_auth_disabled_allows_all_requests() -> None:
    app = _app(routes=False)

    @app.get("/protected")
    async def p() -> dict[str, str]:
        return {"ok": "yes"}

    s = Settings(DEV_BEARER_TOKEN="", OAUTH_ISSUER_URL="")
    with patch(_PATCH, return_value=s), TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/protected").status_code == 200


# ---------------------------------------------------------------------------
# dev bearer token bypass
# ---------------------------------------------------------------------------


def test_dev_token_sets_client_id() -> None:
    captured: list[str | None] = []
    app = _app(routes=False)

    @app.get("/protected")
    async def p() -> dict[str, str | None]:
        captured.append(get_current_client_id())
        return {"client_id": captured[-1]}

    s = Settings(DEV_BEARER_TOKEN="mytoken", DEV_CLIENT_ID="client-abc")
    with patch(_PATCH, return_value=s), TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/protected", headers={"Authorization": "Bearer mytoken"})
    assert resp.status_code == 200
    assert captured[0] == "client-abc"


def test_wrong_token_returns_401() -> None:
    app = _app(routes=False)

    @app.get("/protected")
    async def p() -> dict[str, str]:
        return {"ok": "yes"}

    s = Settings(DEV_BEARER_TOKEN="mytoken", OAUTH_ISSUER_URL="")
    with patch(_PATCH, return_value=s), TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_missing_bearer_returns_401_when_auth_configured() -> None:
    app = _app(routes=False)

    @app.get("/protected")
    async def p() -> dict[str, str]:
        return {"ok": "yes"}

    s = Settings(DEV_BEARER_TOKEN="mytoken")
    with patch(_PATCH, return_value=s), TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/protected")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# assert_owns_client guard
# ---------------------------------------------------------------------------


def test_guard_no_auth_context_passes() -> None:
    def run() -> None:
        assert_owns_client("any-client-id")

    contextvars.Context().run(run)


def test_guard_matching_client_passes() -> None:
    set_current_client_id("client-xyz")
    assert_owns_client("client-xyz")


def test_guard_mismatched_client_raises() -> None:
    set_current_client_id("client-xyz")
    with pytest.raises(VosError) as exc_info:
        assert_owns_client("client-different")
    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


# ---------------------------------------------------------------------------
# auth context ContextVar
# ---------------------------------------------------------------------------


def test_context_var_defaults_to_none_in_fresh_context() -> None:
    result: list[str | None] = []

    def read_ctx() -> None:
        result.append(get_current_client_id())

    contextvars.Context().run(read_ctx)
    assert result[0] is None


def test_context_var_set_and_get() -> None:
    set_current_client_id("acme-123")
    assert get_current_client_id() == "acme-123"
