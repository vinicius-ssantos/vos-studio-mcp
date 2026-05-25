# ADR-0033 — Cross-Tenant Authorization Regression Matrix

**Status:** Accepted  
**Date:** 2026-05-24  
**Issue:** #46  
**Supersedes:** none  
**Related:** ADR-0019 (client_id ownership guard), ADR-0023 (RLS tenant context)

---

## Context

VOS Studio MCP is a multi-tenant system. Each tenant (client) owns objects such as
brand kits, sprints, assets, variant groups, and performance records. Many MCP tools
accept identifiers (sprint_id, asset_id, brand_kit_id, …) that reference these objects.

OWASP API1:2023 identifies **Broken Object-Level Authorization** as the top API risk
when object IDs are caller-supplied. If a tool fails to verify that the authenticated
caller owns the identified object, Client A can read or mutate Client B's data.

The existing guard, `assert_owns_client()` (ADR-0019), was present in some services but
missing in others. There was no systematic test matrix proving end-to-end coverage.

---

## Decision

1. **Application-level guard mandatory for all tenant-scoped services.**  
   Every service function that reads or mutates a tenant-owned object MUST call
   `assert_owns_client(client_id)` before performing any DB write or returning tenant data.
   This applies whether `client_id` comes directly from the input or is resolved by
   looking up a related object (e.g. sprint → client_id).

2. **Guard placement rule.**  
   - If `client_id` is in the input schema: call `assert_owns_client(data.client_id)` as the
     **first line** of the service function (before any DB access).
   - If `client_id` must be resolved from the DB (sprint_id → client_id, asset_id → client_id):
     call `assert_owns_client(resolved_client_id)` immediately after the lookup, before any
     subsequent writes.

3. **Regression matrix in `tests/security/test_cross_tenant_authorization.py`.**  
   A dedicated test file enumerates every tenant-scoped tool and contains at least one
   negative test proving that Client A cannot access Client B's object.  
   Tests run in CI with the rest of the unit test suite (no real database required).

4. **Non-enumerating error responses.**  
   Missing objects return `NOT_FOUND`; unauthorized objects return `INVALID_INPUT` ("client_id
   does not match authenticated session"). Both error codes avoid revealing object existence
   across tenant boundaries (the tool output is structurally identical for the caller).

5. **No-op in dev (auth disabled).**  
   `assert_owns_client()` is a no-op when the auth context is `None` (i.e. neither
   `OAUTH_ISSUER_URL` nor `DEV_BEARER_TOKEN` is configured). This preserves the
   developer-friendly default of running without auth while ensuring the guard fires in
   any environment where auth is enabled.

---

## Tool Classification

### Tenant-scoped (guard required)

| Tool | Input containing client scope | Guard location |
|------|-------------------------------|----------------|
| `create_creative_sprint` | `client_id` | `assert_owns_client(data.client_id)` — first line |
| `save_brand_kit` | `client_id` | `assert_owns_client(data.client_id)` — first line |
| `request_api_video` | `client_id` | `assert_owns_client(data.client_id)` — first line |
| `list_video_jobs` | `client_id` | `assert_owns_client(client_id)` — first line |
| `get_video_job_status` | `asset_id` (resolves to `client_id`) | `assert_owns_client(client_id)` — after asset lookup |
| `get_sprint_status` | `sprint_id` (resolves to `client_id`) | `assert_owns_client(sprint.client_id)` — after sprint load |
| `close_sprint` | `sprint_id` (resolves to `client_id`) | `assert_owns_client(sprint.client_id)` — after sprint load |
| `list_sprint_assets` | `sprint_id` (resolves to `client_id`) | `assert_owns_client(client_id)` — after `set_tenant_context_from_sprint` |
| `register_manual_asset` | `sprint_id` (resolves to `client_id`) | `assert_owns_client(client_id)` — after `set_tenant_context_from_sprint` |
| `record_performance_metrics` | `asset_id` (resolves to `client_id`) | `assert_owns_client(sprint.client_id)` — after asset+sprint lookup |
| `conclude_variant_test` | `group_id` → `sprint_id` → `client_id` | `assert_owns_client(client_id)` — after `set_tenant_context_from_sprint` |
| `prepare_video_blueprint` | `sprint_id` (resolves to `client_id`) | `assert_owns_client(sprint.client_id)` — after sprint load |
| `set_client_webhook` | auth context (no caller-supplied ID) | `AUTH_REQUIRED` if auth context absent |

### System/admin scoped (no ownership check — by design)

| Tool | Reason |
|------|--------|
| `create_client` | Creates a new tenant; no pre-existing owned object |
| `get_server_status` | Server-level diagnostics; no tenant data |
| `search_library` | Intentionally cross-tenant shared library |
| `promote_to_library` | Cross-tenant write, audit-logged with operator_id |

---

## Defence-in-Depth Layers

```
Layer 1 (application): assert_owns_client() in service functions
Layer 2 (database):    PostgreSQL RLS via set_tenant_context() / SET LOCAL row_security = on
Layer 3 (integration): tests/integration/test_rls_isolation.py (requires real DB)
Layer 4 (unit):        tests/security/test_cross_tenant_authorization.py (no DB needed)
```

---

## Consequences

**Positive:**
- Every tenant-scoped tool now has an explicit application-level guard.
- The regression matrix runs in CI and prevents regressions when new tools are added.
- No-op in dev preserves developer ergonomics.

**Negative / Trade-offs:**
- Services that resolve `client_id` from the DB require an extra lookup before the guard fires.
  This is unavoidable for `sprint_id`-only inputs; the cost is one DB round-trip per call.
- Adding a new tool without updating the regression matrix will pass CI silently.
  Teams must consult this ADR when adding tenant-scoped tools.

---

## Adding a New Tenant-Scoped Tool (Checklist)

1. Identify which input field(s) scope the object to a tenant (`client_id`, `sprint_id`, etc.).
2. Add `assert_owns_client(...)` in the service, following the guard placement rule above.
3. Add at least one negative test to `tests/security/test_cross_tenant_authorization.py`.
4. Update the Tool Classification table in this ADR.
