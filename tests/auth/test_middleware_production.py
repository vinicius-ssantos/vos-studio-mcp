"""Tests for fail-closed auth behavior in production (Issue #62)."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.auth.middleware import auth_middleware
from vos_studio_mcp.config.env import Settings

_PATCH = "vos_studio_mcp.auth.middleware.get_settings"


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(auth_middleware)

    @app.get("/protected")
    async def protected() -> dict[str, str | None]:
        return {"client_id": get_current_client_id()}

    return app


# ---------------------------------------------------------------------------
# Development mode — no auth configured → requests pass through
# ---------------------------------------------------------------------------


def test_development_no_auth_allows_requests() -> None:
    """In development mode with no auth config, requests are allowed through."""
    s = Settings(APP_ENV="development", DEV_BEARER_TOKEN="", OAUTH_ISSUER_URL="", SUPABASE_JWT_SECRET="")
    with patch(_PATCH, return_value=s), TestClient(_app(), raise_server_exceptions=False) as c:
        resp = c.get("/protected")
    assert resp.status_code == 200


def test_development_default_env_no_auth_allows_requests() -> None:
    """Default APP_ENV is development; requests pass through when auth is unconfigured."""
    s = Settings(DEV_BEARER_TOKEN="", OAUTH_ISSUER_URL="", SUPABASE_JWT_SECRET="")
    assert not s.is_production
    with patch(_PATCH, return_value=s), TestClient(_app(), raise_server_exceptions=False) as c:
        resp = c.get("/protected")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Production mode — no auth configured → 503
# ---------------------------------------------------------------------------


def test_production_no_auth_returns_503() -> None:
    """In production mode with no auth config, ALL requests must be rejected with 503."""
    s = Settings(APP_ENV="production", DEV_BEARER_TOKEN="", OAUTH_ISSUER_URL="", SUPABASE_JWT_SECRET="")
    with patch(_PATCH, return_value=s), TestClient(_app(), raise_server_exceptions=False) as c:
        resp = c.get("/protected")
    assert resp.status_code == 503
    body = resp.json()
    assert "Authentication not configured" in body.get("detail", "")


def test_production_no_auth_returns_503_for_any_path() -> None:
    """503 is returned regardless of path when auth is not configured in production."""
    s = Settings(APP_ENV="production", DEV_BEARER_TOKEN="", OAUTH_ISSUER_URL="", SUPABASE_JWT_SECRET="")
    app = FastAPI()
    app.middleware("http")(auth_middleware)

    @app.get("/api/tools")
    async def tools() -> dict[str, str]:
        return {"ok": "yes"}

    with patch(_PATCH, return_value=s), TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/api/tools")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Production mode — WITH auth configured → requests processed normally
# ---------------------------------------------------------------------------


def test_production_with_dev_bearer_token_processes_requests() -> None:
    """In production mode WITH a dev bearer token, auth validation runs normally."""
    s = Settings(
        APP_ENV="production",
        DEV_BEARER_TOKEN="prod-secret-token",
        DEV_CLIENT_ID="client-prod-001",
        OAUTH_ISSUER_URL="",
        SUPABASE_JWT_SECRET="",
    )
    with patch(_PATCH, return_value=s), TestClient(_app(), raise_server_exceptions=False) as c:
        resp = c.get("/protected", headers={"Authorization": "Bearer prod-secret-token"})
    assert resp.status_code == 200


def test_production_with_bearer_token_wrong_token_returns_401() -> None:
    """In production WITH auth configured, wrong token gives 401 (not 503)."""
    s = Settings(
        APP_ENV="production",
        DEV_BEARER_TOKEN="prod-secret-token",
        OAUTH_ISSUER_URL="",
        SUPABASE_JWT_SECRET="",
    )
    with patch(_PATCH, return_value=s), TestClient(_app(), raise_server_exceptions=False) as c:
        resp = c.get("/protected", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# APP_ENV=prod (short form) — treated as production
# ---------------------------------------------------------------------------


def test_prod_short_form_treated_as_production() -> None:
    """APP_ENV=prod (short form) must trigger the production fail-closed behavior."""
    s = Settings(APP_ENV="prod", DEV_BEARER_TOKEN="", OAUTH_ISSUER_URL="", SUPABASE_JWT_SECRET="")
    assert s.is_production is True
    with patch(_PATCH, return_value=s), TestClient(_app(), raise_server_exceptions=False) as c:
        resp = c.get("/protected")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Open paths remain open even in production with no auth
# ---------------------------------------------------------------------------


def test_open_paths_bypass_auth_check_in_production() -> None:
    """/health must always be accessible regardless of auth config or environment."""
    s = Settings(APP_ENV="production", DEV_BEARER_TOKEN="", OAUTH_ISSUER_URL="", SUPABASE_JWT_SECRET="")
    app = FastAPI()
    app.middleware("http")(auth_middleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    with patch(_PATCH, return_value=s), TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/health")
    assert resp.status_code == 200
