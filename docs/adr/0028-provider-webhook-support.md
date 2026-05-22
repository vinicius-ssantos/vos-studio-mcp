# ADR-0028 — Provider webhook support

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22

## Context

ADR-0014 decided that long-running generation jobs use a queue (Celery + Redis per ADR-0021). The current model for job completion is polling: a Celery task calls `check_job_status` on the provider adapter at regular intervals until the job is complete or has failed.

Polling has two problems at scale:
- It generates unnecessary API calls to provider endpoints when jobs are not yet complete.
- Response latency is bounded by the polling interval, not by the actual completion time. A video generation that finishes in 47 seconds will not be registered until the next poll, which may be 60 seconds later.

Several providers (including Higgsfield) support webhooks: the provider sends an HTTP POST to a registered endpoint when a job completes, fails, or changes state. Webhook-driven completion is faster, more efficient, and reduces unnecessary API usage.

## Decision

**Phase 1 (partially implemented — Milestone 5):** The `ProviderAdapter` Protocol (ADR-0022) includes `verify_webhook_signature(payload, headers) -> bool` as a required method. `HiggsFieldAdapter` implements HMAC-SHA256 verification using `WEBHOOK_SECRET_HIGGSFIELD`. The webhook endpoint and Celery integration are deferred to the next milestone (tracked in GitHub Issue #6).

**Phase 2 (planned):** Add a webhook receiver endpoint to the FastAPI layer.

### Endpoint

```
POST /webhooks/{provider_id}
```

Each provider has its own sub-path so that signature verification logic can be provider-specific. This endpoint is not part of the MCP protocol and must be mounted on the FastAPI app before the auth middleware chain (webhook validation replaces Bearer token auth for this path).

### Processing flow

1. Provider sends `POST /webhooks/higgsfield` with a payload describing the completed (or failed) job.
2. The handler reads the raw body before any JSON parsing, and calls `adapter.verify_webhook_signature(payload, headers)`. Requests with invalid signatures return `403` immediately and are logged as a security event (ADR-0015).
3. The handler extracts `generation_id` and `status` from the payload, looks up the `Asset` by `provider_job_id`, and updates `generation_status` in Postgres.
4. If status is `COMPLETED`, the handler dispatches a Celery task `upload_video_to_storage` to download from the provider CDN and re-upload to the project's R2 bucket.
5. The handler returns `{"received": true}` immediately — all DB writes and task dispatching happen within the request but the response must not expose DB content or internal state.

### Polling as fallback

Polling is retained as a fallback for providers that do not support webhooks and for jobs where the webhook was not received (network failure, provider outage). The Celery polling task (`poll_video_job`) checks the DB state before calling the provider API — if the job is already marked complete by a webhook, it skips the API call.

The polling interval for webhook-capable providers is extended (e.g. 5 minutes instead of 30 seconds) to reduce redundant calls while still catching missed webhooks.

### Signature verification

Each provider uses a different signature scheme. The implementation contract in `ProviderAdapter.verify_webhook_signature`:
- Receives the raw request body as `bytes` and the request headers as `dict[str, str]`.
- Returns `True` only if the signature is valid.
- Returns `False` (never raises) when the secret is unconfigured or the signature is invalid. Failing closed is required.
- `ManualDashboardAdapter` returns `True` by default (no webhooks).

**Higgsfield implementation:** HMAC-SHA256 with `WEBHOOK_SECRET_HIGGSFIELD`. Signature is sent in the `X-Higgsfield-Signature` header, optionally prefixed with `sha256=`. Verified via `hmac.compare_digest` to prevent timing attacks.

## Alternatives considered

- **Polling only**: simple but inefficient at scale and adds latency to job completion. Rejected as the permanent strategy.
- **Webhooks only, no polling**: fails silently when a webhook is missed. Rejected — polling as fallback is required for reliability.
- **Webhooks with polling fallback**: selected. Webhooks drive normal operation; polling catches edge cases.
- **Server-Sent Events from MCP to client**: the MCP client polls `get_video_job_status` — this is a separate concern from how the server learns about job completion internally.

## Consequences

The FastAPI layer will gain a `POST /webhooks/{provider_id}` endpoint that is not part of the MCP protocol. This endpoint must be publicly accessible so providers can reach it, but it must not be confused with the MCP endpoint. Rate limiting and IP allowlisting (per provider's published IP ranges) are recommended.

Signature verification secrets (`WEBHOOK_SECRET_*`) are credentials that must be managed with the same care as API keys (ADR-0016).

Webhook payloads are external untrusted input. The handler must validate the payload schema strictly and never execute arbitrary logic based on unverified content.

## Implementation status

| Component | Status |
|-----------|--------|
| `verify_webhook_signature` in `ProviderAdapter` Protocol | ✅ Implemented |
| `HiggsFieldAdapter.verify_webhook_signature` (HMAC-SHA256) | ✅ Implemented |
| `POST /webhooks/{provider_id}` FastAPI endpoint | ⏳ Issue #6 item B |
| Celery `poll_video_job` task | ⏳ Issue #6 item C |
| Celery `upload_video_to_storage` task | ⏳ Issue #6 item D |

## Impact on VOS Studio MCP

- Create `src/vos_studio_mcp/routes/webhooks.py` with provider-specific handlers.
- Register webhook routes on the FastAPI app in `server.py`, bypassing auth middleware.
- Add `WEBHOOK_SECRET_HIGGSFIELD` to `.env.example` (already present).
- Update Celery polling tasks to check DB state before calling provider API.
- Target: next milestone, tracked in Issue #6.
