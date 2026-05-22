"""JWT validation via JWKS using joserfc (ADR-0019)."""

import logging
import time
from typing import Any

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.registry import Header

log = logging.getLogger(__name__)

_jwks_cache: dict[str, KeySet] = {}

_ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]


def validate_bearer_token(token: str, issuer_url: str) -> str | None:
    """Validate a JWT against the issuer's JWKS. Returns client_id or None."""
    try:
        key_set = _fetch_key_set(issuer_url)
        decoded = jwt.decode(token, key_set, algorithms=_ALLOWED_ALGORITHMS)
        claims: dict[str, Any] = decoded.claims
        _check_expiry(claims)
        client_id: str | None = claims.get("client_id") or claims.get("sub")
        return client_id
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


def _fetch_key_set(issuer_url: str) -> KeySet:
    if issuer_url in _jwks_cache:
        return _jwks_cache[issuer_url]
    jwks_uri = f"{issuer_url.rstrip('/')}/.well-known/jwks.json"
    response = httpx.get(jwks_uri, timeout=5.0)
    response.raise_for_status()
    key_set = KeySet.import_key_set(response.json())
    _jwks_cache[issuer_url] = key_set
    return key_set


def clear_jwks_cache() -> None:
    """Flush the JWKS cache (e.g. after key rotation)."""
    _jwks_cache.clear()


# Suppress unused import — Header is re-exported for tests that need to inspect headers.
__all__ = ["validate_bearer_token", "clear_jwks_cache", "Header"]
