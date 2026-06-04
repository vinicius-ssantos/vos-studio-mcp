"""Unit tests for JWT validation module (ADR-0019)."""

import time
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from joserfc import jwt as joserfc_jwt
from joserfc.jwk import KeySet, OctKey, RSAKey

from vos_studio_mcp.auth.jwt import (
    _JWKS_TTL,
    clear_jwks_cache,
    validate_bearer_token,
    validate_supabase_token,
)

# Generate test RSA key pair once per module — 2048-bit is acceptable for unit tests.
_TEST_KEY: RSAKey = RSAKey.generate_key(2048)
_TEST_KEYSET: KeySet = KeySet([_TEST_KEY])

_ISSUER = "https://idp.example.com"
_JWKS_URL = f"{_ISSUER}/.well-known/jwks.json"


def _token(claims: dict, alg: str = "RS256", key: RSAKey | OctKey | None = None) -> str:
    k = key if key is not None else _TEST_KEY
    return joserfc_jwt.encode({"alg": alg}, claims, k)


def _jwks() -> dict:
    return _TEST_KEYSET.as_dict(private=False)


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    clear_jwks_cache()
    yield  # type: ignore[misc]
    clear_jwks_cache()


# ---------------------------------------------------------------------------
# claims extraction
# ---------------------------------------------------------------------------


@respx.mock
async def test_returns_client_id_claim() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"client_id": "client-abc", "sub": "user-1", "exp": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER) == "client-abc"


@respx.mock
async def test_prefers_app_metadata_client_id_claim() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({
        "client_id": "legacy-client-abc",
        "sub": "user-1",
        "exp": int(time.time()) + 3600,
        "app_metadata": {"client_id": "brand-client-abc"},
    })
    assert await validate_bearer_token(tok, _ISSUER) == "brand-client-abc"


@respx.mock
async def test_falls_back_to_sub_when_no_client_id() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-xyz", "exp": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER) == "user-xyz"


@respx.mock
async def test_no_exp_claim_is_accepted() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-1"})  # no exp — must succeed
    assert await validate_bearer_token(tok, _ISSUER) == "user-1"


# ---------------------------------------------------------------------------
# rejection paths
# ---------------------------------------------------------------------------


@respx.mock
async def test_returns_none_on_expired_token() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-1", "exp": int(time.time()) - 60})
    assert await validate_bearer_token(tok, _ISSUER) is None


@respx.mock
async def test_returns_none_on_invalid_signature() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    other_key: RSAKey = RSAKey.generate_key(2048)
    tok = _token({"sub": "user-1", "exp": int(time.time()) + 3600}, key=other_key)
    assert await validate_bearer_token(tok, _ISSUER) is None


@respx.mock
async def test_returns_none_on_jwks_fetch_failure() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(500))
    tok = _token({"sub": "user-1", "exp": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER) is None


@respx.mock
async def test_symmetric_algorithm_rejected() -> None:
    """HS256 (symmetric) must not be accepted even with a valid JWKS endpoint."""
    oct_key = OctKey.import_key(b"this-is-a-48-byte-secret-key-for-testing!!!!!")
    tok = joserfc_jwt.encode({"alg": "HS256"}, {"sub": "user-1"}, oct_key)
    # JWKS returns our asymmetric key — the HS256 token won't match any allowed alg.
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    assert await validate_bearer_token(tok, _ISSUER) is None


@respx.mock
async def test_returns_none_when_nbf_in_future() -> None:
    """A token whose not-before is in the future must be rejected."""
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-1", "nbf": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER) is None


# ---------------------------------------------------------------------------
# audience validation (opt-in via OAUTH_AUDIENCE)
# ---------------------------------------------------------------------------


@respx.mock
async def test_audience_not_checked_when_not_configured() -> None:
    """With no expected audience, the aud claim is ignored (backward compatible)."""
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-1", "aud": "some-other-api", "exp": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER) == "user-1"


@respx.mock
async def test_audience_match_accepted() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-1", "aud": "vos-mcp", "exp": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER, "vos-mcp") == "user-1"


@respx.mock
async def test_audience_match_accepted_when_aud_is_list() -> None:
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-1", "aud": ["a", "vos-mcp"], "exp": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER, "vos-mcp") == "user-1"


@respx.mock
async def test_audience_mismatch_rejected() -> None:
    """A token minted for another resource (different aud) must be rejected."""
    respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "user-1", "aud": "other-api", "exp": int(time.time()) + 3600})
    assert await validate_bearer_token(tok, _ISSUER, "vos-mcp") is None


# ---------------------------------------------------------------------------
# JWKS TTL cache
# ---------------------------------------------------------------------------


@respx.mock
async def test_cache_hit_avoids_second_fetch() -> None:
    route = respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "u1", "exp": int(time.time()) + 3600})

    await validate_bearer_token(tok, _ISSUER)
    await validate_bearer_token(tok, _ISSUER)

    assert route.call_count == 1


@respx.mock
async def test_cache_refreshes_after_ttl() -> None:
    route = respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "u1", "exp": int(time.time()) + 7200})

    await validate_bearer_token(tok, _ISSUER)

    future = time.monotonic() + _JWKS_TTL + 1
    with patch("vos_studio_mcp.auth.jwt.time") as mock_time:
        mock_time.monotonic.return_value = future
        mock_time.time.side_effect = time.time  # keep expiry check working
        await validate_bearer_token(tok, _ISSUER)

    assert route.call_count == 2


@respx.mock
async def test_clear_cache_forces_refetch() -> None:
    route = respx.get(_JWKS_URL).mock(return_value=Response(200, json=_jwks()))
    tok = _token({"sub": "u1", "exp": int(time.time()) + 3600})

    await validate_bearer_token(tok, _ISSUER)
    clear_jwks_cache()
    await validate_bearer_token(tok, _ISSUER)

    assert route.call_count == 2


@respx.mock
async def test_different_issuers_cached_independently() -> None:
    issuer_b = "https://other-idp.example.com"
    route_a = respx.get(f"{_ISSUER}/.well-known/jwks.json").mock(
        return_value=Response(200, json=_jwks())
    )
    route_b = respx.get(f"{issuer_b}/.well-known/jwks.json").mock(
        return_value=Response(200, json=_jwks())
    )
    tok = _token({"sub": "u1", "exp": int(time.time()) + 3600})

    await validate_bearer_token(tok, _ISSUER)
    await validate_bearer_token(tok, issuer_b)
    # Second call to each — both should hit cache
    await validate_bearer_token(tok, _ISSUER)
    await validate_bearer_token(tok, issuer_b)

    assert route_a.call_count == 1
    assert route_b.call_count == 1


# ---------------------------------------------------------------------------
# validate_supabase_token — Supabase HS256 mode
# ---------------------------------------------------------------------------

_SUPABASE_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"


def _supabase_token(claims: dict) -> str:
    key = OctKey.import_key(_SUPABASE_SECRET.encode("utf-8"))
    return joserfc_jwt.encode({"alg": "HS256"}, claims, key)


def test_supabase_returns_sub_for_authenticated_user() -> None:
    tok = _supabase_token({"sub": "user-uuid-1", "role": "authenticated", "exp": int(time.time()) + 3600})
    assert validate_supabase_token(tok, _SUPABASE_SECRET) == "user-uuid-1"


def test_supabase_prefers_app_metadata_client_id() -> None:
    tok = _supabase_token({
        "sub": "user-uuid-2",
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
        "app_metadata": {"client_id": "brand-client-abc"},
    })
    assert validate_supabase_token(tok, _SUPABASE_SECRET) == "brand-client-abc"


def test_supabase_rejects_anon_role() -> None:
    tok = _supabase_token({"sub": "user-uuid-3", "role": "anon", "exp": int(time.time()) + 3600})
    assert validate_supabase_token(tok, _SUPABASE_SECRET) is None


def test_supabase_rejects_service_role() -> None:
    tok = _supabase_token({"sub": "service", "role": "service_role", "exp": int(time.time()) + 3600})
    assert validate_supabase_token(tok, _SUPABASE_SECRET) is None


def test_supabase_rejects_expired_token() -> None:
    tok = _supabase_token({"sub": "user-1", "role": "authenticated", "exp": int(time.time()) - 60})
    assert validate_supabase_token(tok, _SUPABASE_SECRET) is None


def test_supabase_rejects_wrong_secret() -> None:
    tok = _supabase_token({"sub": "user-1", "role": "authenticated", "exp": int(time.time()) + 3600})
    assert validate_supabase_token(tok, "wrong-secret-that-is-long-enough-for-hs256") is None
