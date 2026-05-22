# ADR-0030 — Observability and failure diagnostics

Status: Accepted  
Date: 2026-05-21

## Context

The project already defines audit logging (ADR-0015), but it does not yet define runtime observability for MCP tool execution and generation workflows. In practice, generation can fail silently when provider APIs return ambiguous payloads, background jobs time out, or adapter logic swallows errors and only returns a generic failure.

Without a clear observability model, debugging incidents is slow and expensive:
- Operators cannot trace a failed tool call across API request, queue task, provider interaction, and database write.
- Engineering cannot distinguish validation failures, provider outages, quota/credit errors, or code regressions quickly.
- Local development and CI cannot reliably reproduce production failures due to missing correlation and error context.

Before Milestone 0 scaffold and first tool implementation, the baseline observability contract should be explicit so all components are instrumented consistently from day one.

## Decision

Adopt a three-part observability baseline:

1. Structured logging (JSON) across API, tools, services, workers, and adapters.
2. Error tracking with exception capture and stack traces for all unhandled and classified failures.
3. Correlation-first diagnostics for generation workflows, including deterministic IDs and failure reasons.

### Structured logging contract

All logs are emitted as JSON with required fields:
- `timestamp`
- `level`
- `service` (`api`, `worker`, `mcp-tool`, `provider-adapter`)
- `event`
- `trace_id`
- `request_id` (when applicable)
- `client_id` (when authenticated)
- `tool_name` (for MCP tool executions)
- `job_id` (for async generation)
- `provider` (for adapter calls)
- `error_code` (for failures)

Sensitive values (API keys, auth tokens, raw prompts containing client secrets) must be redacted before logging.

### Error tracking

Unhandled exceptions in FastAPI request handlers, MCP tool handlers, and Celery tasks are captured by an error tracking backend with:
- stack trace
- release/version
- environment
- tagged context (`tool_name`, `provider`, `client_id`, `job_id`, `trace_id`)

Known failure classes are normalized to explicit error codes (for example `PROVIDER_TIMEOUT`, `PROVIDER_AUTH_ERROR`, `VALIDATION_ERROR`, `BUDGET_REJECTED`, `RLS_DENIED`).

### Failure diagnostics for generation workflows

Every generation attempt receives a `generation_attempt_id` and emits lifecycle events:
- `generation.requested`
- `generation.queued`
- `generation.started`
- `generation.provider_submitted`
- `generation.provider_polled` (if async provider)
- `generation.completed` or `generation.failed`

`generation.failed` must include:
- normalized `error_code`
- provider raw status/error excerpt (sanitized)
- retry eligibility flag
- terminal vs transient classification

## Alternatives considered

- **Audit logs only (ADR-0015)**: useful for business traceability but insufficient for runtime debugging and stack-level diagnostics. Rejected as sole mechanism.
- **Unstructured text logs**: easy to start, but poor for queryability and cross-service correlation. Rejected.
- **Metrics-only observability**: can show symptoms but not root causes of silent failures. Rejected.
- **Structured logs + error tracking + correlation IDs**: selected for practical debugging and incremental adoption.

## Consequences

Implementation must include logging middleware, shared logger utilities, and common error normalization modules before or during Milestone 0 scaffold. New tools and adapters must emit lifecycle events and attach correlation fields.

Operationally, incident triage will rely on `trace_id` and `generation_attempt_id` as the primary lookup keys across logs, queue records, and error tracking events.

## Implementation status

| Component | Status |
|-----------|--------|
| `observability/logging.py` — JSON formatter + redaction | ✅ Implemented |
| `observability/middleware.py` — `trace_id`/`request_id` injection | ✅ Implemented |
| `observability/context.py` — `ContextVar` correlation store | ✅ Implemented |
| `ErrorCode` enum with all ADR-0030 codes | ✅ Implemented |
| `VosError` FastAPI exception handler (structured JSON, 400) | ✅ Implemented |
| Sentry `FastApiIntegration` + `StarletteIntegration` | ✅ Implemented |
| Sentry `CeleryIntegration` | ✅ Implemented |
| Generation lifecycle events (`generation.requested`, `generation.queued`, `generation.provider_submitted`, `generation.completed`, `generation.failed`) | ✅ Implemented |
| Celery task base class with correlation propagation | ✅ Implemented — `CorrelatedTask` injects/restores `trace_id`/`request_id` via task headers |

## Impact on VOS Studio MCP

- `src/vos_studio_mcp/observability/` — JSON logging, correlation middleware, context vars.
- `src/vos_studio_mcp/errors.py` — `ErrorCode` StrEnum, `VosError` exception.
- `server.py` — Sentry init with FastAPI + Celery integrations; `VosError` exception handler.
- `src/vos_studio_mcp/tasks/base.py` — `CorrelatedTask` base class; registered as `task_cls` in `celery_app.py`.
- `generation_service.py` / `tasks/poll_video.py` — lifecycle log events with `job_id`, `provider`, `error_code` fields.
