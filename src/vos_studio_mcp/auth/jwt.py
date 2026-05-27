"""JWT validation via JWKS using joserfc (ADR-0019)."""

import logging
import time
from typing import Any

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet, OctKey
from joserfc.registry import Header

log = logging.getLogger(__name__)

_JWKS_TTL = 600  # seconds — re-fetch JWKS after 10 min to support key rotation
_jwks_cache: dict[str, tuple[KeySet, float]] = {}  # issuer_url → (keyset, fetched_at)

_ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
_SUPABASE_ROLE_CLAIM = "role"
_SUPABASE_REQUIRED_ROLE = "authenticated"


# ---------------------------------------------------------------------------
# JWKS-based validation (RS/ES — primary path for OAuth 2.1 IdPs)
# ---------------------------------------------------------------------------


async def validate_bearer_token(token: str, issuer_url: str) -> str | None:
    """Validate a JWT against the issuer's JWKS endpoint. Returns client_id or None."""
    try:
        key_set = await _fetch_key_set(issuer_url)
        decoded = jwt.decode(token, key_set, algorithms=_ALLOWED_ALGORITHMS)
        claims: dict[str, Any] = decoded.claims
        _check_expiry(claims)
        return _extract_client_id(claims)
    except JoseError as exc:
        log.warning("jwt validation failed", extra={"reason": str(exc)})
        return None
    except Exception as exc:
        log.warning("jwt validation error", extra={"reason": str(exc)})
        return None


def _check_expiry(claims: dict[str, Any]) -> None:
    exp = claims.get("exp")
    if exp is not None and int(exp) < int(time.time()):
        raise ValueError("token expired")


async def _fetch_key_set(issuer_url: str) -> KeySet:
    cached = _jwks_cache.get(issuer_url)
    if cached is not None:
        key_set, fetched_at = cached
        if time.monotonic() - fetched_at < _JWKS_TTL:
            return key_set

    jwks_uri = f"{issuer_url.rstrip('/')}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(jwks_uri)
        response.raise_for_status()
        key_set = KeySet.import_key_set(response.json())

    _jwks_cache[issuer_url] = (key_set, time.monotonic())
    return key_set


def clear_jwks_cache() -> None:
    """Flush the JWKS cache (e.g. after key rotation)."""
    _jwks_cache.clear()


# ---------------------------------------------------------------------------
# Supabase HS256 validation (symmetric — opt-in via SUPABASE_JWT_SECRET)
# ---------------------------------------------------------------------------


def validate_supabase_token(token: str, jwt_secret: str) -> str | None:
    """Validate a Supabase-issued HS256 JWT using the project's JWT secret.

    Only accepts tokens with role=authenticated. Extracts client_id from
    app_metadata.client_id if present, otherwise falls back to sub (user UUID).
    """
    try:
        oct_key = OctKey.import_key(jwt_secret.encode("utf-8"))
        decoded = jwt.decode(token, oct_key, algorithms=["HS256"])
        claims: dict[str, Any] = decoded.claims
        _check_expiry(claims)
        _check_supabase_role(claims)
        return _extract_supabase_client_id(claims)
    except JoseError as exc:
        log.warning("supabase jwt validation failed", extra={"reason": str(exc)})
        return None
    except Exception as exc:
        log.warning("supabase jwt validation error", extra={"reason": str(exc)})
        return None


def _check_supabase_role(claims: dict[str, Any]) -> None:
    role = claims.get(_SUPABASE_ROLE_CLAIM)
    if role != _SUPABASE_REQUIRED_ROLE:
        raise ValueError(f"rejected Supabase role: {role!r}")


def _extract_client_id(claims: dict[str, Any]) -> str | None:
    app_meta: dict[str, Any] = claims.get("app_metadata") or {}
    return app_meta.get("client_id") or claims.get("client_id") or claims.get("sub")


def _extract_supabase_client_id(claims: dict[str, Any]) -> str | None:
    return _extract_client_id(claims)


# Suppress unused import — Header is re-exported for tests that need to inspect headers.
__all__ = ["validate_bearer_token", "validate_supabase_token", "clear_jwks_cache", "Header"]
