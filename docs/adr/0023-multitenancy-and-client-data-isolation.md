# ADR-0023 — Multitenancy and client data isolation

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio MCP manages data for multiple clients — brand kits, creative sprints, assets, prompts, approvals, audit logs, and delivery packs. All of this data is stored in a shared Postgres database (ADR-0007) and accessed by AI agents authenticated via the model defined in ADR-0019.

Without an explicit isolation model, a bug, a misconfigured query, or a compromised token could allow one client's data to be read or modified by another agent session. For a creative agency handling client brand assets and campaign data, a cross-client data leak is a critical business and legal risk.

Supabase provides Row Level Security (RLS) as a first-class feature of Postgres. RLS policies are enforced at the database level, not in application code — which means they cannot be bypassed by a missing `WHERE` clause in a tool handler.

## Decision

Use **Postgres Row Level Security (RLS) via Supabase** as the primary client data isolation mechanism.

Every table that contains client-scoped data must have RLS enabled and a policy that restricts row access to the authenticated `client_id` present in the current session context.

The application sets the current client context at the start of each authenticated request by calling:

```sql
SELECT set_config('app.current_client_id', $clientId, true);
```

RLS policies on client-scoped tables reference this configuration:

```sql
CREATE POLICY client_isolation ON sprints
  USING (client_id = current_setting('app.current_client_id')::uuid);
```

Tables that are not client-scoped (e.g. internal configuration, provider pricing data, system audit events) do not require RLS but must not expose client-identifying data.

Soft-delete (`deleted_at` timestamp) is the standard for removing client records. Hard deletes are reserved for explicit data deletion requests subject to approval and audit logging (ADR-0015).

## Alternatives considered

- **Separate schema per client**: strong isolation, but operationally complex. Schema creation, migration (ADR-0020), and connection pooling become significantly harder at scale. Rejected.
- **Separate database per client**: maximum isolation, but prohibitively expensive and operationally unmanageable for an agency with many clients. Rejected.
- **Application-level filtering only (WHERE client_id = ?)**: relies on every query in every tool handler being correct. A single missing filter leaks data. Rejected as the sole mechanism — application-level filters remain as defense-in-depth but RLS is the enforcement layer.
- **RLS via Supabase**: selected. Enforced at the database level, auditable, compatible with Drizzle ORM (ADR-0020), and supported natively in Supabase.

## Consequences

RLS policies must be written and reviewed alongside schema migrations (ADR-0020). A migration that adds a new client-scoped table without an RLS policy is incomplete and must not be merged.

Tool handlers must always set the client context before any database query. This context must come from the authenticated session (ADR-0019), not from user-supplied tool input — a tool parameter like `client_id` can be used to select a resource, but authorization is enforced by RLS against the session's client context.

Testing must include cross-client isolation tests: a query authenticated as client A must not return rows belonging to client B, even if the query omits a WHERE clause.

## Impact on VOS Studio MCP

- Enable RLS on all client-scoped tables in each migration file (ADR-0020).
- Create a `src/vos_studio_mcp/services/database.py` helper that sets `app.current_client_id` from the authenticated session before returning a database connection for use in a request.
- Never trust `client_id` from MCP tool input for authorization decisions — use it only for lookups, with RLS as the enforcement layer.
- Add cross-client isolation as a required test category before Milestone 3 is considered complete.
- Soft-delete columns (`deleted_at`) must be included in the initial schema for all client-scoped tables and referenced in RLS policies to prevent deleted records from appearing in queries.
