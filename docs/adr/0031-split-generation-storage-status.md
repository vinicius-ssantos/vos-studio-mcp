# ADR-0031 — Split generation_status from storage_status

**Status:** Accepted  
**Date:** 2026-05-23  
**Related issues:** #18

---

## Context

Provider generation and asset storage are two distinct lifecycle phases that
can succeed or fail independently.  Before this change a single
`generation_status` field tracked both:

- Whether the provider job completed (Higgsfield, Freepik, …)
- Whether the generated file was uploaded to our permanent R2 storage

This blending caused operational ambiguity: if a CDN download or R2 upload
failed *after* the provider had already generated the video, the only way to
represent that was to set `generation_status = "failed"` — which was
semantically wrong and would mislead operators into re-requesting generation
instead of retrying the upload.

---

## Decision

Introduce a dedicated `storage_status` column on the `assets` table alongside
the existing `generation_status`.

### generation_status (provider lifecycle)

| Value | Meaning |
|-------|---------|
| `manual` | Asset registered manually, no provider job |
| `pending` | Job submitted, waiting for provider to start |
| `processing` | Provider is actively generating |
| `completed` | Provider finished successfully |
| `failed` | Provider job failed or timed out |

### storage_status (upload lifecycle)

| Value | Meaning |
|-------|---------|
| `not_required` | No upload needed (manual asset, or generation still in progress) |
| `pending` | Upload task has been enqueued |
| `stored` | File uploaded successfully to R2 |
| `failed` | Upload failed after all retries |

### Ownership boundaries

| Component | May write |
|-----------|-----------|
| Webhook handler | `generation_status` only |
| `poll_video_job` task | `generation_status` only; sets `storage_status = "pending"` when upload is enqueued |
| `upload_video_to_storage` task | `storage_url` + `storage_status` only |
| Manual registration | both fields set at creation, no further updates |

`storage_url` remains the permanent R2 URL written by the upload task on
success.  The ephemeral CDN URL from the provider is **never** written to
`storage_url`.

---

## Consequences

**Good:**
- Operators can distinguish "provider failed" from "upload failed" without
  inspecting logs.
- Retrying a failed upload does not require re-requesting a paid generation.
- Tool responses (`get_video_job_status`) expose both statuses, giving the MCP
  client full lifecycle visibility.
- Each component has a single, clear write-ownership over its status field.

**Trade-off:**
- One additional DB column and migration.
- Existing data is back-filled with `storage_status = 'not_required'` (safe
  default — all existing assets either lack a provider job or already have a
  `storage_url`).
