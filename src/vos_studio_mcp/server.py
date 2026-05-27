"""FastAPI/FastMCP application entrypoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from urllib.parse import urlparse

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from mcp.server.fastmcp import FastMCP
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from vos_studio_mcp.auth.middleware import auth_middleware
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import VosError
from vos_studio_mcp.observability.logging import configure_logging
from vos_studio_mcp.observability.metrics import metrics_response
from vos_studio_mcp.observability.middleware import (
    correlation_middleware,
    metrics_instrumentation_middleware,
)
from vos_studio_mcp.resources.playbook import register_resources_and_prompts
from vos_studio_mcp.routes.webhooks import router as webhooks_router
from vos_studio_mcp.services.status import get_health
from vos_studio_mcp.tools import register_tools

log = logging.getLogger(__name__)

settings = get_settings()
configure_logging(settings.log_level)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration(), CeleryIntegration()],
        send_default_pii=False,
    )

if settings.is_production and not (
    settings.oauth_issuer_url or settings.supabase_jwt_secret or settings.dev_bearer_token
):
    log.warning(
        "auth.not_configured_in_production — set OAUTH_ISSUER_URL, SUPABASE_JWT_SECRET, or DEV_BEARER_TOKEN"
    )

mcp = FastMCP(settings.mcp_server_name, streamable_http_path="/")
register_tools(mcp)
register_resources_and_prompts(mcp)


def _get_mcp_app(mcp_server: FastMCP) -> Any:
    """Return the FastMCP ASGI app supported by the installed SDK."""
    streamable_http_app = getattr(mcp_server, "streamable_http_app", None)
    if callable(streamable_http_app):
        return streamable_http_app()

    sse_app = getattr(mcp_server, "sse_app", None)
    if callable(sse_app):
        return sse_app()

    return None


mcp_app = _get_mcp_app(mcp)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start the FastMCP Streamable HTTP session manager with the FastAPI app."""
    session_manager = getattr(mcp, "_session_manager", None)
    if (
        mcp_app is not None
        and session_manager is not None
        and not getattr(session_manager, "_has_started", False)
    ):
        async with mcp.session_manager.run():
            yield
        return

    yield


app = FastAPI(title=settings.mcp_server_name, debug=settings.debug, lifespan=lifespan)


@app.middleware("http")
async def tunnel_host_header_middleware(request: Request, call_next: Any) -> Response:
    """Normalize tunneled Host headers for the mounted FastMCP app.

    Some MCP SDK transports validate the incoming Host header. When the local
    server is reached through a public HTTPS tunnel, the external Host differs
    from the local ASGI origin. Keep the original host in x-forwarded-host and
    pass a local host to the mounted app.
    """
    public_base_url = settings.mcp_public_base_url
    if public_base_url:
        public_host = urlparse(public_base_url).netloc
        if request.url.path.startswith("/mcp") and request.headers.get("host") == public_host:
            headers = []
            has_forwarded_host = False
            for key, value in request.scope["headers"]:
                key_l = key.lower()
                if key_l == b"host":
                    headers.append((key, f"127.0.0.1:{settings.mcp_server_port}".encode()))
                else:
                    headers.append((key, value))
                if key_l == b"x-forwarded-host":
                    has_forwarded_host = True
            if not has_forwarded_host:
                headers.append((b"x-forwarded-host", public_host.encode()))
            request.scope["headers"] = headers

    response: Response = await call_next(request)
    return response


# Middleware executes in reverse registration order:
# metrics_instrumentation runs outermost, then correlation, then auth.
app.middleware("http")(auth_middleware)
app.middleware("http")(correlation_middleware)
app.middleware("http")(metrics_instrumentation_middleware)
# Webhook routes bypass auth middleware via _OPEN_PREFIXES in auth/middleware.py
app.include_router(webhooks_router)


@app.exception_handler(VosError)
async def vos_error_handler(_request: Request, exc: VosError) -> JSONResponse:
    """Translate domain errors into compact structured JSON (ADR-0011, ADR-0030)."""
    log.warning("vos_error", extra={"error_code": exc.error_code, "error_message": exc.message})
    return JSONResponse(
        status_code=400,
        content={"error_code": exc.error_code, "message": exc.message},
    )


@app.get("/health")
async def health() -> dict[str, object]:
    """Return a detailed health check with per-component status.

    Overall status:
    - "ok"       — all components healthy
    - "degraded" — celery worker unreachable (web still serves)
    - "down"     — database or Redis unavailable
    """
    result = await get_health()
    return result.model_dump()


@app.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics for scraping.

    Returns standard Prometheus text format with:
    - vos_http_requests_total
    - vos_http_request_duration_seconds
    - vos_provider_calls_total
    - vos_circuit_breaker_open
    - vos_mcp_tool_calls_total
    """
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)


def _public_base_url(request: Request) -> str:
    """Return the public resource origin used in OAuth metadata."""
    return settings.mcp_public_base_url or str(request.base_url).rstrip("/")


def _oauth_issuer_url() -> str:
    """Return the delegated OAuth issuer URL, if configured."""
    if settings.oauth_issuer_url:
        return settings.oauth_issuer_url
    if settings.supabase_url:
        return f"{settings.supabase_url.rstrip('/')}/auth/v1"
    return ""


@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata(request: Request) -> dict[str, object]:
    """Advertise OAuth protection for remote MCP clients (ADR-0019)."""
    return _oauth_protected_resource_metadata(request, resource_path="")


@app.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_protected_mcp_resource_metadata(request: Request) -> dict[str, object]:
    """Advertise path-specific OAuth protection for the mounted MCP endpoint."""
    return _oauth_protected_resource_metadata(request, resource_path="/mcp")


def _oauth_protected_resource_metadata(
    request: Request,
    *,
    resource_path: str,
) -> dict[str, object]:
    """Build OAuth protected resource metadata."""
    issuer = _oauth_issuer_url()
    authorization_servers = [issuer] if issuer else []
    resource = f"{_public_base_url(request)}{resource_path}"
    return {
        "resource": resource,
        "resource_name": "VOS Studio MCP",
        "authorization_servers": authorization_servers,
        "scopes_supported": ["openid", "profile", "email"],
        "bearer_methods_supported": ["header"],
    }


@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata() -> dict[str, object]:
    """Expose delegated IdP metadata at the resource origin for client compatibility."""
    issuer = _oauth_issuer_url()
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer.rstrip('/')}/oauth/authorize" if issuer else "",
        "token_endpoint": f"{issuer.rstrip('/')}/oauth/token" if issuer else "",
        "jwks_uri": f"{issuer.rstrip('/')}/.well-known/jwks.json" if issuer else "",
        "scopes_supported": ["openid", "profile", "email"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
            "none",
        ],
    }


@app.get("/oauth/consent", response_class=HTMLResponse)
async def oauth_consent_page(request: Request) -> HTMLResponse:
    """Render the Supabase OAuth consent UI for external OAuth clients."""
    authorization_id = request.query_params.get("authorization_id", "")
    if not settings.supabase_url or not settings.supabase_publishable_key:
        return HTMLResponse(
            "<h1>OAuth consent unavailable</h1>"
            "<p>SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured.</p>",
            status_code=500,
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Authorize VOS Studio MCP</title>
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8fafc;
      color: #111827;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    main {{
      width: min(560px, 100%);
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
    }}
    h1 {{ margin: 0 0 8px; font-size: 22px; }}
    p {{ line-height: 1.5; color: #4b5563; }}
    label {{ display: block; margin-top: 14px; font-weight: 600; font-size: 14px; }}
    input {{
      width: 100%;
      box-sizing: border-box;
      margin-top: 6px;
      padding: 10px 12px;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      font: inherit;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
      background: #111827;
      color: white;
    }}
    button.secondary {{ background: #e5e7eb; color: #111827; }}
    .actions {{ display: flex; gap: 10px; margin-top: 20px; }}
    .panel {{
      margin-top: 16px;
      padding: 14px;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      background: #f9fafb;
    }}
    .error {{ color: #b91c1c; }}
    .muted {{ color: #6b7280; font-size: 13px; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <main>
    <h1>Authorize VOS Studio MCP</h1>
    <p id="status">Loading authorization request...</p>

    <section id="login" hidden>
      <p>Sign in with the Supabase account allowed to use this MCP server.</p>
      <label>Email<input id="email" type="email" autocomplete="email"></label>
      <label>Password<input id="password" type="password" autocomplete="current-password"></label>
      <div class="actions">
        <button id="login-button" type="button">Sign in</button>
      </div>
    </section>

    <section id="consent" hidden>
      <div class="panel">
        <p><strong>Client:</strong> <span id="client-name"></span></p>
        <p><strong>Redirect URI:</strong> <code id="redirect-uri"></code></p>
        <p><strong>Scopes:</strong> <code id="scopes"></code></p>
      </div>
      <p class="muted">Approve only if this request came from the ChatGPT connector you are configuring.</p>
      <div class="actions">
        <button id="approve-button" type="button">Authorize</button>
        <button id="deny-button" class="secondary" type="button">Deny</button>
      </div>
    </section>
  </main>

  <script>
    const SUPABASE_URL = {settings.supabase_url!r};
    const SUPABASE_KEY = {settings.supabase_publishable_key!r};
    const AUTHORIZATION_ID = {authorization_id!r};
    const client = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
    const statusEl = document.getElementById("status");
    const loginEl = document.getElementById("login");
    const consentEl = document.getElementById("consent");

    function setStatus(message, isError = false) {{
      statusEl.textContent = message;
      statusEl.className = isError ? "error" : "";
    }}

    async function loadAuthorization() {{
      if (!AUTHORIZATION_ID) {{
        setStatus("Missing authorization_id.", true);
        return;
      }}

      const {{ data: sessionData }} = await client.auth.getSession();
      if (!sessionData.session) {{
        setStatus("Sign in to continue.");
        loginEl.hidden = false;
        consentEl.hidden = true;
        return;
      }}

      const {{ data, error }} = await client.auth.oauth.getAuthorizationDetails(AUTHORIZATION_ID);
      if (error) {{
        setStatus(error.message || "Invalid authorization request.", true);
        return;
      }}

      if (data.redirect_to || data.redirect_url) {{
        window.location.href = data.redirect_to || data.redirect_url;
        return;
      }}

      document.getElementById("client-name").textContent =
        data.client?.name || data.client?.client_name || data.client?.id || "Unknown client";
      document.getElementById("redirect-uri").textContent = data.redirect_uri || "";
      document.getElementById("scopes").textContent = data.scope || "";
      setStatus("Review and authorize this OAuth request.");
      loginEl.hidden = true;
      consentEl.hidden = false;
    }}

    document.getElementById("login-button").addEventListener("click", async () => {{
      setStatus("Signing in...");
      const email = document.getElementById("email").value;
      const password = document.getElementById("password").value;
      const {{ error }} = await client.auth.signInWithPassword({{ email, password }});
      if (error) {{
        setStatus(error.message, true);
        return;
      }}
      await loadAuthorization();
    }});

    document.getElementById("approve-button").addEventListener("click", async () => {{
      setStatus("Authorizing...");
      const {{ data, error }} = await client.auth.oauth.approveAuthorization(AUTHORIZATION_ID);
      if (error) {{
        setStatus(error.message, true);
        return;
      }}
      window.location.href = data.redirect_to || data.redirect_url;
    }});

    document.getElementById("deny-button").addEventListener("click", async () => {{
      setStatus("Denying...");
      const {{ data, error }} = await client.auth.oauth.denyAuthorization(AUTHORIZATION_ID);
      if (error) {{
        setStatus(error.message, true);
        return;
      }}
      window.location.href = data.redirect_to || data.redirect_url;
    }});

    loadAuthorization();
  </script>
</body>
</html>"""
    return HTMLResponse(html)


def _mount_mcp_app(
    fastapi_app: FastAPI,
    mcp_server: FastMCP,
    asgi_app: Any | None = None,
) -> None:
    """Mount the FastMCP ASGI app when supported by the installed SDK."""
    app_to_mount = asgi_app if asgi_app is not None else _get_mcp_app(mcp_server)
    if app_to_mount is not None:
        fastapi_app.mount("/mcp", cast(Any, app_to_mount))


_mount_mcp_app(app, mcp, mcp_app)

if __name__ == "__main__":
    mcp.run()
