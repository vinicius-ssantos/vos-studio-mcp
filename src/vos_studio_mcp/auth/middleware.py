"""Bearer token auth middleware (ADR-0019)."""

import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from vos_studio_mcp.auth.context import set_current_client_id
from vos_studio_mcp.auth.jwt import validate_bearer_token, validate_supabase_token
from vos_studio_mcp.config.env import get_settings

log = logging.getLogger(__name__)

_OPEN_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}
_OPEN_PREFIXES = ("/webhooks/",)


async def auth_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Validate bearer token and inject client_id into request context."""
    path = request.url.path
    if path in _OPEN_PATHS or path.startswith(_OPEN_PREFIXES):
        return await call_next(request)

    settings = get_settings()
    auth_required = bool(
        settings.oauth_issuer_url or settings.supabase_jwt_secret or settings.dev_bearer_token
    )

    if not auth_required:
        log.warning("auth_disabled — no OAUTH_ISSUER_URL, SUPABASE_JWT_SECRET, or DEV_BEARER_TOKEN configured")
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "unauthorized", "detail": "Bearer token required"}, status_code=401)

    token = auth_header[7:]

    if settings.dev_bearer_token and token == settings.dev_bearer_token:
        set_current_client_id(settings.dev_client_id)
        return await call_next(request)

    client_id: str | None = None

    if settings.oauth_issuer_url:
        # JWKS mode (RS/ES) — takes precedence when configured.
        client_id = await validate_bearer_token(token, settings.oauth_issuer_url)
    elif settings.supabase_jwt_secret:
        # Supabase HS256 mode — used when only the symmetric JWT secret is configured.
        client_id = validate_supabase_token(token, settings.supabase_jwt_secret)

    if client_id is None:
        return JSONResponse({"error": "unauthorized", "detail": "Invalid or expired token"}, status_code=401)

    set_current_client_id(client_id)
    return await call_next(request)
