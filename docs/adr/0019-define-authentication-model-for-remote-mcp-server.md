# ADR-0019 — Define authentication model for the remote MCP server

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22, 2026-05-22

## Context

ADR-0002 decided that VOS Studio MCP will be a remote HTTP server exposed at `https://mcp.vosstudio.com/mcp`. That endpoint will receive connections from external AI agents (Claude, ChatGPT, Codex) and potentially from multiple users or clients.

Exposing an MCP server on the public internet without an explicit authentication model is a critical security gap. Any unauthenticated endpoint could be called by unauthorized agents, leak client data, trigger paid provider actions, or bypass the approval controls defined in ADR-0005.

The MCP spec supports an OAuth 2.1 authorization flow for remote servers. The server can also be protected at the transport layer using simpler mechanisms such as static bearer tokens or mTLS.

## Decision

**Phase 1 (implemented — Milestone 5):** Delegate token issuance entirely to an external identity provider (IdP) such as Supabase Auth or Auth0. The MCP server acts only as a resource server: it validates Bearer tokens issued by the IdP by fetching the IdP's JWKS endpoint and verifying the JWT signature and expiry claims.

JWT validation is implemented using **`joserfc`** (not `authlib`, which deprecated its JOSE API). The primary allowed algorithms are `RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512`.

The validated `client_id` claim (falling back to `sub`) is stored in an async `ContextVar` for the duration of the request, so downstream service calls and guards can enforce ownership without re-parsing the token.

**Development bypass:** a `DEV_BEARER_TOKEN` environment variable enables a static token for local development and CI. When this token is presented, the server sets `client_id` to the value of `DEV_CLIENT_ID` (defaults to a fixed UUID). This bypass must never be configured in production.

**Phase 2 (implemented — Supabase Auth integration):** Two validation modes are now supported:

### Mode 1 — JWKS / RS256 (primary)

Configured via `OAUTH_ISSUER_URL`. The server fetches `{issuer}/.well-known/jwks.json` on first use, caches the `KeySet` for 10 minutes (TTL-based, auto-refreshes on expiry), and validates tokens using only asymmetric algorithms (`RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512`).

For Supabase: enable RS256 keys under Project Settings → Auth → JWT Settings. Set `OAUTH_ISSUER_URL=https://<project>.supabase.co/auth/v1`.

### Mode 2 — Supabase HS256 (opt-in fallback)

Configured via `SUPABASE_JWT_SECRET` (the project's JWT Secret from Project Settings → API). Uses `joserfc` with `HS256` and the symmetric secret. This mode is provided specifically for standard Supabase projects that have not enabled RS256.

**Security scope of Mode 2:** the JWT secret is a server-side-only secret — it is never shared with clients or exposed in responses. Mode 2 is therefore acceptable under controlled conditions even though HS256 is generally rejected for shared-secret reasons. If `OAUTH_ISSUER_URL` is also set, JWKS (Mode 1) takes precedence unconditionally.

**Role enforcement (Mode 2 only):** Supabase tokens with `role=anon` or `role=service_role` are rejected. Only `role=authenticated` is accepted. This prevents API keys (`anon`/`service_role`) from being used to call MCP tools.

**`client_id` extraction (Mode 2):** `app_metadata.client_id` takes precedence over `sub`. Operators can assign a brand `client_id` to a Supabase user via `app_metadata` without changing the user's UUID.

**Phase 3 (future):** If VOS Studio MCP is ever embedded in an AI platform that supports the full MCP OAuth 2.1 flow (authorization code + PKCE), the server can be fronted by the IdP acting as an authorization server. No code changes to the resource-server validation logic should be needed for this transition.

Every request to the MCP server must include a valid Bearer token. Unauthenticated requests return `401 Unauthorized` and must not execute any tool or expose any data. Paths `/health`, `/docs`, `/openapi.json`, and `/redoc` are exempt.

## Alternatives considered

- **Build a full OAuth 2.1 authorization server in-process**: correct but disproportionate complexity for Milestone 5. Deferred to Phase 3 or delegated permanently to an external IdP.
- **No authentication (IP allowlist only)**: rejected. IP allowlists are brittle and do not provide per-user or per-client granularity.
- **API key per user (no JWT)**: simpler than OAuth, but provides no standard claims (`sub`, `client_id`) that services can use for RLS. Rejected as primary model.
- **mTLS**: strong but operationally complex for connecting external AI agents that do not support client certificates natively.
- **`authlib` JOSE**: deprecated its JWT API in v1.x. Replaced by `joserfc`, which has a stable, explicit API and supports the same algorithms.
- **HS256 allowed globally**: rejected. HS256 is only allowed via explicit `SUPABASE_JWT_SECRET` as a controlled exception for Supabase defaults; it is not accepted via the JWKS path.

## Consequences

The JWKS cache now has a 10-minute TTL and refreshes automatically — key rotation at the IdP is handled without process restarts. `clear_jwks_cache()` remains available for immediate cache invalidation.

Token scopes are not validated in Phase 2 — only signature, expiry, and (in Mode 2) Supabase role are checked. Scope enforcement is a Phase 3 item.

## Implementation

- `src/vos_studio_mcp/auth/jwt.py` — `validate_bearer_token` (JWKS/async), `validate_supabase_token` (HS256/sync), TTL cache
- `src/vos_studio_mcp/auth/middleware.py` — Mode 1 vs Mode 2 routing; JWKS takes precedence
- `src/vos_studio_mcp/auth/context.py` — `ContextVar[str | None]` for the authenticated `client_id`
- `src/vos_studio_mcp/auth/guards.py` — `assert_owns_client(input_client_id)` guard used in services
- `src/vos_studio_mcp/config/env.py` — `OAUTH_ISSUER_URL`, `SUPABASE_JWT_SECRET`, `DEV_BEARER_TOKEN`, `DEV_CLIENT_ID`
- `tests/auth/test_jwt.py` — 30 unit tests covering both modes, TTL cache, role enforcement

## Impact on VOS Studio MCP

- Production: configure either `OAUTH_ISSUER_URL` (Mode 1, recommended) or `SUPABASE_JWT_SECRET` (Mode 2, Supabase default projects).
- All MCP tool handlers validate the authenticated identity via `assert_owns_client` in services (not in tools).
- `app_metadata.client_id` on the Supabase user record controls which brand/client that user can access in Mode 2.
- Static bearer tokens for development must be clearly marked as non-production in code and documentation.
