"""Bearer token auth middleware (ADR-0019)."""

import hmac
import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from vos_studio_mcp.auth.context import set_current_client_id
from vos_studio_mcp.auth.jwt import validate_bearer_token, validate_supabase_token
from vos_studio_mcp.auth.oauth_native import validate_access_token
from vos_studio_mcp.config.env import get_settings

log = logging.getLogger(__name__)

_OPEN_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-authorization-server/mcp",
    "/oauth/register",
    "/oauth/authorize",
    "/oauth/token",
    "/oauth/consent",
}
_OPEN_PREFIXES = ("/webhooks/",)


async def auth_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Validate bearer token and inject client_id into request context."""
    path = request.url.path
    if path in _OPEN_PATHS or path.startswith(_OPEN_PREFIXES):
        return await call_next(request)

    settings = get_settings()
    auth_required = bool(
        settings.mcp_oauth_signing_key
        or settings.oauth_issuer_url
        or settings.supabase_jwt_secret
        or settings.dev_bearer_token
    )

    if not auth_required:
        if settings.is_production:
            log.error(
                "auth.not_configured_in_production",
                extra={"path": path},
            )
            return JSONResponse(
                {"error": "service_unavailable", "detail": "Authentication not configured"},
                status_code=503,
            )
        log.warning("auth_disabled — no OAUTH_ISSUER_URL, SUPABASE_JWT_SECRET, or DEV_BEARER_TOKEN configured")
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        response = JSONResponse(
            {"error": "unauthorized", "detail": "Bearer token required"},
            status_code=401,
        )
        base_url = settings.mcp_public_base_url or str(request.base_url).rstrip("/")
        resource_metadata_path = "/.well-known/oauth-protected-resource"
        if path.startswith("/mcp"):
            resource_metadata_path = "/.well-known/oauth-protected-resource/mcp"
        scope = "mcp" if settings.mcp_oauth_signing_key else "openid profile email"
        response.headers["WWW-Authenticate"] = (
            f'Bearer resource_metadata="{base_url}{resource_metadata_path}", '
            f'scope="{scope}"'
        )
        return response

    token = auth_header[7:]

    if settings.dev_bearer_token and hmac.compare_digest(token, settings.dev_bearer_token):
        set_current_client_id(settings.dev_client_id)
        return await call_next(request)

    client_id: str | None = None

    native_claims = validate_access_token(token, settings)
    if native_claims is not None:
        # Native MCP OAuth authenticates the private owner/operator, not a
        # specific VOS domain client. Leave tenant unset so client-scoped
        # service guards use explicit tool input until per-client grants exist.
        set_current_client_id(None)
        return await call_next(request)
    elif settings.oauth_issuer_url:
        # JWKS mode (RS/ES) — takes precedence when configured.
        client_id = await validate_bearer_token(
            token, settings.oauth_issuer_url, settings.oauth_audience or None
        )
    elif settings.supabase_jwt_secret:
        # Supabase HS256 mode — used when only the symmetric JWT secret is configured.
        client_id = validate_supabase_token(token, settings.supabase_jwt_secret)

    if client_id is None:
        return JSONResponse({"error": "unauthorized", "detail": "Invalid or expired token"}, status_code=401)

    set_current_client_id(client_id)
    return await call_next(request)
