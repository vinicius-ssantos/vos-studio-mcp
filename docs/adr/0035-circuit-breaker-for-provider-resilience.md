# ADR-0035 — Circuit Breaker for Provider Resilience

**Status:** Accepted  
**Date:** 2026-05-24  
**Issue:** #29  

---

## Context

ADR-0009 establishes the provider adapter interface. Provider APIs (Higgsfield,
Freepik, Magnific) are external services that can become temporarily unavailable
due to outages, rate-limit storms, or network partitions.

Without a circuit breaker:
- Every client request that reaches the MCP server triggers a live HTTP call to
  the failing provider, accumulating latency and wasting Celery worker threads.
- Error logs fill with repeated provider timeouts that obscure actionable
  signals.
- A temporary outage can cascade: blocked workers back up the task queue, which
  stalls polling for jobs that were submitted before the outage.

---

## Decision

Implement an **in-process circuit breaker** (`services/circuit_breaker.py`) for
each provider adapter.

### States

```
closed ──(failure_threshold exceeded)──► open
open   ──(recovery_timeout elapsed)───► half_open
half_open ──(trial succeeds)──────────► closed
half_open ──(trial fails)─────────────► open
```

### Parameters (per-provider, configurable at construction)

| Parameter           | Default | Description                                   |
|---------------------|---------|-----------------------------------------------|
| `failure_threshold` | 5       | Consecutive failures before tripping to open  |
| `recovery_timeout`  | 60 s    | Time to wait before allowing a trial call     |

### Error classification

Only `VosError(PROVIDER_ERROR)` and `VosError(PROVIDER_TIMEOUT)` count as
circuit-tripping failures. Input validation errors (`INVALID_INPUT`,
`BUDGET_EXCEEDED`, etc.) do not trip the breaker.

### Integration

Each provider adapter wraps its calls in `CircuitBreaker.call()`:

```python
breaker = get_breaker("higgsfield")
result = await breaker.call("generate_video", adapter.generate_video, params)
```

`CircuitBreaker.call()` raises `VosError(PROVIDER_UNAVAILABLE)` immediately
when the breaker is open, without contacting the external service.

### Observability

The circuit breaker's `_record_metric()` helper calls
`record_provider_call(provider, operation, success=bool)` on every call,
updating the `vos_provider_calls_total` Prometheus counter.  The
`/metrics` endpoint also exposes `vos_circuit_breaker_open{provider}` — a
gauge that reflects the current breaker state at scrape time.

### Scope and limitations

- **In-process only** — state is not shared across multiple Celery workers or
  API server instances.  Under a multi-process deployment, each process has
  independent breaker state.  A shared-state solution (Redis) is deferred
  (YAGNI) until evidence of thundering-herd problems across workers.
- **No persistence** — breaker state resets on process restart.
- **Best-effort metric recording** — metric failures are swallowed so they
  never affect the request path.

---

## Consequences

**Positive:**
- Fast-fail under provider outages: subsequent calls are rejected in microseconds
  instead of waiting for HTTP timeouts.
- Reduced noise in error logs: only the first failure per window is a genuine
  provider error; subsequent rejections are `PROVIDER_UNAVAILABLE` (circuit open).
- Operators can observe breaker state via `vos_circuit_breaker_open` Prometheus
  metric and act on it (e.g. manual reset, alert rule).

**Negative / Trade-offs:**
- No cross-worker state: two workers can both be in `closed` state while the
  provider is down, each tripping independently.  Acceptable given typical
  single-worker configurations.
- Stale open state after provider recovers: must wait for `recovery_timeout`
  before the first trial call.  A `half_open` state with a health-check
  endpoint could shorten this; deferred.
