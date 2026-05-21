# ADR-0019 — Define authentication model for the remote MCP server

Status: Accepted  
Date: 2026-05-21

## Context

ADR-0002 decided that VOS Studio MCP will be a remote HTTP server exposed at `https://mcp.vosstudio.com/mcp`. That endpoint will receive connections from external AI agents (Claude, ChatGPT, Codex) and potentially from multiple users or clients.

Exposing an MCP server on the public internet without an explicit authentication model is a critical security gap. Any unauthenticated endpoint could be called by unauthorized agents, leak client data, trigger paid provider actions, or bypass the approval controls defined in ADR-0005.

The MCP spec supports an OAuth 2.1 authorization flow for remote servers. The server can also be protected at the transport layer using simpler mechanisms such as static bearer tokens or mTLS.

## Decision

Use OAuth 2.1 with PKCE as the primary authentication mechanism for the remote MCP server, following the MCP specification for remote server authorization.

For internal and development use, a static bearer token via `Authorization: Bearer <token>` header is acceptable as a temporary fallback. This fallback must never be used in production with client data.

Every request to the MCP server must include a valid, scoped credential. Unauthenticated requests must return `401 Unauthorized` and must not execute any tool or expose any data.

## Alternatives considered

- **No authentication (IP allowlist only)**: rejected. IP allowlists are brittle and do not provide per-user or per-client granularity.
- **API key per user**: simpler than OAuth, but no standard support in the MCP protocol. Acceptable as a secondary internal mechanism, not as the primary model for agent-facing use.
- **mTLS**: strong but operationally complex for connecting external AI agents (Claude, ChatGPT) that do not support client certificates natively.
- **OAuth 2.1 with PKCE**: aligned with the MCP remote server specification, supports scoped tokens, and is compatible with major AI platforms.

## Consequences

OAuth 2.1 adds implementation complexity in Milestone 5, but it is the correct long-term model for a multi-agent, multi-client server exposed on the internet.

Token scopes should be designed to enforce the principle of least privilege: a token for a specific client should not be able to read or modify another client's data.

The authentication layer should be implemented before any production endpoint is exposed, even for internal testing with real client data.

## Impact on VOS Studio MCP

- The server must implement an OAuth 2.1 authorization server or delegate to an identity provider (e.g. Supabase Auth, Auth0).
- All MCP tool handlers must validate the authenticated identity before accessing any data.
- Audit logs (ADR-0015) must record the authenticated actor on every logged event.
- The `.env.example` must include placeholders for auth provider configuration (client ID, secret, issuer URL).
- Static bearer tokens for development must be clearly marked as non-production in code and documentation.
