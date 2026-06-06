# ADR-0040 — RLS Enforcement Role Model and Outbound SSRF IP Pinning

**Status:** Accepted  
**Date:** 2026-06-04  
**Related:** ADR-0023 (multitenancy / RLS), ADR-0032 (SSRF protection), ADR-0019 (auth)

> **Implementation status:** Fully implemented.
> - Decision 2 (outbound SSRF IP pinning) — done.
> - Decision 1 step 1 — webhook ingress bootstrap via `SECURITY DEFINER`
>   functions; the main connection no longer uses `SET row_security = off`.
> - Decision 1 step 2 — `bypass_rls()` has been **removed entirely**. The
>   remaining cross-tenant system tasks (scheduled rollups/cleanup, library-tier
>   refresh, the global provider-budget ledger) now use a dedicated privileged
>   connection (`get_privileged_session`, `DATABASE_PRIVILEGED_URL`); the audit
>   writer uses a plain session since `audit_logs` has no RLS policy.

---

## Context

A security review of the authentication, RLS, and SSRF layers surfaced two
residual risks that are not fixable with isolated code changes because they
touch the database connection model and the outbound HTTP transport.

### Finding 1 — Runtime database role can silently bypass RLS

ADR-0023 designates Row-Level Security as the **enforcement layer** for
multi-tenant isolation: "policies are enforced at the database level … they
cannot be bypassed by a missing `WHERE` clause." The schema backs this up with
`ENABLE` + `FORCE ROW LEVEL SECURITY` and deny-by-default policies keyed on
`current_setting('app.current_client_id', TRUE)`.

However:

- The documented `DATABASE_URL` (`.env.example`) connects as the Postgres
  **superuser** (`postgres`). A superuser — and any role with the `BYPASSRLS`
  attribute, such as the Supabase **service_role** — ignores RLS *even with*
  `FORCE ROW LEVEL SECURITY`. In that configuration the RLS "enforcement layer"
  is inert for the application's own queries; isolation rests entirely on the
  application-level guards (`assert_owns_client`) and explicit
  `client_id == …` filters. Those exist as defense-in-depth, but ADR-0023
  explicitly rejected relying on them as the *sole* mechanism.

- There is an inherent tension with `services/database.py::bypass_rls()`, which
  issues `SET LOCAL row_security = off` for the cross-tenant webhook lookups
  (`get_asset_with_client`, `set_tenant_context_from_sprint`,
  `get_asset_notification_context`). `SET row_security = off` only *returns rows*
  for a role that already bypasses RLS (superuser / `BYPASSRLS`). For a role
  that is genuinely subject to RLS (like the CI `vos_app` role), the same
  statement raises `ERROR: query would be affected by row-level security
  policy`. So a single connection role cannot simultaneously (a) be subject to
  RLS so policies enforce, and (b) use `bypass_rls()`.

CI already proves the policies are correct by running the isolation tests as the
non-privileged `vos_app` role — but the application engine itself uses
`DATABASE_URL`, which the documentation points at a superuser.

- **Known follow-up (RLS session-variable drift).** Every tenant table keys its
  policy on `app.current_client_id` (set by `set_tenant_context`) *except*
  `provider_usage_events`, whose policy (migration `0011`) checks
  `app.tenant_id` — a variable nothing in the app ever sets. Under a genuinely
  RLS-subject role the `provider_usage_events` policy therefore denies all rows,
  so any read of that table must go through the privileged connection
  (`get_privileged_session`). All current callers do. Aligning the policy to
  `app.current_client_id` (so clients can read their own usage events under the
  main role) is deferred to a dedicated RLS migration with isolation tests.

### Finding 2 — DNS rebinding (TOCTOU) on outbound webhook delivery

`webhook_ssrf_guard.check_webhook_url()` resolves the hostname and validates
every resolved IP, then `webhook_notifier._deliver()` hands the **hostname** to
`httpx`, which resolves DNS **again** when it opens the connection. An attacker
controlling DNS for their registered webhook host can answer with a public IP
during the check and a private/metadata IP (e.g. `169.254.169.254`) during the
actual connection, defeating the guard. (Redirect-based bypass is already closed
by pinning `follow_redirects=False`.)

---

## Decision

### 1. Run the application as an RLS-subject role; isolate privileged lookups

- The runtime connection (`DATABASE_URL`) MUST use a role that is **`NOSUPERUSER
  NOBYPASSRLS`** (analogous to the CI `vos_app` role / a Supabase role that is
  *not* `service_role`). This makes the `FORCE` RLS policies the real
  enforcement boundary, as ADR-0023 intends.

- The handful of legitimately cross-tenant lookups (resolving an asset's owning
  `client_id` before any tenant context exists — used by the provider webhook
  ingress) MUST NOT rely on `SET row_security = off` over the main connection.
  Replace `bypass_rls()` with one of:
  - **Preferred:** `SECURITY DEFINER` SQL functions owned by a privileged role
    that return only the minimal columns needed (`client_id`, `sprint_id`,
    `webhook_url`), callable by the app role. RLS stays on for everything else.
    Each such function MUST pin `search_path` (e.g. `pg_catalog, public`) so a
    caller cannot prepend a writable schema and shadow the unqualified table
    references — the standard hardening against `SECURITY DEFINER` search_path
    injection.
  - **Alternative:** a separate, narrowly-scoped engine/connection using a
    privileged role, used *only* by the webhook ingress lookups.

- `.env.example` and deployment docs MUST state that production must not use
  `service_role` / superuser for `DATABASE_URL`.

### 2. Pin the validated IP for outbound webhook delivery

Resolve the webhook hostname **once**, validate every returned address with the
existing `_is_public_ip` rules, then connect to a **validated IP literal** while
preserving the original hostname for TLS SNI and certificate verification (via an
httpx transport that maps the host to the pre-validated address, or by setting
the `Host` header + `sni_hostname` extension). This removes the second,
unvalidated DNS resolution and closes the rebinding window. IPv4 and IPv6 must
both be handled, and certificate verification must remain enabled.

---

## Consequences

**Positive**
- RLS becomes a genuine enforcement boundary, matching ADR-0023's guarantee;
  a missing application-level filter can no longer leak cross-tenant data.
- The outbound webhook path can no longer be steered to internal/metadata
  addresses via DNS rebinding.

**Negative / Trade-offs**
- Requires provisioning and migrating to a dedicated app role plus
  `SECURITY DEFINER` functions (or a second engine) — a deployment and
  migration change, not a pure code change. This is why the change is gated
  behind this ADR rather than shipped directly.
- IP-pinned delivery adds modest complexity to the HTTP client setup and must
  be covered by tests that assert TLS verification still targets the hostname.

## Implementation notes (deferred until Accepted)

- New Alembic migration set for the `SECURITY DEFINER` functions + grants, with
  isolation tests proving the app role still cannot read another tenant's rows
  directly (only via the definer functions).
- Update `services/database.py` to drop `SET row_security = off` from the main
  path.
- Update `services/webhook_notifier.py` delivery client to use the pinned-IP
  transport; extend `tests/services/test_webhook_notifier.py` and the SSRF
  guard tests with a rebinding regression case.
