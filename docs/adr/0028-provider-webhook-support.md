# ADR-0028 — Provider webhook support

Status: Accepted  
Date: 2026-05-21

## Context

ADR-0014 decided that long-running generation jobs use a queue (Celery + Redis per ADR-0021). The current model for job completion is polling: a Celery task calls `check_job_status` on the provider adapter at regular intervals until the job is complete or has failed.

Polling has two problems at scale:
- It generates unnecessary API calls to provider endpoints when jobs are not yet complete.
- Response latency is bounded by the polling interval, not by the actual completion time. A video generation that finishes in 47 seconds will not be registered until the next poll, which may be 60 seconds later.

Several providers (including Higgsfield) support webhooks: the provider sends an HTTP POST to a registered endpoint when a job completes, fails, or changes state. Webhook-driven completion is faster, more efficient, and reduces unnecessary API usage.

Without a webhook architecture, the system is stuck with polling indefinitely — including for providers that support webhooks — because there is no endpoint to receive callbacks.

## Decision

Add a webhook receiver endpoint to the FastAPI layer that accepts provider callbacks and updates job state in the database.

### Endpoint

```
POST /webhooks/{provider_id}
```

Each provider has its own sub-path so that signature verification logic can be provider-specific.

### Processing flow

1. Provider sends POST to `/webhooks/higgsfield` with a payload describing the completed (or failed) job.
2. FastAPI middleware verifies the webhook signature using the `WEBHOOK_SECRET_{PROVIDER}` environment variable (ADR-0016). Requests with invalid signatures return `403` immediately and are logged as a security event (ADR-0015).
3. The webhook handler extracts the `job_id` and new status from the payload, updates the `jobs` table in Postgres, and enqueues a Celery follow-up task if the job completed successfully (e.g. `register_asset_from_job`).
4. The handler returns `200` immediately — all processing happens asynchronously. This prevents provider retry storms caused by slow processing.

### Polling as fallback

Polling is retained as a fallback for providers that do not support webhooks and for jobs where the webhook was not received (network failure, provider outage). The Celery polling task checks the `jobs` table before calling the provider API — if the job is already marked complete by a webhook, it skips the API call.

The polling interval for webhook-capable providers is extended (e.g. 5 minutes instead of 30 seconds) to reduce redundant calls while still catching missed webhooks.

### Signature verification

Each provider uses a different signature scheme. The `ProviderAdapter` Protocol (ADR-0022) is extended with an optional method:

```python
class ProviderAdapter(Protocol):
    ...
    def verify_webhook_signature(
        self, payload: bytes, headers: dict[str, str]
    ) -> bool: ...
```

Manual dashboard adapters return `True` by default (they never send webhooks). Adapters that do not implement webhook verification raise `NotImplementedError`, and the system falls back to polling for those providers.

## Alternatives considered

- **Polling only**: simple but inefficient at scale and adds latency to job completion. Rejected as the permanent strategy.
- **Webhooks only, no polling**: fails silently when a webhook is missed. Rejected — polling as fallback is required for reliability.
- **Webhooks with polling fallback**: selected. Webhooks drive normal operation; polling catches edge cases.
- **Server-Sent Events from MCP to client**: the MCP client polls `check_generation_status` — this is a separate concern from how the server learns about job completion internally.

## Consequences

The FastAPI layer gains a new `POST /webhooks/{provider_id}` endpoint that is not part of the MCP protocol. This endpoint must be publicly accessible so providers can reach it, but it must not be confused with the MCP endpoint. Rate limiting and IP allowlisting (per provider's published IP ranges) are recommended for the webhook endpoint.

Signature verification secrets (`WEBHOOK_SECRET_*`) are new credentials that must be managed with the same care as API keys (ADR-0016).

Webhook payloads are external untrusted input. The handler must validate the payload schema strictly and never execute arbitrary logic based on unverified content.

## Impact on VOS Studio MCP

- Create `src/vos_studio_mcp/webhooks/` with one file per provider (e.g. `higgsfield.py`).
- Register webhook routes on the FastAPI app (not on FastMCP) in `server.py`.
- Add `verify_webhook_signature` to the `ProviderAdapter` Protocol in `base.py`.
- Add `WEBHOOK_SECRET_HIGGSFIELD` and `WEBHOOK_SECRET_FREEPIK` to `.env.example` (already added).
- Update Celery polling tasks to check DB state before calling provider API.
- Target: Milestone 5 (production readiness), alongside deployment and rate limiting.
