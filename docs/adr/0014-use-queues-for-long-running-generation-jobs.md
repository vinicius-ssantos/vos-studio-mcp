# ADR-0014 — Use queues for long-running generation jobs

Status: Accepted  
Date: 2026-05-21

## Context

Image and video generation jobs may take time, fail, retry, or require status polling. MCP calls should not become unreliable because a provider job takes too long.

## Decision

Use a job queue for long-running or retryable work.

The MCP tool should create a job, return a job ID, and allow follow-up status checks.

## Alternatives considered

- Keep MCP calls open until completion: risky for long jobs.
- Run everything synchronously: simple but fragile.
- Use async job queues: accepted.

## Consequences

This improves reliability and supports retries, status checks, and operational monitoring.

The tradeoff is additional infrastructure such as Redis/BullMQ, Trigger.dev, or a managed queue.

## Impact on VOS Studio MCP

Generation tools should return:

```json
{
  "job_id": "job_123",
  "status": "queued",
  "next_action": "check_generation_status"
}
```
