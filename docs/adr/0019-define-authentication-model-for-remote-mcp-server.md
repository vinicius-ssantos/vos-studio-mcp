# ADR-0019 — Define authentication model for the remote MCP server

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22

## Context

ADR-0002 decided that VOS Studio MCP will be a remote HTTP server exposed at `https://mcp.vosstudio.com/mcp`. That endpoint will receive connections from external AI agents (Claude, ChatGPT, Codex) and potentially from multiple users or clients.

Exposing an MCP server on the public internet without an explicit authentication model is a critical security gap. Any unauthenticated endpoint could be called by unauthorized agents, leak client data, trigger paid provider actions, or bypass the approval controls defined in ADR-0005.

The MCP spec supports an OAuth 2.1 authorization flow for remote servers. The server can also be protected at the transport layer using simpler mechanisms such as static bearer tokens or mTLS.

## Decision

**Phase 1 (implemented — Milestone 5):** Delegate token issuance entirely to an external identity provider (IdP) such as Supabase Auth or Auth0. The MCP server acts only as a resource server: it validates Bearer tokens issued by the IdP by fetching the IdP's JWKS endpoint and verifying the JWT signature and expiry claims.

JWT validation is implemented using **`joserfc`** (not `authlib`, which deprecated its JOSE API). Allowed signing algorithms are `RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512` — symmetric algorithms (`HS256`, etc.) are rejected to prevent shared-secret attacks.

The validated `client_id` claim (falling back to `sub`) is stored in an async `ContextVar` for the duration of the request, so downstream service calls and guards can enforce ownership without re-parsing the token.

**Development bypass:** a `DEV_BEARER_TOKEN` environment variable enables a static token for local development and CI. When this token is presented, the server sets `client_id` to the value of `DEV_CLIENT_ID` (defaults to a fixed UUID). This bypass must never be configured in production.

**Phase 2 (deferred):** If VOS Studio MCP is ever embedded in an AI platform that supports the full MCP OAuth 2.1 flow (authorization code + PKCE), the server can be fronted by the IdP acting as an authorization server. No code changes to the resource-server validation logic should be needed for this transition.

Every request to the MCP server must include a valid Bearer token. Unauthenticated requests return `401 Unauthorized` and must not execute any tool or expose any data. Paths `/ health`, `/docs`, `/openapi.json`, and `/redoc` are exempt.

## Alternatives considered

- **Build a full OAuth 2.1 authorization server in-process**: correct but disproportionate complexity for Milestone 5. Deferred to Phase 2 or delegated permanently to an external IdP.
- **No authentication (IP allowlist only)**: rejected. IP allowlists are brittle and do not provide per-user or per-client granularity.
- **API key per user (no JWT)**: simpler than OAuth, but provides no standard claims (`sub`, `client_id`) that services can use for RLS. Rejected as primary model.
- **mTLS**: strong but operationally complex for connecting external AI agents that do not support client certificates natively.
- **`authlib` JOSE**: deprecated its JWT API in v1.x. Replaced by `joserfc`, which has a stable, explicit API and supports the same algorithms.

## Consequences

The server trusts whatever IdP is configured via `OAUTH_ISSUER_URL`. The JWKS response from that IdP is cached in memory for the lifetime of the process. Key rotation by the IdP requires a cache flush (call `clear_jwks_cache()`) or a process restart. A TTL-based cache refresh should be added in a future milestone to handle rotation transparently.

Token scopes are not validated in Phase 1 — only signature and expiry are checked. Scope enforcement should be added once the IdP is integrated and token scopes are defined per client.

## Implementation

- `src/vos_studio_mcp/auth/jwt.py` — JWKS fetch and JWT decode via `joserfc`
- `src/vos_studio_mcp/auth/middleware.py` — FastAPI HTTP middleware; enforces Bearer token on all non-open paths
- `src/vos_studio_mcp/auth/context.py` — `ContextVar[str | None]` for the authenticated `client_id`
- `src/vos_studio_mcp/auth/guards.py` — `assert_owns_client(input_client_id)` guard used in services
- `src/vos_studio_mcp/config/env.py` — `OAUTH_ISSUER_URL`, `DEV_BEARER_TOKEN`, `DEV_CLIENT_ID`

## Impact on VOS Studio MCP

- The server must be configured with `OAUTH_ISSUER_URL` pointing to a live IdP in production.
- All MCP tool handlers validate the authenticated identity via `assert_owns_client` in services (not in tools).
- Audit logs (ADR-0015) must record the authenticated actor on every logged event.
- The `.env.example` must include placeholders for `OAUTH_ISSUER_URL`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `DEV_BEARER_TOKEN`, `DEV_CLIENT_ID`.
- Static bearer tokens for development must be clearly marked as non-production in code and documentation.
