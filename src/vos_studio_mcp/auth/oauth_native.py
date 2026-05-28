"""Native OAuth 2.1 helpers for ChatGPT MCP connectors."""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from vos_studio_mcp.config.env import Settings

DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 3600
DEFAULT_AUTH_CODE_TTL_SECONDS = 300
CLIENT_ID_PREFIX = "mcp-client-"
ACCESS_TOKEN_PREFIX = "mcp."


@dataclass(frozen=True)
class RegisteredClient:
    """Dynamically registered public OAuth client."""

    client_id: str
    redirect_uris: tuple[str, ...]
    client_id_issued_at: int
    token_endpoint_auth_method: str = "none"


@dataclass(frozen=True)
class AuthorizationCode:
    """Short-lived authorization code tied to a PKCE challenge."""

    code: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    scope: str
    resource: str
    expires_at: int


class OAuthState:
    """In-memory OAuth state for a single Railway instance."""

    def __init__(self) -> None:
        self.clients: dict[str, RegisteredClient] = {}
        self.authorization_codes: dict[str, AuthorizationCode] = {}
        self._consumed_code_cache: dict[str, tuple[dict[str, Any], int]] = {}

    def register_client(
        self,
        *,
        redirect_uris: list[str],
        settings: Settings,
        token_endpoint_auth_method: str = "none",
    ) -> RegisteredClient:
        """Register a public OAuth client using deterministic signed client IDs."""
        if token_endpoint_auth_method != "none":
            raise ValueError("Only public OAuth clients are supported")
        if not redirect_uris:
            raise ValueError("At least one redirect URI is required")

        issued_at = int(time.time())
        safe_redirect_uris = tuple(validate_redirect_uris(redirect_uris, settings))
        client = RegisteredClient(
            client_id=sign_client_id(
                redirect_uris=list(safe_redirect_uris),
                settings=settings,
                token_endpoint_auth_method=token_endpoint_auth_method,
            ),
            redirect_uris=safe_redirect_uris,
            client_id_issued_at=issued_at,
            token_endpoint_auth_method=token_endpoint_auth_method,
        )
        self.clients[client.client_id] = client
        return client

    def get_client(self, client_id: str, settings: Settings) -> RegisteredClient | None:
        """Return a cached or reconstructed signed client."""
        cached = self.clients.get(client_id)
        if cached is not None:
            return cached
        return validate_client_id(client_id, settings)

    def issue_authorization_code(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        scope: str,
        resource: str,
        settings: Settings,
    ) -> AuthorizationCode:
        """Issue a short-lived authorization code."""
        validate_code_challenge_method(code_challenge_method)
        requested_resource = validate_resource(resource, settings)
        code = secrets.token_urlsafe(32)
        auth_code = AuthorizationCode(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            resource=requested_resource,
            expires_at=int(time.time()) + settings.mcp_oauth_auth_code_ttl_seconds,
        )
        self.authorization_codes[code] = auth_code
        return auth_code

    def consume_authorization_code(self, code: str) -> AuthorizationCode | None:
        """Consume an authorization code once."""
        auth_code = self.authorization_codes.pop(code, None)
        if auth_code is None or auth_code.expires_at < int(time.time()):
            return None
        return auth_code

    def cache_consumed_code_response(self, code: str, response: dict[str, Any]) -> None:
        """Cache token response briefly for duplicate token requests."""
        self._consumed_code_cache[code] = (dict(response), int(time.time()) + 30)

    def get_cached_token_response(self, code: str) -> dict[str, Any] | None:
        """Return a cached token response for duplicate code exchange."""
        entry = self._consumed_code_cache.get(code)
        if entry is None:
            return None
        response, expires_at = entry
        if int(time.time()) > expires_at:
            self._consumed_code_cache.pop(code, None)
            return None
        return dict(response)


oauth_state = OAuthState()


def issuer_url(settings: Settings) -> str:
    """Return the native OAuth issuer origin."""
    return (settings.mcp_oauth_issuer_url or settings.mcp_public_base_url).rstrip("/")


def resource_url(settings: Settings) -> str:
    """Return the MCP resource URL."""
    return f"{issuer_url(settings)}/mcp"


def protected_resource_metadata(settings: Settings) -> dict[str, Any]:
    """Build OAuth protected-resource metadata."""
    issuer = issuer_url(settings)
    return {
        "resource": resource_url(settings),
        "resource_name": "VOS Studio MCP",
        "authorization_servers": [issuer],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp"],
    }


def authorization_server_metadata(settings: Settings) -> dict[str, Any]:
    """Build OAuth authorization-server metadata."""
    issuer = issuer_url(settings)
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "registration_endpoint": f"{issuer}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
        "resource_indicators_supported": True,
    }


def registration_response(client: RegisteredClient) -> dict[str, Any]:
    """Return RFC 7591-style dynamic registration response."""
    return {
        "client_id": client.client_id,
        "client_id_issued_at": client.client_id_issued_at,
        "redirect_uris": list(client.redirect_uris),
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
    }


def authorization_redirect_url(*, redirect_uri: str, code: str, state: str | None) -> str:
    """Build OAuth authorization redirect URL."""
    params = {"code": code}
    if state:
        params["state"] = state
    return f"{redirect_uri}?{urlencode(params)}"


def sign_access_token(
    *,
    client_id: str,
    scope: str,
    resource: str,
    settings: Settings,
) -> str:
    """Create a signed opaque-looking MCP access token."""
    now = int(time.time())
    payload = {
        "client_id": client_id,
        "scope": scope,
        "aud": validate_resource(resource, settings),
        "iat": now,
        "exp": now + settings.mcp_oauth_access_token_ttl_seconds,
    }
    encoded_payload = _json_b64url(payload)
    encoded_signature = _hmac_b64url(encoded_payload, settings)
    return f"{ACCESS_TOKEN_PREFIX}{encoded_payload}.{encoded_signature}"


def validate_access_token(token: str, settings: Settings) -> dict[str, Any] | None:
    """Validate a native MCP access token and return claims."""
    if not settings.mcp_oauth_signing_key or not token.startswith(ACCESS_TOKEN_PREFIX):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    _, encoded_payload, encoded_signature = parts
    expected = _hmac_b64url(encoded_payload, settings)
    if not hmac.compare_digest(encoded_signature, expected):
        return None
    try:
        decoded_payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(decoded_payload, dict):
        return None
    payload: dict[str, Any] = decoded_payload
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    try:
        expected_resource = validate_resource(str(payload.get("aud", "")), settings)
    except ValueError:
        return None
    if payload.get("aud") != expected_resource:
        return None
    return payload


def token_response(*, access_token: str, settings: Settings) -> dict[str, Any]:
    """Return OAuth token endpoint response."""
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.mcp_oauth_access_token_ttl_seconds,
        "scope": "mcp",
    }


def sign_client_id(
    *,
    redirect_uris: list[str],
    settings: Settings,
    token_endpoint_auth_method: str = "none",
) -> str:
    """Sign redirect metadata into a deterministic dynamic client ID."""
    if token_endpoint_auth_method != "none":
        raise ValueError("Only public OAuth clients are supported")
    safe_redirect_uris = validate_redirect_uris(redirect_uris, settings)
    payload = {
        "redirect_uris": safe_redirect_uris,
        "token_endpoint_auth_method": token_endpoint_auth_method,
    }
    encoded_payload = _json_b64url(payload)
    encoded_signature = _hmac_b64url(encoded_payload, settings)
    return f"{CLIENT_ID_PREFIX}{encoded_payload}.{encoded_signature}"


def validate_client_id(client_id: str, settings: Settings) -> RegisteredClient | None:
    """Validate and reconstruct a signed dynamic client ID."""
    if not client_id.startswith(CLIENT_ID_PREFIX):
        return None
    signed_value = client_id[len(CLIENT_ID_PREFIX) :]
    parts = signed_value.split(".")
    if len(parts) != 2:
        return None
    encoded_payload, encoded_signature = parts
    expected = _hmac_b64url(encoded_payload, settings)
    if not hmac.compare_digest(encoded_signature, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
        redirect_uris = tuple(validate_redirect_uris(list(payload["redirect_uris"]), settings))
        token_endpoint_auth_method = str(payload.get("token_endpoint_auth_method", "none"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if token_endpoint_auth_method != "none":
        return None
    return RegisteredClient(
        client_id=client_id,
        redirect_uris=redirect_uris,
        client_id_issued_at=0,
        token_endpoint_auth_method=token_endpoint_auth_method,
    )


def validate_redirect_uris(redirect_uris: list[str], settings: Settings) -> list[str]:
    """Validate redirect URIs against HTTPS/localhost and optional allowlist."""
    safe_uris: list[str] = []
    allowed_patterns = [
        pattern.strip()
        for pattern in settings.mcp_oauth_allowed_redirect_uris.split(",")
        if pattern.strip()
    ]
    for uri in redirect_uris:
        value = str(uri).strip()
        if not value.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("Redirect URI must use HTTPS or localhost HTTP")
        if allowed_patterns and not any(fnmatch.fnmatch(value, pattern) for pattern in allowed_patterns):
            raise ValueError("Redirect URI not allowed")
        safe_uris.append(value)
    return safe_uris


def validate_resource(resource: str, settings: Settings) -> str:
    """Validate OAuth resource indicator."""
    value = str(resource).strip().rstrip("/")
    expected = resource_url(settings)
    if value != expected:
        raise ValueError("Unsupported OAuth resource")
    return value


def validate_code_challenge_method(method: str) -> None:
    """Only PKCE S256 is supported."""
    if method != "S256":
        raise ValueError("Only PKCE S256 is supported")


def verify_pkce(*, code_verifier: str, code_challenge: str, method: str) -> bool:
    """Validate PKCE code verifier against the stored challenge."""
    validate_code_challenge_method(method)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = _b64url_encode(digest)
    return hmac.compare_digest(computed, code_challenge)


def verify_owner_approval_secret(value: str | None, settings: Settings) -> bool:
    """Check owner approval form secret."""
    expected = settings.mcp_oauth_authorization_secret
    if not expected or not value:
        return False
    return hmac.compare_digest(value, expected)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _json_b64url(payload: dict[str, Any]) -> str:
    return _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _hmac_b64url(message: str, settings: Settings) -> str:
    key = settings.mcp_oauth_signing_key
    if not key:
        raise RuntimeError("MCP_OAUTH_SIGNING_KEY is required")
    digest = hmac.new(key.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)
