# ADR-0044 — VOS as MCP Client for Provider MCP Servers

**Status:** Accepted  
**Date:** 2026-05-27  
**Related issues:** #73

---

## Context

VOS Studio MCP is an MCP server that exposes creative operations to upstream
agents (Claude, Codex, etc.).  It currently reaches external providers via two
mechanisms:

- **`dashboard_manual`** — VOS produces execution packs; a human operator
  executes generation outside VOS and registers the result.
- **`api_credits`** — VOS calls provider REST APIs directly, managing cost,
  job polling, storage, and audit.

Higgsfield (and potentially other providers) now publish official hosted MCP
servers.  Connecting to one of these servers creates a third execution path:

```
upstream agent → VOS MCP server → internal MCP client → provider MCP server
```

This is architecturally sound:
- It uses an official, provider-supported automation surface (ADR-0004 compliant).
- It avoids storing a provider REST API key when OAuth-based auth is available.
- Generation still passes through VOS cost, QA, audit, and storage lifecycle.

However it introduces a new pattern: **VOS acts as both an MCP server and an
MCP client within the same process.**

---

## Decision

Implement provider MCP client support in a dedicated package:

```
src/vos_studio_mcp/services/mcp_clients/
```

Each provider that exposes an MCP server gets its own module (e.g.
`higgsfield.py`).  No change is made to existing provider adapters or tools.

### Transport

Use **Streamable HTTP** (JSON-RPC 2.0 over POST) as the wire protocol.
The client sends POST requests to the provider MCP endpoint and parses
JSON or SSE responses.  This does not require an additional MCP SDK dependency
— the existing `httpx` client is sufficient for Phase 1 discovery.

### Authentication

Phase 1 uses a single bearer token supplied via environment variable
(`HIGGSFIELD_MCP_ACCESS_TOKEN`).  The token is never logged or returned in
MCP tool outputs.  Phase 2 will decide on an OAuth refresh strategy once the
provider's auth model is confirmed.

### Feature flag

Each MCP client is guarded by an enabled flag (`HIGGSFIELD_MCP_ENABLED`,
default `false`).  Disabled by default so that production deployments are not
affected until an operator explicitly opts in.

### Phase 1 scope (discovery only)

Phase 1 adds a **diagnostic tool** (`list_higgsfield_mcp_capabilities`) that:

1. Performs the MCP initialize handshake.
2. Sends `notifications/initialized` (spec compliance).
3. Lists tools, resources, and prompts from the server.
4. Returns a compact structured response.
5. Never triggers generation or any paid action.

Generation is out of scope for Phase 1.

### Error contract

The diagnostic tool never raises; it always returns a structured response
with one of: `ok`, `disabled`, `auth_required`, `unreachable`.  Sensitive
fields (token, session ID) are redacted from logs and responses.

---

## Consequences

### Positive

- VOS can verify connectivity to provider MCP servers before committing to
  full Phase 2–4 integration.
- Answers the core technical question: does the provider accept a bearer token
  from a non-interactive client?
- No impact on existing tools, adapters, database, or task queue.

### Negative / risks

- Provider MCP auth model may require interactive OAuth, making server-side
  token injection insufficient.  Phase 2 must revisit this.
- Provider MCP tool schemas may change without notice — VOS must treat them
  as unstable in Phases 2–4.
- Session state management (Mcp-Session-Id) adds request sequencing
  requirements compared to stateless REST calls.

---

## Compliance

- **ADR-0004**: Official MCP is an accepted automation surface; no dashboard
  automation.
- **ADR-0005**: Phase 1 does not perform any paid action.
- **ADR-0009**: Provider MCP clients are adapters behind the service boundary.
- **ADR-0016**: Token stored in environment variable, never committed or logged.
