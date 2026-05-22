# ADR-0021 — Job queue technology selection

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-21

## Context

ADR-0014 decided that long-running generation jobs must use a queue rather than blocking synchronously inside the MCP tool call.

The original decision selected Trigger.dev because it integrates with Supabase and is TypeScript-native. With the switch to Python (ADR-0001 amended), Trigger.dev is no longer applicable — it has no Python SDK. A Python-native queue solution is required.

The primary use cases for the queue remain unchanged:
- AI image and video generation jobs via provider APIs (Higgsfield, Freepik, Magnific)
- Jobs that can fail and need retry with exponential backoff
- Jobs where the result must be registered as an asset after completion
- Jobs that should be trackable by `job_id` from MCP tools like `check_generation_status`

## Decision

Use **Celery** with **Redis** as the job queue and background task runtime.

Celery was selected because:
- It is the standard background task library in the Python ecosystem, battle-tested in production for over 12 years.
- It supports retries with exponential backoff, task chaining, and result storage natively.
- Redis as the broker is lightweight, fast, and requires no additional schema management alongside Postgres.
- **Flower** (Celery's monitoring dashboard) provides real-time visibility into job status, retries, and failures — equivalent to the observability benefit that Trigger.dev offered in the original decision.
- Workers are regular Python async functions, consistent with the FastAPI codebase (ADR-0001).
- Strong community knowledge reduces risk for agent-assisted development.

For local development, a single Redis instance (via Docker) runs alongside the FastAPI server. Workers are started separately with `make worker`, which resolves to `uv run celery -A vos_studio_mcp.tasks.celery_app:celery_app worker --loglevel=info`.

## Alternatives considered

- **Trigger.dev**: TypeScript-only. Not applicable after ADR-0001 amendment. Rejected.
- **ARQ**: async-native Python queue backed by Redis. Lighter than Celery and well-suited for async FastAPI projects. Rejected in favor of Celery's greater maturity and monitoring tooling (Flower), but a valid fallback if Celery proves heavy for the initial workload.
- **Dramatiq + Redis**: good alternative to Celery with a cleaner API, but smaller community and less monitoring tooling. Rejected.
- **AWS SQS or Google Cloud Tasks**: managed queues that eliminate the Redis dependency, but introduce cloud-specific coupling. Rejected for the current stage.
- **Synchronous polling loop**: rejected. Blocks the server process and is not retryable.

## Consequences

The production deployment requires a Redis instance alongside the FastAPI server and Celery workers. This is a well-understood operational pattern with broad hosting support (Railway, Fly.io, Render all offer managed Redis).

Each provider adapter (ADR-0009) defines one or more Celery task functions for its generation workflows. The adapter interface contract (ADR-0022) specifies how tasks are enqueued and how results are reported back.

Job IDs returned by MCP tools map to Celery task IDs stored in an internal `jobs` table in Postgres, so `check_generation_status` queries the database rather than coupling directly to Celery's result backend.

## Impact on VOS Studio MCP

- Add `celery[redis]` and `redis` to `pyproject.toml` in Milestone 5.
- Add `flower` as a dev/monitoring dependency.
- Create `src/vos_studio_mcp/tasks/generation.py` as the location for Celery task definitions.
- Each provider adapter must expose an `enqueue_generation_job(params)` method that returns a `job_id`.
- The `.env.example` must include `CELERY_BROKER_URL` (e.g. `redis://localhost:6379/0`) and `CELERY_RESULT_BACKEND`.
- Local development uses `docker compose up redis` to start Redis, then `make worker` to start workers.
- Flower monitoring runs on a separate port (default `5555`) for local and staging visibility.
