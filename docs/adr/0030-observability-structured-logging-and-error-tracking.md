# ADR-0030 — Observability: structured logging and error tracking

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio MCP orchestrates multi-step workflows involving external provider APIs, async job queues, database writes, and human approval checkpoints. Several categories of failure are silent by default:

- A generation job is enqueued but the Celery worker crashes before processing it.
- A provider API returns a non-200 status that the adapter swallows as a failed job without alerting anyone.
- An RLS policy blocks a query and the tool returns an empty result instead of an error.
- A webhook arrives with an invalid signature and is rejected — but no one is notified.

Without structured observability, debugging these failures requires digging through raw logs, which is slow and unreliable in an agent-assisted development environment. Coding agents also need machine-readable log output to diagnose failures without human intervention.

Audit logs (ADR-0015) cover what happened for accountability purposes. Observability covers why things fail for operational purposes. These are distinct concerns.

## Decision

Three components form the observability stack:

### 1. Structured logging — `structlog`

Use `structlog` with JSON output as the logging library. Every log entry is a JSON object with consistent fields:

```json
{
  "timestamp": "2026-05-21T14:32:01.123Z",
  "level": "error",
  "event": "provider_api_call_failed",
  "provider": "higgsfield",
  "job_id": "job_abc123",
  "sprint_id": "spr_xyz",
  "client_id": "client_001",
  "status_code": 503,
  "retry_count": 2,
  "duration_ms": 1842
}
```

Every log entry that relates to a request must include `sprint_id` and `client_id` where available. This makes filtering logs by client or sprint trivial in any log aggregation tool.

Sensitive values — API keys, tokens, prompt content, client brand data — must never appear in log entries. Log the fact of an action, not its sensitive content.

In local development (`DEBUG=true`), `structlog` renders human-readable colored output instead of JSON. In production, JSON output is consumed by the deployment platform's log aggregation (Railway, Fly.io, etc.).

### 2. Error tracking — Sentry

Use **Sentry** for exception tracking and alerting. Sentry captures unhandled exceptions, slow transactions, and custom error events with full stack traces and request context.

Sentry is initialized in `server.py` and configured to:
- Capture all unhandled exceptions in FastAPI request handlers and FastMCP tool calls.
- Capture Celery task failures with the task name, arguments (sanitized), and retry count.
- Set `client_id` and `sprint_id` as Sentry tags on every event where available, enabling filtering by client in the Sentry dashboard.
- Sample performance traces at 10% in production to avoid excessive overhead.

Sentry must be configured to **scrub sensitive data**: API keys, bearer tokens, and any field named `*key`, `*token`, `*secret`, `*password` are stripped before the event is sent to Sentry's servers.

### 3. Generation job monitoring

Silent job failures are the most operationally dangerous failure mode. A job that is stuck in `queued` state indefinitely, or that transitions to `failed` without notifying anyone, blocks client delivery without any visible signal.

Two mechanisms address this:

**Job timeout alerts**: every generation job stored in the `jobs` table has a `deadline_at` field set at enqueue time (default: job type's expected maximum duration + 50% buffer). A Celery beat task runs every 5 minutes and queries for jobs where `status = 'queued' OR status = 'running'` and `deadline_at < now()`. These jobs are marked `timed_out` and a Sentry alert is raised.

**Failed job notification**: when a Celery task exhausts its retries and transitions a job to `failed`, it logs a structured error event at `level: critical` and raises a Sentry issue tagged with `provider`, `sprint_id`, and `client_id`. This ensures failed generation is always visible, even if no webhook was received.

## Alternatives considered

- **Python `logging` module only**: built-in but produces unstructured string output by default. Rejected in favor of `structlog` which produces JSON natively and integrates with the standard `logging` module.
- **Datadog or New Relic**: full APM platforms. More powerful but significantly more expensive and complex for an early-stage project. Rejected in favor of Sentry + structured logs to a platform log aggregator.
- **No error tracking, logs only**: logs require active monitoring. Sentry provides proactive alerting when exceptions occur. Rejected for a production system with client data.
- **structlog + Sentry + job monitoring**: selected. Lightweight, open, and sufficient for the operational needs of Milestones 1–5.

## Consequences

Every tool handler, service method, and Celery task must use `structlog` instead of `print()` or `logging.info()`. This is enforced by a Ruff lint rule that flags direct use of the `logging` module in the `src/` directory.

`SENTRY_DSN` becomes a required production environment variable. Local development runs without Sentry (`SENTRY_DSN` left empty disables the SDK).

The `jobs` table gains a `deadline_at` column and a Celery beat schedule must be configured for the timeout monitor task.

## Impact on VOS Studio MCP

- Add `structlog` and `sentry-sdk[fastapi,celery]` to `pyproject.toml`.
- Add `SENTRY_DSN` and `SENTRY_ENVIRONMENT` to `.env.example`.
- Create `src/vos_studio_mcp/config/logging.py` with `structlog` configuration.
- Initialize Sentry in `server.py` before the FastAPI and FastMCP apps are created.
- Add `deadline_at` to the `jobs` table in the first Alembic migration that creates it.
- Create `src/vos_studio_mcp/tasks/monitor.py` with the Celery beat job timeout monitor.
- Add a Ruff rule (`LOG001` or equivalent) to flag `import logging` in `src/`.
- Never log `prompt_content`, `api_key`, `token`, `webhook_payload`, or `asset_url` at any log level.
