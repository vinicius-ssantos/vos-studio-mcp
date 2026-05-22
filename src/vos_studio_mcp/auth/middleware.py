"""Bearer token auth middleware (ADR-0019)."""

import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from vos_studio_mcp.auth.context import set_current_client_id
from vos_studio_mcp.auth.jwt import validate_bearer_token
from vos_studio_mcp.config.env import get_settings

log = logging.getLogger(__name__)

_OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


async def auth_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Validate bearer token and inject client_id into request context."""
    if request.url.path in _OPEN_PATHS:
        return await call_next(request)

    settings = get_settings()
    auth_required = bool(settings.oauth_issuer_url or settings.dev_bearer_token)

    if not auth_required:
        log.warning("auth_disabled — no OAUTH_ISSUER_URL or DEV_BEARER_TOKEN configured")
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "unauthorized", "detail": "Bearer token required"}, status_code=401)

    token = auth_header[7:]

    if settings.dev_bearer_token and token == settings.dev_bearer_token:
        set_current_client_id(settings.dev_client_id)
        return await call_next(request)

    if not settings.oauth_issuer_url:
        return JSONResponse({"error": "unauthorized", "detail": "Invalid token"}, status_code=401)

    client_id = validate_bearer_token(token, settings.oauth_issuer_url)
    if client_id is None:
        return JSONResponse({"error": "unauthorized", "detail": "Invalid or expired token"}, status_code=401)

    set_current_client_id(client_id)
    return await call_next(request)
