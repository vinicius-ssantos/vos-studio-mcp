# ADR-0036 — Outbound Webhook Retry Policy

**Status:** Accepted  
**Date:** 2026-05-24  
**Issue:** #33  

---

## Context

ADR-0028 specifies that completed or failed video generation jobs trigger an
outbound HTTP notification to the client's registered `webhook_url`.

The initial implementation delivered notifications inline (inside the Celery
poll/upload task) with a single HTTP attempt — best-effort with no retry.  For
clients running SLA-critical integrations (CI pipelines, downstream automation),
a single-attempt delivery model is insufficient: transient network issues,
short server restarts, or load-spikes on the receiving endpoint cause silent
notification loss.

---

## Decision

Deliver outbound webhook notifications through a **dedicated Celery task**
(`tasks.deliver_webhook`) with exponential backoff.

### Task: `tasks.deliver_webhook`

The task is self-contained: all payload fields are passed as keyword arguments
so no DB look-up is needed at retry time.

```python
@celery_app.task(bind=True, max_retries=5, acks_late=True)
def deliver_webhook(self, *, event, webhook_url, asset_id, ...): ...
```

`acks_late=True` ensures the task is not acknowledged until it completes (or is
explicitly abandoned), providing at-least-once delivery guarantees.

### Retry schedule

| Attempt | Countdown (approx.)              |
|---------|----------------------------------|
| 1       | 30 s ± 10 s jitter               |
| 2       | 60 s ± 10 s jitter               |
| 3       | 120 s ± 10 s jitter              |
| 4       | 240 s ± 10 s jitter              |
| 5       | 480 s ± 10 s jitter              |
| abandon | Log `deliver_webhook.abandoned`  |

Total worst-case delivery window: ≈ 15 minutes.

Jitter (`±10 s uniform`) prevents thundering-herd when a batch of jobs
completes simultaneously and their delivery tasks are retried at the same time.

### Trigger points

| Trigger                  | Task call                         |
|--------------------------|-----------------------------------|
| Generation completed     | `enqueue_webhook_completed()`     |
| Generation failed        | `enqueue_webhook_failed()`        |
| Storage upload failed    | `enqueue_webhook_failed(..., event="asset.upload_failed")` |

### SSRF guard

Before each HTTP delivery (including retries), `_deliver()` calls
`check_webhook_url()` (ADR-0032).  This second-checkpoint guard prevents
delivery to URLs that may have been redirected to private addresses between
registration and delivery.

### Failure semantics

After 5 failed attempts, the task logs `deliver_webhook.abandoned` and
**returns without error**.  The job outcome recorded in the DB and audit log
is not affected — webhook delivery failure is distinct from generation failure.

### Non-durable fallback

The inline `notify_job_completed()` / `notify_job_failed()` functions in
`webhook_notifier.py` remain as a non-retryable path for contexts where
Celery is not available (local dev, unit tests).  They are NOT called by
production task workers; only the Celery task is used in production.

---

## Consequences

**Positive:**
- At-least-once delivery: transient endpoint failures are retried automatically.
- Total delivery window (≈ 15 min) sufficient for most real-world receiver
  restart scenarios.
- Self-contained task: no DB round-trip at retry time — robust against
  mid-delivery DB maintenance windows.
- SSRF guard re-runs on each retry: protects against URL redirect attacks.

**Negative / Trade-offs:**
- Notifications may arrive out of order if a retry from an earlier failure
  lands after a later event's first attempt (e.g. `asset.upload_failed` before
  `asset.completed`).  Clients must tolerate duplicate or out-of-order events.
- Requires a running Celery worker and Redis broker.  In dev without Celery,
  notifications use the single-attempt inline path.
- At-least-once semantics: successful delivery may be retried if the worker
  crashes between HTTP success and Celery ack.  Client webhook endpoints must
  be idempotent (keyed on `asset_id` + `event`).
