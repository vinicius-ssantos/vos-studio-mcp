# ADR-0034 — Provider Usage Ledger and Global Daily Quota

**Status:** Accepted  
**Date:** 2026-05-24  
**Issue:** #42  

---

## Context

ADR-0005 mandates that no paid generation action is executed without explicit
budget authorization.  Previously, budget enforcement existed only at the sprint
level (`Sprint.max_spend_usd` / `Sprint.max_videos`).  There was no global view
of how much the system was spending across all sprints for a given provider in a
day, and no hard ceiling that could prevent runaway spend from a compromised
session or a misconfigured sprint budget.

The missing controls were:

1. **No per-provider daily cap** — a single sprint with a large approved budget
   could exhaust the provider account in one day.
2. **No persistent cost ledger** — spend information lived only as an aggregate
   on the `Sprint` row and was not auditable at the event level.
3. **No operator visibility** — there was no tool to see real-time provider
   consumption before triggering additional paid actions.

---

## Decision

Introduce a **provider usage ledger** (`provider_usage_events` table) and a
**global daily quota guard** enforced at generation time.

### 1. `ProviderUsageEvent` model

A new immutable-ish table records every generation request with:

| Column          | Description                                                  |
|-----------------|--------------------------------------------------------------|
| `provider`      | Provider name (`higgsfield`, `freepik`, …)                   |
| `sprint_id`     | Sprint that triggered the event (SET NULL on delete)         |
| `client_id`     | Client that owns the sprint (CASCADE on delete)              |
| `estimated_usd` | Cost estimate at request time                                |
| `actual_usd`    | Actual billed cost — filled in by the poll task on completion |
| `event_type`    | `generation_requested` or `generation_completed`             |
| `recorded_at`   | UTC server timestamp (server_default)                        |

RLS is enabled: clients can only read their own events; the service role uses
`bypass_rls` for cross-tenant quota aggregation.

### 2. `budget_guard.check_provider_budget()`

Called in `generation_service.request_api_video()` **after** the sprint-level
budget check passes and **before** `adapter.generate_video()` is called.

Algorithm:

```
today_spend = SUM(estimated_usd) WHERE provider=<p> AND recorded_at >= midnight UTC
IF provider_daily_limit_usd > 0 AND today_spend + estimated_usd > limit:
    raise VosError(QUOTA_EXCEEDED, …)
INSERT ProviderUsageEvent(estimated_usd=…, actual_usd=NULL, event_type="generation_requested")
```

If `PROVIDER_DAILY_LIMIT_USD=0` (the default), the quota check is skipped but
the event is still written to populate the ledger.

### 3. `budget_guard.record_actual_cost()`

Called by the poll task when a job completes and the provider reports actual
cost.  Fire-and-forget (swallows all exceptions) — ledger completeness is best
effort and must never block delivery.

### 4. `get_provider_usage_summary` MCP tool

Read-only tool that returns today's per-provider estimated and actual spend,
remaining daily quota, and whether the limit is enforced.  Requires an
authenticated session.

### 5. `ErrorCode.QUOTA_EXCEEDED`

New error code distinct from `BUDGET_EXCEEDED` (sprint level) to allow clients
to surface a specific message when the global operator cap is hit.

### 6. Migration 0011

Creates the table, indexes, and an RLS policy.  Adds `PROVIDER_DAILY_LIMIT_USD`
as an env-var–backed `Settings` field.

---

## Consequences

**Positive:**
- Defence-in-depth: operator-level daily cap layers on top of per-sprint caps.
- Full event-level audit trail for provider spend (complements `audit_logs`).
- Operators can monitor quota consumption via `get_provider_usage_summary`
  before triggering additional paid generations.
- `PROVIDER_DAILY_LIMIT_USD=0` (default) is non-breaking: existing deployments
  get the ledger without enforcement until they opt in.

**Negative / Trade-offs:**
- Two DB round-trips per `request_api_video` call (sprint validation + quota
  check).  Both use indexed queries and are expected to be fast.
- No pessimistic locking — concurrent requests may briefly over-commit.
  Acceptable given typical generation request rates; add advisory locks if
  bursts become a problem.
- `actual_usd` is populated asynchronously by the poll task.  Real-time
  remaining-budget calculations use estimated values.

---

## Alternatives Considered

- **Redis counter for quota**: Fast, but lossy on restart.  DB ledger preferred
  for auditability and durability.
- **Pessimistic DB lock on quota row**: Eliminates over-commit races but adds
  latency and complexity.  Deferred until evidence of a real problem.
- **Per-client daily limit**: More granular but adds complexity to the settings
  model.  Global limit sufficient for current milestone.
