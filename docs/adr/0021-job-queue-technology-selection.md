# ADR-0021 — Job queue technology selection

Status: Accepted  
Date: 2026-05-21

## Context

ADR-0014 decided that long-running generation jobs must use a queue rather than blocking synchronously inside the MCP tool call. That ADR listed Redis/BullMQ and Trigger.dev as candidate options but did not select one.

Without a concrete choice, Milestone 5 implementation cannot begin safely. The selection affects infrastructure requirements (does it need a Redis instance?), local development setup, observability, retry behavior, and cost model.

The primary use cases for the queue are:
- AI image and video generation jobs via provider APIs (Higgsfield, Freepik, Magnific)
- Jobs that can fail and need retry with backoff
- Jobs where the result must be registered as an asset after completion
- Jobs that should be trackable by `job_id` from MCP tools like `check_generation_status`

## Decision

Use **Trigger.dev** (self-hosted or cloud) as the job queue and background task runtime.

Trigger.dev was selected because:
- It is designed for long-running, retryable background jobs in TypeScript — exactly the use case here.
- It integrates with Supabase natively, which eliminates the need for a separate Redis instance.
- It provides a built-in dashboard for monitoring job status, retries, and failures — relevant for operational traceability (ADR-0015).
- Jobs are defined as regular TypeScript functions, keeping the codebase consistent (ADR-0001).
- It supports durable execution: if the server restarts mid-job, the job resumes from the last checkpoint.

For local development and very simple internal retry needs, a lightweight in-process retry with exponential backoff is acceptable as a temporary bridge before Trigger.dev is configured.

## Alternatives considered

- **BullMQ + Redis**: mature, widely used, TypeScript-native. Rejected because it requires a Redis instance, which adds infrastructure to manage alongside Supabase Postgres.
- **Trigger.dev**: selected. See reasoning above.
- **Inngest**: similar to Trigger.dev, good TypeScript support, but less mature Supabase integration at the time of this decision.
- **AWS SQS or Google Cloud Tasks**: production-grade managed queues, but introduce cloud-specific dependencies that conflict with the infrastructure-agnostic stance of the current stage.
- **Synchronous polling loop**: rejected. Blocks the MCP server process and is not retryable.

## Consequences

Adding Trigger.dev means the production deployment must include either a Trigger.dev cloud account or a self-hosted Trigger.dev instance. This is a new infrastructure dependency but a manageable one given the tight Supabase integration.

Each provider adapter (ADR-0009) will define one or more Trigger.dev task functions for its generation workflows. The adapter interface contract (ADR-0022) must include how tasks are enqueued and how results are reported back.

Job IDs returned by MCP tools must map to Trigger.dev run IDs or an internal tracking record in Postgres, so that `check_generation_status` can always query status without coupling directly to Trigger.dev's API in the tool layer.

## Impact on VOS Studio MCP

- Add `@trigger.dev/sdk` as a dependency in Milestone 5.
- Create `src/queues/` as the location for Trigger.dev task definitions.
- Each provider adapter must expose a `enqueueGenerationJob(params)` function that returns a `job_id`.
- The `.env.example` must include `TRIGGER_API_KEY` and `TRIGGER_API_URL`.
- Local development can use the Trigger.dev CLI (`npx trigger.dev dev`) to run tasks locally without a cloud account.
